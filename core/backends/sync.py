import socket
from .base import NetworkStream, NetworkBackend
from ..base import Origin


class SyncStream(NetworkStream):
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def read(self, max_bytes: int, timeout: float = None) -> bytes:
        return self._sock.recv(max_bytes)

    def write(self, buffer: bytes, timeout: float = None) -> None:
        while buffer:
            n = self._sock.send(data)
            buffer = buffer[n:]

    def close(self) -> None:
        self._sock.close()


class SyncBackend(NetworkBackend):
    def connect(self, origin: Origin) -> NetworkStream:
        address = (origin.host.decode("ascii"), origin.port)
        sock = socket.create_connection(address)
        return SyncStream(sock)
