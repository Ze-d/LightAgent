import asyncio

import pytest

from app.a2a.event_broker import A2AEventBroker
from app.a2a.schemas import (
    StreamResponse,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)


def _status_event(
    *,
    state: TaskState,
    final: bool = False,
) -> StreamResponse:
    return StreamResponse(
        statusUpdate=TaskStatusUpdateEvent(
            taskId="task-1",
            contextId="ctx-1",
            status=TaskStatus(state=state),
            final=final,
        )
    )


def test_event_broker_fans_out_events_to_multiple_subscribers():
    async def scenario():
        broker = A2AEventBroker()
        first = broker.subscribe("task-1")
        second = broker.subscribe("task-1")

        broker.publish("task-1", _status_event(state=TaskState.working))
        broker.publish(
            "task-1",
            _status_event(state=TaskState.completed, final=True),
        )

        first_working = await first.__anext__()
        second_working = await second.__anext__()
        first_final = await first.__anext__()
        second_final = await second.__anext__()

        assert first_working.status_update.status.state == TaskState.working
        assert second_working.status_update.status.state == TaskState.working
        assert first_final.status_update.status.state == TaskState.completed
        assert first_final.status_update.final is True
        assert second_final.status_update.status.state == TaskState.completed

        with pytest.raises(StopAsyncIteration):
            await first.__anext__()
        with pytest.raises(StopAsyncIteration):
            await second.__anext__()

    asyncio.run(scenario())


def test_event_broker_replays_logged_events():
    async def scenario():
        broker = A2AEventBroker()
        broker.publish("task-1", _status_event(state=TaskState.working))

        subscription = broker.subscribe("task-1", replay=True)
        event = await subscription.__anext__()

        assert event.status_update.status.state == TaskState.working
        subscription.close()

    asyncio.run(scenario())
