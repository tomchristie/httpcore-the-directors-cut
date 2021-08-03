from ..backends.base import AsyncNetworkBackend
from ..synchronization import AsyncLock
from ..urls import Origin, RawURL
from .connection_pool import AsyncConnectionPool
from .connection import AsyncHTTPConnection
from .http11 import AsyncHTTP11Connection
from .interfaces import AsyncConnectionInterface
from .models import AsyncRawRequest, AsyncRawResponse
import ssl


class AsyncHTTPProxy(AsyncConnectionPool):
    def __init__(
        self,
        proxy_origin: Origin,
        ssl_context: ssl.SSLContext = None,
        max_connections: int = 10,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        network_backend: AsyncNetworkBackend = None,
    ) -> None:
        super().__init__(
            ssl_context=ssl_context,
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive_connections,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._ssl_context = ssl_context
        self._proxy_origin = proxy_origin

    def get_origin(self, request: AsyncRawRequest) -> Origin:
        if request.url.scheme == b'http':
            return self._proxy_origin
        return request.url.origin

    def create_connection(self, origin: Origin) -> AsyncConnectionInterface:
        if origin.scheme == b'http':
            return AsyncForwardHTTPConnection(
                proxy_origin=self._proxy_origin,
                keepalive_expiry=self._keepalive_expiry,
                network_backend=self._network_backend,
            )
        return AsyncTunnelHTTPConnection(
            proxy_origin=self._proxy_origin,
            remote_origin=origin,
            ssl_context=self._ssl_context,
            keepalive_expiry=self._keepalive_expiry,
            network_backend=self._network_backend,
        )


class AsyncForwardHTTPConnection(AsyncConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        keepalive_expiry: float = None,
        network_backend: AsyncNetworkBackend = None,
    ) -> None:
        self._connection = AsyncHTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._proxy_origin = proxy_origin

    async def handle_async_request(self, request: AsyncRawRequest) -> AsyncRawResponse:
        target = b''.join([
            request.url.scheme,
            b'://',
            request.url.host,
            b':',
            str(request.url.port).encode('ascii'),
            request.url.target
        ])
        proxy_url = RawURL(
            scheme=self._proxy_origin.scheme,
            host=self._proxy_origin.host,
            port=self._proxy_origin.port,
            target=target
        )
        proxy_request = AsyncRawRequest(
            method=request.method,
            url=proxy_url,
            headers=request.headers,
            stream=request.stream,
            extensions=request.extensions
        )
        return await self._connection.handle_async_request(proxy_request)

    async def aclose(self):
        await self._connection.aclose()

    async def attempt_aclose(self) -> bool:
        await self._connection.attempt_aclose()

    def info(self) -> str:
        return self._connection.info()

    def get_origin(self) -> Origin:
        return self._proxy_origin

    def is_available(self) -> bool:
        return self._connection.is_available()

    def has_expired(self) -> bool:
        return self._connection.has_expired()

    def is_idle(self) -> bool:
        return self._connection.is_idle()

    def is_closed(self) -> bool:
        return self._connection.is_closed()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.info()}]>"


class AsyncTunnelHTTPConnection(AsyncConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        remote_origin: Origin,
        ssl_context: ssl.SSLContext,
        keepalive_expiry: float = None,
        network_backend: AsyncNetworkBackend = None,
    ) -> None:
        self._connection = AsyncHTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._proxy_origin = proxy_origin
        self._remote_origin = remote_origin
        self._ssl_context = ssl_context
        self._keepalive_expiry = keepalive_expiry
        self._connect_lock = AsyncLock()
        self._connected = False

    async def handle_async_request(self, request: AsyncRawRequest) -> AsyncRawResponse:
        async with self._connect_lock:
            if not self._connected:
                target = b''.join([
                    self._remote_origin.host,
                    b':',
                    str(self._remote_origin.port).encode('ascii'),
                ])
                headers = [
                    (b"Host", target)
                ]
                proxy_url = RawURL(
                    scheme=self._proxy_origin.scheme,
                    host=self._proxy_origin.host,
                    port=self._proxy_origin.port,
                    target=target
                )
                proxy_request = AsyncRawRequest(
                    method="CONNECT",
                    url=proxy_url,
                    headers=headers
                )
                response = await self._connection.handle_async_request(proxy_request)
                stream = response.extensions["stream"]
                stream = await stream.start_tls(
                    ssl_context=self._ssl_context,
                    server_hostname=self._remote_origin.host
                )
                self._connection = AsyncHTTP11Connection(
                    origin=self._remote_origin,
                    stream=stream,
                    keepalive_expiry=self._keepalive_expiry,
                )
                self._connected = True
        return await self._connection.handle_async_request(request)

    async def aclose(self):
        await self._connection.aclose()

    async def attempt_aclose(self) -> bool:
        await self._connection.attempt_aclose()

    def info(self) -> str:
        return self._connection.info()

    def get_origin(self) -> Origin:
        return self._remote_origin

    def is_available(self) -> bool:
        return self._connection.is_available()

    def has_expired(self) -> bool:
        return self._connection.has_expired()

    def is_idle(self) -> bool:
        return self._connection.is_idle()

    def is_closed(self) -> bool:
        return self._connection.is_closed()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{self.info()}]>"
