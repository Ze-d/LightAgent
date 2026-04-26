from abc import ABC, abstractmethod
from typing import Any


class BaseTransport(ABC):
    @abstractmethod
    def connect(self) -> None:
        pass

    @abstractmethod
    async def send_request(self, request: dict[str, Any], timeout: float) -> dict[str, Any]:
        pass

    @abstractmethod
    def close(self) -> None:
        pass
