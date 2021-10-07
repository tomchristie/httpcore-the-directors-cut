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
        if info == "client_addr":
            return self._sock.getsockname()
        if info == "server_addr":
            return self._sock.getpeername()
        return None


class SyncBackend(NetworkBackend):
    def connect(
        self, origin: Origin, timeout: float = None, local_address: str = None
    ) -> SyncStream:
        address = (origin.host.decode("ascii"), origin.port)
        source_address = None if local_address is None else (local_address, 0)
        exc_map = {socket.timeout: ConnectTimeout, socket.error: ConnectError}
        with map_exceptions(exc_map):
            sock = socket.create_connection(
                address, timeout, source_address=source_address
            )
        return SyncStream(sock)
