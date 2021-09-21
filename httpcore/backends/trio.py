import ssl
import trio
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
from .._models import Origin


class TrioStream(AsyncNetworkStream):
    def __init__(self, stream: trio.abc.Stream) -> None:
        self._stream = stream

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        timeout_or_inf = float("inf") if timeout is None else timeout
        exc_map = {trio.TooSlowError: ReadTimeout, trio.BrokenResourceError: ReadError}
        with map_exceptions(exc_map):
            with trio.fail_after(timeout_or_inf):
                return await self._stream.receive_some(max_bytes=max_bytes)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        if not buffer:
            return

        timeout_or_inf = float("inf") if timeout is None else timeout
        exc_map = {
            trio.TooSlowError: WriteTimeout,
            trio.BrokenResourceError: WriteError,
        }
        with map_exceptions(exc_map):
            with trio.fail_after(timeout_or_inf):
                return await self._stream.send_all(data=buffer)

    async def aclose(self) -> None:
        await self._stream.aclose()

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> AsyncNetworkStream:
        timeout_or_inf = float("inf") if timeout is None else timeout
        exc_map = {
            trio.TooSlowError: ConnectTimeout,
            trio.BrokenResourceError: ConnectError,
        }
        ssl_stream = trio.SSLStream(
            self._stream,
            ssl_context=ssl_context,
            server_hostname=server_hostname.decode("ascii"),
            https_compatible=True,
            server_side=False,
        )
        with map_exceptions(exc_map):
            with trio.fail_after(timeout_or_inf):
                await ssl_stream.do_handshake()
        return TrioStream(ssl_stream)

    def get_extra_info(self, info: str) -> typing.Any:
        if info == "ssl_object" and isinstance(self._stream, trio.SSLStream):
            return self._stream._ssl_object
        if info == "client_addr":
            return self._get_socket_stream().socket.getsockname()
        if info == "server_addr":
            return self._get_socket_stream().socket.getpeername()
        return None

    def _get_socket_stream(self) -> trio.SocketStream:
        stream = self._stream
        while isinstance(stream, trio.SSLStream):
            stream = stream.transport_stream
        assert isinstance(stream, trio.SocketStream)
        return stream


class TrioBackend(AsyncNetworkBackend):
    async def connect(
        self, origin: Origin, timeout: float = None
    ) -> AsyncNetworkStream:
        timeout_or_inf = float("inf") if timeout is None else timeout
        exc_map = {
            trio.TooSlowError: ConnectTimeout,
            trio.BrokenResourceError: ConnectError,
        }
        with map_exceptions(exc_map):
            with trio.fail_after(timeout_or_inf):
                trio_stream: trio.abc.Stream = await trio.open_tcp_stream(
                    host=origin.host, port=origin.port
                )
        return TrioStream(trio_stream)
