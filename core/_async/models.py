from types import TracebackType
from typing import Any, AsyncIterator, Iterator, List, Optional, Tuple, Type, Union
from ..urls import RawURL


class AsyncByteStream:
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b""  # pragma: nocover

    async def aclose(self) -> None:
        pass  # pragma: nocover

    async def aread(self) -> bytes:
        return b"".join([part async for part in self])


class AsyncRawRequest:
    def __init__(
        self,
        method: bytes,
        url: RawURL,
        headers: List[Tuple[bytes, bytes]],
        stream: AsyncByteStream = None,
        extensions: dict = None,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.stream = AsyncByteStream() if stream is None else stream
        self.extensions = {} if extensions is None else extensions


class AsyncRawResponse:
    def __init__(
        self,
        status: int,
        headers: List[Tuple[bytes, bytes]],
        stream: AsyncByteStream = None,
        extensions: dict = None,
    ) -> None:
        self.status = status
        self.headers = headers
        self.stream = AsyncByteStream() if stream is None else stream
        self.extensions = {} if extensions is None else extensions

    async def __aenter__(self) -> "AsyncRawResponse":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self.stream.aclose()
