import ssl
from types import TracebackType
from typing import Optional, Type

from .._models import Origin, Request, Response
from ..backends.auto import AutoBackend
from ..backends.base import AsyncNetworkBackend
from .._exceptions import ConnectionNotAvailable
from .._ssl import default_ssl_context
from .._synchronization import AsyncLock
from .http11 import AsyncHTTP11Connection
from .interfaces import AsyncConnectionInterface


class AsyncHTTPConnection(AsyncConnectionInterface):
    def __init__(
        self,
        origin: Origin,
        ssl_context: ssl.SSLContext = None,
        keepalive_expiry: float = None,
        http2: bool = False,
        network_backend: AsyncNetworkBackend = None,
    ) -> None:
        ssl_context = default_ssl_context() if ssl_context is None else ssl_context
        alpn_protocols = ["http/1.1", "h2"] if http2 else ["http/1.1"]
        ssl_context.set_alpn_protocols(alpn_protocols)

        self._origin = origin
        self._ssl_context = ssl_context
        self._keepalive_expiry = keepalive_expiry
        self._http2 = http2
        self._network_backend: AsyncNetworkBackend = (
            AutoBackend() if network_backend is None else network_backend
        )
        self._connection: Optional[AsyncConnectionInterface] = None
        self._request_lock = AsyncLock()

    async def handle_async_request(self, request: Request) -> Response:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("connect", None)

        if not self.can_handle_request(request.url.origin):
            raise RuntimeError(
                f"Attempted to send request to {request.url.origin} on connection to {self._origin}"
            )

        async with self._request_lock:
            if self._connection is None:
                origin = self._origin
                stream = await self._network_backend.connect(
                    origin=origin, timeout=timeout
                )
                if origin.scheme == b"https":
                    stream = await stream.start_tls(
                        ssl_context=self._ssl_context,
                        server_hostname=origin.host,
                        timeout=timeout,
                    )

                ssl_object = stream.get_extra_info("ssl_object")
                if (
                    ssl_object is not None
                    and ssl_object.selected_alpn_protocol() == "h2"
                ):
                    from .http2 import AsyncHTTP2Connection

                    self._connection = AsyncHTTP2Connection(
                        origin=origin,
                        stream=stream,
                    )
                else:
                    self._connection = AsyncHTTP11Connection(
                        origin=origin,
                        stream=stream,
                        keepalive_expiry=self._keepalive_expiry,
                    )
            elif not self._connection.is_available():
                raise ConnectionNotAvailable()

        return await self._connection.handle_async_request(request)

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._origin

    async def attempt_aclose(self) -> bool:
        closed = False
        if self._connection is not None:
            closed = await self._connection.attempt_aclose()
        return closed

    async def aclose(self) -> None:
        if self._connection is not None:
            await self._connection.aclose()

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

    async def __aenter__(self) -> "AsyncHTTPConnection":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.aclose()
