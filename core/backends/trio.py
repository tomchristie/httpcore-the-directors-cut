import trio
from .base import NetworkStream, NetworkBackend
from ..base import Origin


class TrioStream(NetworkStream):
    def __init__(self, stream: trio.abc.Stream) -> None:
        self._stream = stream

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        return await self._stream.receive_some(max_bytes=max_bytes)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        return await self._stream.send_all(data=buffer)

    async def aclose(self) -> None:
        await self._stream.aclose()


class TrioBackend(NetworkBackend):
    async def connect(self, origin: Origin) -> NetworkStream:
        stream: trio.abc.Stream = await trio.open_tcp_stream(
            host=origin.host, port=origin.port
        )
        return TrioStream(stream)
