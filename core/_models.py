from types import TracebackType
from typing import Any, AsyncIterator, Iterator, List, Optional, Tuple, Type, Union
from urllib.parse import urlparse

__all__ = [
    "SyncByteStream",
    "AsyncByteStream",
    "ByteStream",
    "Origin",
    "URL",
    "Request",
    "Response",
]


def enforce_bytes(bytes_or_str: Union[bytes, str], *, name: str) -> bytes:
    """
    Any arguments that are ultimately represented as bytes can be specified
    either as bytes or as strings.

    However we enforce that any string arguments must only contain characters in
    the plain ASCII range. chr(0)...chr(127). If you need to use characters
    outside that range then be precise, and use a byte-wise argument.
    """
    if isinstance(bytes_or_str, str):
        try:
            return bytes_or_str.encode("ascii")
        except UnicodeEncodeError:
            raise RuntimeError(
                f"{name} must either be a plain ascii string, or specified as bytes."
            )
    return bytes_or_str


def enforce_headers_as_bytes(
    headers: List[Tuple[Union[bytes, str], Union[bytes, str]]]
) -> List[Tuple[bytes, bytes]]:
    """
    Convienence function that ensure all items in request or response headers
    are either bytes or strings in the plain ASCII range.
    """
    return [
        (
            enforce_bytes(k, name="header name"),
            enforce_bytes(v, name="header value"),
        )
        for k, v in headers
    ]


class SyncByteStream:
    def __iter__(self) -> Iterator[bytes]:  # pragma: nocover
        raise NotImplementedError("The '__iter__' method must be implemented.")
        yield b""

    def close(self) -> None:
        pass  # pragma: nocover


class AsyncByteStream:
    async def __aiter__(self) -> AsyncIterator[bytes]:  # pragma: nocover
        raise NotImplementedError("The '__aiter__' method must be implemented.")
        yield b""

    async def aclose(self) -> None:
        pass  # pragma: nocover


class ByteStream(SyncByteStream, AsyncByteStream):
    """
    A concrete implementation of a byte stream, that can be used for
    non-streaming content, and that supports both sync and async styles.
    """

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __iter__(self) -> Iterator[bytes]:
        yield self._content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} [{len(self._content)} bytes]>"


class Origin:
    def __init__(self, scheme: bytes, host: bytes, port: int) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Origin)
            and self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __str__(self) -> str:
        scheme = self.scheme.decode("ascii")
        host = self.host.decode("ascii")
        port = str(self.port)
        return f"{scheme}://{host}:{port}"


class URL:
    """
    Represents the URL against which an HTTP request may be made.

    The URL may either be specified as a plain string, for convienence:

    >>> url = httpcore.URL("https://www.example.com/")

    Or be constructed with explicitily pre-parsed components:

    >>> url = httpcore.URL(scheme=b'https', host=b'www.example.com', port=None, target=b'/')

    The four components are important here, as they allow the URL to be precisely specified
    in a pre-parsed format. They also allow certain types of request to be created that
    could not otherwise be expressed.

    For example, an HTTP request to 'http://www.example.com/' made via a proxy
    at http://localhost:8080...

    >>> url = httpcore.URL(
        scheme=b'http',
        host=b'localhost',
        port=8080,
        target=b'http://www.example.com/'
    )
    >>> request = httpcore.Request(
        method="GET",
        url=url
    )

    GET http://www.example.com/ HTTP/1.1

    Another example is constructing an 'OPTIONS *' request...

    >>> url = httpcore.URL(scheme=b'http', host=b'www.example.com', target=b'*')
    >>> request = httpcore.Request(method="OPTIONS", url=url)

    OPTIONS * HTTP/1.1
    """

    def __init__(
        self,
        url: Union[bytes, str] = "",
        *,
        scheme: Union[bytes, str] = b"",
        host: Union[bytes, str] = b"",
        port: Optional[int] = None,
        target: Union[bytes, str] = b"",
    ) -> None:
        if url:
            parsed = urlparse(enforce_bytes(url, name="url"))
            self.scheme = parsed.scheme
            self.host = parsed.hostname or b""
            self.port = parsed.port
            self.target = (parsed.path or b"/") + (
                b"?" + parsed.query if parsed.query else b""
            )
        else:
            self.scheme = enforce_bytes(scheme, name="scheme")
            self.host = enforce_bytes(host, name="host")
            self.port = port
            self.target = enforce_bytes(target, name="target")

    @property
    def origin(self) -> Origin:
        return Origin(scheme=self.scheme, host=self.host, port=self.port)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, URL)
            and other.scheme == self.scheme
            and other.host == self.host
            and other.port == self.port
            and other.target == self.target
        )

    def __bytes__(self) -> bytes:
        if self.port is None:
            return b"%b://%b%b" % (self.scheme, self.host, self.target)
        return b"%b://%b:%d%b" % (self.scheme, self.host, self.port, self.target)


class Request:
    def __init__(
        self,
        method: Union[bytes, str],
        url: URL,
        *,
        headers: List[Tuple[Union[bytes, str], Union[bytes, str]]] = None,
        stream: Union[SyncByteStream, AsyncByteStream] = None,
        extensions: dict = None,
    ) -> None:
        self.method = enforce_bytes(method, name="method")
        self.url = url
        self.headers = [] if headers is None else enforce_headers_as_bytes(headers)
        self.stream = ByteStream(b"") if stream is None else stream
        self.extensions = {} if extensions is None else extensions

    def __repr__(self):
        return f"<{self.__class__.__name__} [{self.method}]>"


class Response:
    def __init__(
        self,
        status: int,
        *,
        headers: List[Tuple[Union[bytes, str], Union[bytes, str]]] = None,
        stream: Union[SyncByteStream, AsyncByteStream] = None,
        extensions: dict = None,
    ) -> None:
        self.status = status
        self.headers = [] if headers is None else enforce_headers_as_bytes(headers)
        self.stream = ByteStream(b"") if stream is None else stream
        self.extensions = {} if extensions is None else extensions

        self._stream_consumed = False

    @property
    def content(self) -> bytes:
        if not hasattr(self, "_content"):
            if isinstance(self.stream, SyncByteStream):
                raise RuntimeError(
                    "Attempted to access 'response.content' on a streaming response. "
                    "Call 'response.read()' first."
                )
            else:
                raise RuntimeError(
                    "Attempted to access 'response.content' on a streaming response. "
                    "Call 'await response.aread()' first."
                )
        return self._content

    def __repr__(self):
        return f"<{self.__class__.__name__} [{self.status}]>"

    # Sync interface...

    def __enter__(self) -> "Response":
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        assert isinstance(
            self.stream, SyncByteStream
        ), "Attempted to close an asynchronous response using 'with ... as response'. You should use 'async with ... as response' instead."
        self.close()

    def read(self) -> bytes:
        assert isinstance(
            self.stream, SyncByteStream
        ), "Attempted to read an asynchronous response using 'response.read()'. You should use 'await response.aread()' instead."
        if not hasattr(self, "_content"):
            self._content = b"".join([part for part in self.iter_stream()])
        return self._content

    def iter_stream(self) -> Iterator[bytes]:
        assert isinstance(
            self.stream, SyncByteStream
        ), "Attempted to stream an asynchronous response using 'for ... in response.iter_stream()'. You should use 'async for ... in response.aiter_stream()' instead."
        if self._stream_consumed:
            raise RuntimeError(
                "Attempted to call 'for ... in response.iter_stream()' more than once."
            )
        self._stream_consumed = True
        for chunk in self.stream:
            yield chunk

    def close(self) -> None:
        assert isinstance(
            self.stream, SyncByteStream
        ), "Attempted to close an asynchronous response using 'response.close()'. You should use 'await response.aclose()' instead."
        self.stream.close()

    # Async interface...

    async def __aenter__(self) -> "Response":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        assert isinstance(
            self.stream, AsyncByteStream
        ), "Attempted to close a synchronous response using 'async with ... as response'. You should use 'with ... as response' instead."
        await self.aclose()

    async def aread(self) -> bytes:
        assert isinstance(
            self.stream, AsyncByteStream
        ), "Attempted to read an synchronous response using 'await response.aread()'. You should use 'response.read()' instead."
        if not hasattr(self, "_content"):
            self._content = b"".join([part async for part in self.aiter_stream()])
        return self._content

    async def aiter_stream(self) -> Iterator[bytes]:
        assert isinstance(
            self.stream, AsyncByteStream
        ), "Attempted to stream an synchronous response using 'async for ... in response.aiter_stream()'. You should use 'for ... in response.iter_stream()' instead."
        if self._stream_consumed:
            raise RuntimeError(
                "Attempted to call 'async for ... in response.aiter_stream()' more than once."
            )
        self._stream_consumed = True
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        assert isinstance(
            self.stream, AsyncByteStream
        ), "Attempted to close a synchronous response using 'await response.aclose()'. You should use 'response.close()' instead."
        await self.stream.aclose()
