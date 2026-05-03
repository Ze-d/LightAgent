from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Lock

from app.a2a.schemas import StreamResponse, TERMINAL_TASK_STATES


@dataclass(frozen=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[StreamResponse | None]


class A2AEventSubscription:
    def __init__(
        self,
        broker: "A2AEventBroker",
        task_id: str,
        subscriber: _Subscriber,
    ) -> None:
        self._broker = broker
        self._task_id = task_id
        self._subscriber = subscriber
        self._closed = False

    def __aiter__(self) -> "A2AEventSubscription":
        return self

    async def __anext__(self) -> StreamResponse:
        item = await self._subscriber.queue.get()
        if item is None:
            self.close()
            raise StopAsyncIteration
        return item

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._broker.unsubscribe(self._task_id, self._subscriber)


class A2AEventBroker:
    """In-memory ordered event log and live fan-out per A2A task."""

    def __init__(self) -> None:
        self._events: dict[str, list[StreamResponse]] = {}
        self._subscribers: dict[str, list[_Subscriber]] = {}
        self._lock = Lock()

    def events(self, task_id: str) -> list[StreamResponse]:
        with self._lock:
            return [
                event.model_copy(deep=True)
                for event in self._events.get(task_id, [])
            ]

    def subscribe(
        self,
        task_id: str,
        *,
        replay: bool = False,
    ) -> A2AEventSubscription:
        loop = asyncio.get_running_loop()
        subscriber = _Subscriber(loop=loop, queue=asyncio.Queue())
        with self._lock:
            self._subscribers.setdefault(task_id, []).append(subscriber)
            replay_events = [
                event.model_copy(deep=True)
                for event in self._events.get(task_id, [])
            ] if replay else []

        for event in replay_events:
            subscriber.queue.put_nowait(event)
        if replay_events and self._is_terminal_event(replay_events[-1]):
            subscriber.queue.put_nowait(None)

        return A2AEventSubscription(self, task_id, subscriber)

    def unsubscribe(self, task_id: str, subscriber: _Subscriber) -> None:
        with self._lock:
            subscribers = self._subscribers.get(task_id)
            if not subscribers:
                return
            self._subscribers[task_id] = [
                item for item in subscribers
                if item is not subscriber
            ]
            if not self._subscribers[task_id]:
                self._subscribers.pop(task_id, None)

    def publish(self, task_id: str, response: StreamResponse) -> None:
        event = response.model_copy(deep=True)
        with self._lock:
            self._events.setdefault(task_id, []).append(event)
            subscribers = list(self._subscribers.get(task_id, []))
            terminal = self._is_terminal_event(event)
            if terminal:
                self._subscribers.pop(task_id, None)

        for subscriber in subscribers:
            self._publish_to_subscriber(subscriber, event)
            if terminal:
                self._close_subscriber(subscriber)

    def _publish_to_subscriber(
        self,
        subscriber: _Subscriber,
        event: StreamResponse,
    ) -> None:
        subscriber.loop.call_soon_threadsafe(
            subscriber.queue.put_nowait,
            event.model_copy(deep=True),
        )

    def _close_subscriber(self, subscriber: _Subscriber) -> None:
        subscriber.loop.call_soon_threadsafe(subscriber.queue.put_nowait, None)

    def _is_terminal_event(self, response: StreamResponse) -> bool:
        if response.status_update is None:
            return False
        return response.status_update.status.state in TERMINAL_TASK_STATES
