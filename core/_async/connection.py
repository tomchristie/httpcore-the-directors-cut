from ..backends.base import NetworkBackend
from ..backends.trio import TrioBackend
from ..base import ConnectionNotAvailable, Origin
from ..synchronization import Lock
from .http11 import AsyncHTTP11Connection
from .interfaces import (
    AsyncByteStream,
    AsyncConnectionInterface,
    RawRequest,
    RawResponse,
)
from typing import AsyncIterator, List, Optional, Type
from types import TracebackType
import enum
import time


class AsyncHTTPConnection(AsyncConnectionInterface):
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
        self._connection: Optional[AsyncConnectionInterface] = None
        self._request_lock = Lock()

    async def handle_async_request(self, request: RawRequest) -> RawResponse:
        async with self._request_lock:
            if self._connection is None:
                origin = self._origin
                stream = await self._network_backend.connect(origin=origin)
                self._connection = AsyncHTTP11Connection(
                    origin=origin,
                    stream=stream,
                    keepalive_expiry=self._keepalive_expiry,
                )
            elif not self._connection.is_available():
                raise ConnectionNotAvailable()

        return await self._connection.handle_async_request(request)

    async def attempt_close(self) -> bool:
        if self._connection is None:
            return False
        return await self._connection.attempt_close()

    async def aclose(self) -> None:
        if self._connection is not None:
            await self._connection.aclose()

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

    def info(self) -> str:
        if self._connection is None:
            return "CONNECTING"
        return self._connection.info()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.info()}]>"

    # These context managers are not used in the standard flow, but are
    # useful for testing or working with connection instances directly.

    async def __aenter__(self) -> "AsyncHTTP11Connection":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.aclose()
