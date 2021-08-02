from types import TracebackType
from typing import Any, Iterator, Iterator, List, Optional, Tuple, Type, Union
from ..urls import RawURL


class ByteStream:
    def __iter__(self) -> Iterator[bytes]:
        yield b""  # pragma: nocover

    def close(self) -> None:
        pass  # pragma: nocover

    def read(self) -> bytes:
        return b"".join([part for part in self])


class RawRequest:
    def __init__(
        self,
        method: bytes,
        url: RawURL,
        headers: List[Tuple[bytes, bytes]],
        stream: ByteStream = None,
        extensions: dict = None,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.stream = ByteStream() if stream is None else stream
        self.extensions = {} if extensions is None else extensions


class RawResponse:
    def __init__(
        self,
        status: int,
        headers: List[Tuple[bytes, bytes]],
        stream: ByteStream = None,
        extensions: dict = None,
    ) -> None:
        self.status = status
        self.headers = headers
        self.stream = ByteStream() if stream is None else stream
        self.extensions = {} if extensions is None else extensions

    def __enter__(self) -> "RawResponse":
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self.stream.close()
