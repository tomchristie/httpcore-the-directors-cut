from .base import AsyncNetworkStream, AsyncNetworkBackend, NetworkStream, NetworkBackend
from .._models import Origin
import typing
import ssl


class MockSSLObject:
    def __init__(self, http2: bool):
        self._http2 = http2

    def selected_alpn_protocol(self) -> str:
        return "h2" if self._http2 else "http/1.1"


class MockStream(NetworkStream):
    def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
        self._original_buffer = buffer
        self._current_buffer = list(self._original_buffer)
        self._http2 = http2

    def read(self, max_bytes: int, timeout: float = None) -> bytes:
        if not self._current_buffer:
            self._current_buffer = list(self._original_buffer)
        return self._current_buffer.pop(0)

    def write(self, buffer: bytes, timeout: float = None) -> None:
        pass

    def close(self) -> None:
        pass

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> NetworkStream:
        return self

    def get_extra_info(self, info: str) -> typing.Any:
        return MockSSLObject(http2=self._http2) if info == "ssl_object" else None


class MockBackend(NetworkBackend):
    def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
        self._buffer = buffer
        self._http2 = http2

    def connect(self, origin: Origin, timeout: float = None) -> NetworkStream:
        return MockStream(self._buffer, http2=self._http2)


class AsyncMockStream(AsyncNetworkStream):
    def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
        self._original_buffer = buffer
        self._current_buffer = list(self._original_buffer)
        self._http2 = http2

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        if not self._current_buffer:
            self._current_buffer = list(self._original_buffer)
        return self._current_buffer.pop(0)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        pass

    async def aclose(self) -> None:
        pass

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> AsyncNetworkStream:
        return self

    def get_extra_info(self, info: str) -> typing.Any:
        return MockSSLObject(http2=self._http2) if info == "ssl_object" else None


class AsyncMockBackend(AsyncNetworkBackend):
    def __init__(self, buffer: typing.List[bytes], http2: bool = False) -> None:
        self._buffer = buffer
        self._http2 = http2

    async def connect(
        self, origin: Origin, timeout: float = None
    ) -> AsyncNetworkStream:
        return AsyncMockStream(self._buffer, http2=self._http2)
