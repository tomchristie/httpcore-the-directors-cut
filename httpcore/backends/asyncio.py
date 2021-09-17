import anyio
import ssl
import typing
from .base import AsyncNetworkStream, AsyncNetworkBackend
from .._exceptions import (
    ConnectError,
    ConnectTimeout,
    ReadError,
    ReadTimeout,
    WriteError,
    WriteTimeout,
    map_exceptions,
)
from .._ssl import default_ssl_context
from .._models import Origin


class AsyncIOStream(AsyncNetworkStream):
    def __init__(self, stream: anyio.abc.ByteStream) -> None:
        self._stream = stream

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        exc_map = {
            TimeoutError: ReadTimeout,
            anyio.BrokenResourceError: ReadError,
        }
        with map_exceptions(exc_map):
            with anyio.fail_after(timeout):
                return await self._stream.receive(max_bytes=max_bytes)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        if not buffer:
            return

        exc_map = {
            TimeoutError: WriteTimeout,
            anyio.BrokenResourceError: WriteError,
        }
        with map_exceptions(exc_map):
            with anyio.fail_after(timeout):
                return await self._stream.send(item=buffer)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> AsyncNetworkStream:
        exc_map = {
            TimeoutError: ConnectTimeout,
            anyio.BrokenResourceError: ConnectError,
        }
        with map_exceptions(exc_map):
            with anyio.fail_after(timeout):
                ssl_stream = await anyio.streams.tls.TLSStream.wrap(
                    self._stream,
                    ssl_context=ssl_context,
                    hostname=server_hostname.decode("ascii"),
                    standard_compatible=False,
                    server_side=False,
                )
        return AsyncIOStream(ssl_stream)

    def get_extra_info(self, info: str) -> typing.Any:
        if info == "ssl_object":
            return self._stream.extra(anyio.streams.tls.TLSAttribute.ssl_object, None)
        return None


class AsyncIOBackend(AsyncNetworkBackend):
    def __init__(self, ssl_context: ssl.SSLContext = None) -> None:
        self._ssl_context = (
            default_ssl_context() if ssl_context is None else ssl_context
        )

    async def connect(
        self, origin: Origin, timeout: float = None
    ) -> AsyncNetworkStream:
        exc_map = {
            TimeoutError: ConnectTimeout,
            anyio.BrokenResourceError: ConnectError,
        }
        with map_exceptions(exc_map):
            with anyio.fail_after(timeout):
                anyio_stream: anyio.abc.ByteStream = await anyio.connect_tcp(
                    remote_host=origin.host.decode("ascii"), remote_port=origin.port
                )
        stream = AsyncIOStream(anyio_stream)
        if origin.scheme == b"https":
            stream = await stream.start_tls(
                self._ssl_context, server_hostname=origin.host, timeout=timeout
            )
        return stream
