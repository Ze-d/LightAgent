import json
from collections.abc import AsyncIterable, Iterable
from typing import Any

from starlette.responses import StreamingResponse


try:
    from fastapi.sse import EventSourceResponse as EventSourceResponse
except ModuleNotFoundError:
    try:
        from sse_starlette.sse import EventSourceResponse as EventSourceResponse
    except ModuleNotFoundError:

        class EventSourceResponse(StreamingResponse):
            """Small EventSourceResponse fallback for test/dev environments."""

            media_type = "text/event-stream"

            def __init__(self, content: AsyncIterable | Iterable, **kwargs: Any):
                super().__init__(
                    self._stream(content),
                    media_type=self.media_type,
                    headers={"Cache-Control": "no-cache"},
                    **kwargs,
                )

            async def _stream(self, content: AsyncIterable | Iterable):
                if hasattr(content, "__aiter__"):
                    async for item in content:
                        yield self._format_event(item)
                    return

                for item in content:
                    yield self._format_event(item)

            def _format_event(self, item: Any) -> bytes:
                if not isinstance(item, dict):
                    data = str(item)
                    return f"data: {data}\n\n".encode("utf-8")

                event = item.get("event")
                data = item.get("data", "")
                if not isinstance(data, str):
                    data = json.dumps(data, ensure_ascii=False, default=str)

                lines: list[str] = []
                if event:
                    lines.append(f"event: {event}")
                for line in data.splitlines() or [""]:
                    lines.append(f"data: {line}")
                lines.append("")
                lines.append("")
                return "\n".join(lines).encode("utf-8")
