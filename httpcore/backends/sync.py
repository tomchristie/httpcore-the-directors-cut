from .base import NetworkStream, NetworkBackend
from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._models import Origin
from .._ssl import default_ssl_context
import socket
import ssl
import typing


class SyncStream(NetworkStream):
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def read(self, max_bytes: int, timeout: float = None) -> bytes:
        exc_map = {socket.timeout: ReadTimeout, socket.error: ReadError}
        with map_exceptions(exc_map):
            self._sock.settimeout(timeout)
            return self._sock.recv(max_bytes)

    def write(self, buffer: bytes, timeout: float = None) -> None:
        if not buffer:
            return

        exc_map = {socket.timeout: WriteTimeout, socket.error: WriteError}
        with map_exceptions(exc_map):
            while buffer:
                self._sock.settimeout(timeout)
                n = self._sock.send(buffer)
                buffer = buffer[n:]

    def close(self) -> None:
        self._sock.close()

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> NetworkStream:
        exc_map = {socket.timeout: ConnectTimeout, socket.error: ConnectError}
        with map_exceptions(exc_map):
            self._sock.settimeout(timeout)
            sock = ssl_context.wrap_socket(
                self._sock, server_hostname=server_hostname.decode("ascii")
            )
        return SyncStream(sock)

    def get_extra_info(self, info: str) -> typing.Any:
        if info == "ssl_object" and isinstance(self._sock, ssl.SSLSocket):
            return self._sock._sslobj
        if info == "local_addr":
            return self._sock.getsockname()
        if info == "remote_addr":
            return self._sock.getpeername()
        return None


class SyncBackend(NetworkBackend):
    def __init__(self, ssl_context: ssl.SSLContext = None) -> None:
        self._ssl_context = (
            default_ssl_context() if ssl_context is None else ssl_context
        )

    def connect(self, origin: Origin, timeout: float = None) -> SyncStream:
        address = (origin.host.decode("ascii"), origin.port)
        exc_map = {socket.timeout: ConnectTimeout, socket.error: ConnectError}
        with map_exceptions(exc_map):
            sock = socket.create_connection(address, timeout)

        stream = SyncStream(sock)
        if origin.scheme == b"https":
            stream = stream.start_tls(self._ssl_context, server_hostname=origin.host)
        return stream
