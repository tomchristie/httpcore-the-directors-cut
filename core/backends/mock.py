from .base import AsyncNetworkStream, AsyncNetworkBackend
from ..base import Origin
from typing import List


class AsyncMockStream(AsyncNetworkStream):
    def __init__(self, buffer: List[bytes]) -> None:
        self._original_buffer = buffer
        self._current_buffer = list(self._original_buffer)

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        if not self._current_buffer:
            self._current_buffer = list(self._original_buffer)
        return self._current_buffer.pop(0)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        pass

    async def aclose(self) -> None:
        pass


class AsyncMockBackend(AsyncNetworkBackend):
    def __init__(self, buffer: List[bytes]) -> None:
        self._buffer = buffer

    async def connect(self, origin: Origin) -> None:
        return AsyncMockStream(self._buffer)
