from ..backends.base import AsyncNetworkBackend
from ..synchronization import AsyncLock
from ..urls import Origin, RawURL
from .connection_pool import AsyncConnectionPool
from .connection import AsyncHTTPConnection
from .http11 import AsyncHTTP11Connection
from .interfaces import AsyncConnectionInterface
from .models import AsyncRawRequest, AsyncRawResponse
import ssl
from typing import List, Tuple


def merge_headers(
    default_headers: List[Tuple[bytes, bytes]] = None,
    override_headers: List[Tuple[bytes, bytes]] = None
) -> List[Tuple[bytes, bytes]]:
    """
    Append default_headers and override_headers, de-duplicating if a key exists in both cases.
    """
    default_headers = [] if default_headers is None else default_headers
    override_headers = [] if override_headers is None else override_headers
    has_override = set([key.lower() for key, value in override_headers])
    default_headers = [
        (key, value)
        for key, value in default_headers
        if key.lower() not in has_override
    ]
    return default_headers + override_headers


class AsyncHTTPProxy(AsyncConnectionPool):
    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        proxy_mode: str = "DEFAULT",
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
        self._proxy_headers = proxy_headers
        self._forward_schemes = {
            "DEFAULT": (b'http',),
            "FORWARD_ONLY": (b'http', b'https'),
            "TUNNEL_ONLY": (),
        }[proxy_mode]
        self._tunnel_schemes = {
            "DEFAULT": (b'https',),
            "FORWARD_ONLY": (),
            "TUNNEL_ONLY": (b'http', b'https'),
        }[proxy_mode]

    def create_connection(self, origin: Origin) -> AsyncConnectionInterface:
        if origin.scheme in self._forward_schemes:
            return AsyncForwardHTTPConnection(
                proxy_origin=self._proxy_origin,
                supported_schemes=self._forward_schemes,
                keepalive_expiry=self._keepalive_expiry,
                network_backend=self._network_backend,
            )
        elif origin.scheme in self._tunnel_schemes:
            return AsyncTunnelHTTPConnection(
                proxy_origin=self._proxy_origin,
                remote_origin=origin,
                ssl_context=self._ssl_context,
                supported_schemes=self._tunnel_schemes,
                keepalive_expiry=self._keepalive_expiry,
                network_backend=self._network_backend,
            )
        raise UnsupportedProtocol(
            f"The request has an unsupported protocol '{origin.scheme}://'."
        )


class AsyncForwardHTTPConnection(AsyncConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        supported_schemes: Tuple[bytes] = (b"http",),
        keepalive_expiry: float = None,
        network_backend: AsyncNetworkBackend = None,
    ) -> None:
        self._connection = AsyncHTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._proxy_origin = proxy_origin
        self._proxy_headers = [] if proxy_headers is None else proxy_headers

    async def handle_async_request(self, request: AsyncRawRequest) -> AsyncRawResponse:
        target = b''.join([
            request.url.scheme,
            b'://',
            request.url.host,
            b':',
            str(request.url.port).encode('ascii'),
            request.url.target
        ])
        headers = merge_headers(self._proxy_headers, request.headers)
        url = RawURL(
            scheme=self._proxy_origin.scheme,
            host=self._proxy_origin.host,
            port=self._proxy_origin.port,
            target=target
        )
        proxy_request = AsyncRawRequest(
            method=request.method,
            url=url,
            headers=headers,
            stream=request.stream,
            extensions=request.extensions
        )
        return await self._connection.handle_async_request(proxy_request)

    def can_handle_request(self, origin: Origin) -> bool:
        return origin.scheme in self._supported_schemes

    async def aclose(self):
        await self._connection.aclose()

    async def attempt_aclose(self) -> bool:
        await self._connection.attempt_aclose()

    def info(self) -> str:
        return self._connection.info()

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
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        supported_schemes: Tuple[bytes] = (b"https",),
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
        self._proxy_headers = [] if proxy_headers is None else proxy_headers
        self._keepalive_expiry = keepalive_expiry
        self._connect_lock = AsyncLock()
        self._connected = False

    async def handle_async_request(self, request: AsyncRawRequest) -> AsyncRawResponse:
        async with self._connect_lock:
            if not self._connected:
                target = b"%b:%d" % (self._remote_origin.host, self._remote_origin.port)

                connect_url = RawURL(
                    scheme=self._proxy_origin.scheme,
                    host=self._proxy_origin.host,
                    port=self._proxy_origin.port,
                    target=target
                )
                connect_headers = [(b"Host", target), (b"Accept", b"*/*")]
                connect_request = AsyncRawRequest(
                    method=b"CONNECT",
                    url=connect_url,
                    headers=connect_headers
                )
                response = await self._connection.handle_async_request(connect_request)
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

    def can_handle_request(self, origin: Origin) -> bool:
        return origin.scheme == self._remote_origin

    async def aclose(self):
        await self._connection.aclose()

    async def attempt_aclose(self) -> bool:
        await self._connection.attempt_aclose()

    def info(self) -> str:
        return self._connection.info()

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
