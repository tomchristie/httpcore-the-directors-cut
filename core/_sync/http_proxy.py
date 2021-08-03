from ..backends.base import NetworkBackend
from ..synchronization import Lock
from ..urls import Origin, RawURL
from .connection_pool import ConnectionPool
from .connection import HTTPConnection
from .http11 import HTTP11Connection
from .interfaces import ConnectionInterface
from .models import RawRequest, RawResponse
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


class HTTPProxy(ConnectionPool):
    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        proxy_mode: str = "DEFAULT",
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

    def create_connection(self, origin: Origin) -> ConnectionInterface:
        if origin.scheme in self._forward_schemes:
            return ForwardHTTPConnection(
                proxy_origin=self._proxy_origin,
                supported_schemes=self._forward_schemes,
                keepalive_expiry=self._keepalive_expiry,
                network_backend=self._network_backend,
            )
        elif origin.scheme in self._tunnel_schemes:
            return TunnelHTTPConnection(
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


class ForwardHTTPConnection(ConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        supported_schemes: Tuple[bytes] = (b"http",),
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._connection = HTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend
        )
        self._proxy_origin = proxy_origin
        self._proxy_headers = [] if proxy_headers is None else proxy_headers

    def handle_request(self, request: RawRequest) -> RawResponse:
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
        proxy_request = RawRequest(
            method=request.method,
            url=url,
            headers=headers,
            stream=request.stream,
            extensions=request.extensions
        )
        return self._connection.handle_request(proxy_request)

    def can_handle_request(self, origin: Origin) -> bool:
        return origin.scheme in self._supported_schemes

    def close(self):
        self._connection.close()

    def attempt_aclose(self) -> bool:
        self._connection.attempt_aclose()

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


class TunnelHTTPConnection(ConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        remote_origin: Origin,
        ssl_context: ssl.SSLContext,
        proxy_headers: List[Tuple[bytes, bytes]] = None,
        supported_schemes: Tuple[bytes] = (b"https",),
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
        self._proxy_headers = [] if proxy_headers is None else proxy_headers
        self._keepalive_expiry = keepalive_expiry
        self._connect_lock = Lock()
        self._connected = False

    def handle_request(self, request: RawRequest) -> RawResponse:
        with self._connect_lock:
            if not self._connected:
                target = b"%b:%d" % (self._remote_origin.host, self._remote_origin.port)

                connect_url = RawURL(
                    scheme=self._proxy_origin.scheme,
                    host=self._proxy_origin.host,
                    port=self._proxy_origin.port,
                    target=target
                )
                connect_headers = [(b"Host", target), (b"Accept", b"*/*")]
                connect_request = RawRequest(
                    method=b"CONNECT",
                    url=connect_url,
                    headers=connect_headers
                )
                response = self._connection.handle_request(connect_request)
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

    def can_handle_request(self, origin: Origin) -> bool:
        return origin.scheme == self._remote_origin

    def close(self):
        self._connection.close()

    def attempt_aclose(self) -> bool:
        self._connection.attempt_aclose()

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
