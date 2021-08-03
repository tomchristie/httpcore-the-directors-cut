from ..backends.base import NetworkBackend
from ..synchronization import Lock
from ..urls import Origin, RawURL
from .connection_pool import ConnectionPool
from .connection import HTTPConnection
from .http11 import HTTP11Connection
from .interfaces import ConnectionInterface
from .models import RawRequest, RawResponse
import ssl


class HTTPProxy(ConnectionPool):
    def __init__(
        self,
        proxy_origin: Origin,
        ssl_context: ssl.SSLContext = None,
        max_connections: int = 10,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
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

    def get_origin(self, request: RawRequest) -> Origin:
        if request.url.scheme == b'http':
            return self._proxy_origin
        return request.url.origin

    def create_connection(self, origin: Origin) -> ConnectionInterface:
        if origin.scheme == b'http':
            return ForwardHTTPConnection(
                proxy_origin=self._proxy_origin,
                keepalive_expiry=self._keepalive_expiry,
                network_backend=self._network_backend,
            )
        return TunnelHTTPConnection(
            proxy_origin=self._proxy_origin,
            remote_origin=origin,
            ssl_context=self._ssl_context,
            keepalive_expiry=self._keepalive_expiry,
            network_backend=self._network_backend,
        )


class ForwardHTTPConnection(ConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._connection = HTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._proxy_origin = proxy_origin

    def handle_request(self, request: RawRequest) -> RawResponse:
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
        proxy_request = RawRequest(
            method=request.method,
            url=proxy_url,
            headers=request.headers,
            stream=request.stream,
            extensions=request.extensions
        )
        return self._connection.handle_request(proxy_request)

    def close(self):
        self._connection.close()

    def attempt_aclose(self) -> bool:
        self._connection.attempt_aclose()

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


class TunnelHTTPConnection(ConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        remote_origin: Origin,
        ssl_context: ssl.SSLContext,
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._connection = HTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._proxy_origin = proxy_origin
        self._remote_origin = remote_origin
        self._ssl_context = ssl_context
        self._keepalive_expiry = keepalive_expiry
        self._connect_lock = Lock()
        self._connected = False

    def handle_request(self, request: RawRequest) -> RawResponse:
        with self._connect_lock:
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
                proxy_request = RawRequest(
                    method="CONNECT",
                    url=proxy_url,
                    headers=headers
                )
                response = self._connection.handle_request(proxy_request)
                stream = response.extensions["stream"]
                stream = stream.start_tls(
                    ssl_context=self._ssl_context,
                    server_hostname=self._remote_origin.host
                )
                self._connection = HTTP11Connection(
                    origin=self._remote_origin,
                    stream=stream,
                    keepalive_expiry=self._keepalive_expiry,
                )
                self._connected = True
        return self._connection.handle_request(request)

    def close(self):
        self._connection.close()

    def attempt_aclose(self) -> bool:
        self._connection.attempt_aclose()

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
