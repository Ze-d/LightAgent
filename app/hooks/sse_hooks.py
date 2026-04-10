import asyncio
from typing import Any
from app.core.hooks import BaseRunnerHooks
from app.core.event_channel import EventChannel
from app.obj.types import RunEndEvent, RunStartEvent, ToolCallEvent


class SSEHooks(BaseRunnerHooks):
    def __init__(self, channel: EventChannel, loop: asyncio.AbstractEventLoop):
        self.channel = channel
        self.loop = loop

    def _publish(self, event: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(self.channel.publish(event), self.loop)

    def on_tool_start(self, event: RunStartEvent):
        self._publish({
            "event": "tool_start",
            "data": event,
        })

    def on_tool_end(self, event: ToolCallEvent):
        event_name = "tool_success" if event["status"] == "success" else "tool_error"
        self._publish({
            "event": event_name,
            "data": event,
        })

    def on_run_end(self, event: RunEndEvent):
        self._publish({
            "event": "run_end",
            "data": event,
        })