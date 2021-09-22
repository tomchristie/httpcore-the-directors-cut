from .._exceptions import ProxyError
from .._models import enforce_headers, enforce_url, Origin, Request, Response, URL
from ..backends.base import NetworkBackend
from .._synchronization import Lock
from .connection_pool import ConnectionPool
from .connection import HTTPConnection
from .http11 import HTTP11Connection
from .interfaces import ConnectionInterface
import ssl
from typing import Dict, List, Tuple, Union


HeadersAsList = List[Tuple[Union[bytes, str], Union[bytes, str]]]
HeadersAsDict = Dict[Union[bytes, str], Union[bytes, str]]


def merge_headers(
    default_headers: List[Tuple[bytes, bytes]] = None,
    override_headers: List[Tuple[bytes, bytes]] = None,
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
        proxy_url: Union[URL, bytes, str, tuple],
        proxy_headers: Union[HeadersAsDict, HeadersAsList] = None,
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
            network_backend=network_backend,
        )
        self._ssl_context = ssl_context
        self._proxy_url = enforce_url(proxy_url, name="proxy_url")
        self._proxy_headers = enforce_headers(proxy_headers, name="proxy_headers")

    def create_connection(self, origin: Origin) -> ConnectionInterface:
        if origin.scheme == b"http":
            return ForwardHTTPConnection(
                proxy_origin=self._proxy_url.origin,
                keepalive_expiry=self._keepalive_expiry,
                network_backend=self._network_backend,
            )
        return TunnelHTTPConnection(
            proxy_origin=self._proxy_url.origin,
            remote_origin=origin,
            ssl_context=self._ssl_context,
            keepalive_expiry=self._keepalive_expiry,
            network_backend=self._network_backend,
        )


class ForwardHTTPConnection(ConnectionInterface):
    def __init__(
        self,
        proxy_origin: Origin,
        proxy_headers: Union[HeadersAsDict, HeadersAsList] = None,
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._connection = HTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend,
        )
        self._proxy_origin = proxy_origin
        self._proxy_headers = enforce_headers(proxy_headers, name="proxy_headers")

    def handle_request(self, request: Request) -> Response:
        headers = merge_headers(self._proxy_headers, request.headers)
        url = URL(
            scheme=self._proxy_origin.scheme,
            host=self._proxy_origin.host,
            port=self._proxy_origin.port,
            target=bytes(request.url),
        )
        proxy_request = Request(
            method=request.method,
            url=url,
            headers=headers,
            stream=request.stream,
            extensions=request.extensions,
        )
        return self._connection.handle_request(proxy_request)

    def can_handle_request(self, origin: Origin) -> bool:
        return origin.scheme == b"http"

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
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._connection = HTTPConnection(
            origin=proxy_origin,
            keepalive_expiry=keepalive_expiry,
            network_backend=network_backend,
        )
        self._proxy_origin = proxy_origin
        self._remote_origin = remote_origin
        self._ssl_context = ssl_context
        self._proxy_headers = [] if proxy_headers is None else proxy_headers
        self._keepalive_expiry = keepalive_expiry
        self._connect_lock = Lock()
        self._connected = False

    def handle_request(self, request: Request) -> Response:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("connect", None)

        with self._connect_lock:
            if not self._connected:
                target = b"%b:%d" % (self._remote_origin.host, self._remote_origin.port)

                connect_url = URL(
                    scheme=self._proxy_origin.scheme,
                    host=self._proxy_origin.host,
                    port=self._proxy_origin.port,
                    target=target,
                )
                connect_headers = [(b"Host", target), (b"Accept", b"*/*")]
                connect_request = Request(
                    method=b"CONNECT", url=connect_url, headers=connect_headers
                )
                connect_response = self._connection.handle_request(
                    connect_request
                )

                if connect_response.status < 200 or connect_response.status > 299:
                    reason_bytes = connect_response.extensions.get("reason_phrase", b"")
                    reason_str = reason_bytes.decode("ascii", errors="ignore")
                    msg = "%d %s" % (connect_response.status, reason_str)
                    self._connection.close()
                    raise ProxyError(msg)

                stream = connect_response.extensions["stream"]
                stream = stream.start_tls(
                    ssl_context=self._ssl_context,
                    server_hostname=self._remote_origin.host,
                    timeout=timeout,
                )
                self._connection = HTTP11Connection(
                    origin=self._remote_origin,
                    stream=stream,
                    keepalive_expiry=self._keepalive_expiry,
                )
                self._connected = True
        return self._connection.handle_request(request)

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._remote_origin

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
