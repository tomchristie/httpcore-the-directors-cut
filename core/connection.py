from .base import (
    ByteStream,
    ConnectionInterface,
    ConnectionNotAvailable,
    Origin,
    RawRequest,
    RawResponse,
)
from .http11 import HTTP11Connection
from .network import NetworkStream
from .synchronization import Lock
from typing import AsyncIterator, List
import enum
import time


class MockNetworkStream(NetworkStream):
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


class HTTPConnection(ConnectionInterface):
    def __init__(self, origin: Origin, keepalive_expiry: float = None, buffer: List[bytes] = None) -> None:
        if buffer is None:
            buffer = [
                b"HTTP/1.1 200 OK\r\n",
                b"Content-Type: plain/text\r\n",
                b"Content-Length: 13\r\n",
                b"\r\n",
                b"Hello, world!",
            ]
        stream = MockNetworkStream(buffer=buffer)
        self._connection: ConnectionInterface = HTTP11Connection(
            origin=origin,
            stream=stream,
            keepalive_expiry=keepalive_expiry
        )

    async def handle_request(self, request: RawRequest) -> RawResponse:
        return await self._connection.handle_request(request)

    async def attempt_close(self) -> bool:
        return await self._connection.attempt_close()

    async def aclose(self) -> None:
        await self._connection.aclose()

    def info(self) -> str:
        return self._connection.info()

    def get_origin(self) -> Origin:
        return self._connection.get_origin()

    def is_available(self) -> bool:
        return self._connection.is_available()

    def has_expired(self) -> bool:
        return self._connection.has_expired()

    def is_idle(self) -> bool:
        return self._connection.is_idle()

    def is_closed(self) -> bool:
        return self._connection.is_closed()
