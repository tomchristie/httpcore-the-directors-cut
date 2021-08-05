import ssl
import trio
from .base import AsyncNetworkStream, AsyncNetworkBackend
from .._ssl import default_ssl_context
from .._models import Origin


class TrioStream(AsyncNetworkStream):
    def __init__(self, stream: trio.abc.Stream) -> None:
        self._stream = stream

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        return await self._stream.receive_some(max_bytes=max_bytes)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        return await self._stream.send_all(data=buffer)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self, ssl_context: ssl.SSLContext, server_hostname: bytes = None
    ) -> AsyncNetworkStream:
        trio_ssl_stream = trio.SSLStream(
            self._stream, ssl_context, server_hostname=server_hostname.decode("ascii")
        )
        await trio_ssl_stream.do_handshake()
        return TrioStream(trio_ssl_stream)


class TrioBackend(AsyncNetworkBackend):
    def __init__(self, ssl_context: ssl.SSLContext = None) -> None:
        self._ssl_context = default_ssl_context() if ssl_context is None else ssl_context

    async def connect(self, origin: Origin) -> AsyncNetworkStream:
        trio_stream: trio.abc.Stream = await trio.open_tcp_stream(
            host=origin.host, port=origin.port
        )
        stream = TrioStream(trio_stream)
        if origin.scheme == b"https":
            stream = await stream.start_tls(
                self._ssl_context, server_hostname=origin.host
            )
        return stream
