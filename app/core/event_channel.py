import asyncio
from collections.abc import AsyncIterator
from typing import Any


class EventChannel:
    def __init__(self):
        self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def publish(self, event: dict[str, Any]) -> None:
        await self._queue.put(event)

    async def close(self) -> None:
        await self._queue.put({"event": "__close__", "data": {}})

    async def stream(self) -> AsyncIterator[dict[str, Any]]:
        while True:
            item = await self._queue.get()
            if item["event"] == "__close__":
                break
            yield item