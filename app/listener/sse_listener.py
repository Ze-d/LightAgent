import asyncio
from typing import Any
from app.obj.types import ToolCallEvent
from app.core.event_channel import EventChannel


def make_tool_event_listener(channel: EventChannel):
    def listener(event: ToolCallEvent) -> None:
        mapped_event: dict[str, Any] = {
            "event": {
                "start": "tool_start",
                "success": "tool_success",
                "error": "tool_error",
            }[event["status"]],
            "data": event,
        }
        asyncio.create_task(channel.publish(mapped_event))
    return listener
# 这版是“教学型最小方案”。
# 如果你后面把 Runner 放在线程池里，asyncio.create_task() 这套就要换成更稳的线程安全桥接方式。
# 但现在先把架构通了最重要。