from .backends.base import NetworkBackend
from .backends.trio import TrioBackend
from .base import (
    ByteStream,
    ConnectionInterface,
    ConnectionNotAvailable,
    Origin,
    RawRequest,
    RawResponse,
)
from .http11 import HTTP11Connection
from .synchronization import Lock
from typing import AsyncIterator, List, Optional
import enum
import time


class HTTPConnection(ConnectionInterface):
    def __init__(
        self,
        origin: Origin,
        keepalive_expiry: float = None,
        buffer: List[bytes] = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._origin = origin
        self._keepalive_expiry = keepalive_expiry
        self._network_backend: NetworkBackend = (
            TrioBackend() if network_backend is None else network_backend
        )
        self._connection: Optional[ConnectionInterface] = None

    async def handle_request(self, request: RawRequest) -> RawResponse:
        if self._connection is None:
            origin = self._origin
            stream = await self._network_backend.connect(origin=origin)
            self._connection = HTTP11Connection(
                origin=origin, stream=stream, keepalive_expiry=self._keepalive_expiry
            )
        return await self._connection.handle_request(request)

    async def attempt_close(self) -> bool:
        if self._connection is None:
            return False
        return await self._connection.attempt_close()

    async def aclose(self) -> None:
        if self._connection is not None:
            await self._connection.aclose()

    def info(self) -> str:
        if self._connection is None:
            return 'Opening connection'
        return self._connection.info()

    def get_origin(self) -> Origin:
        return self._origin

    def is_available(self) -> bool:
        if self._connection is None:
            return True
        return self._connection.is_available()

    def has_expired(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.has_expired()

    def is_idle(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.is_idle()

    def is_closed(self) -> bool:
        if self._connection is None:
            return False
        return self._connection.is_closed()
