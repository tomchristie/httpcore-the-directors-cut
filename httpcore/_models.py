from types import TracebackType
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Dict,
    Iterable,
    Iterator,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)
from urllib.parse import urlparse

__all__ = [
    "Origin",
    "URL",
    "Request",
    "Response",
]


# Functions for typechecking...


def enforce_bytes(value: Union[bytes, str], *, name: str) -> bytes:
    """
    Any arguments that are ultimately represented as bytes can be specified
    either as bytes or as strings.

    However we enforce that any string arguments must only contain characters in
    the plain ASCII range. chr(0)...chr(127). If you need to use characters
    outside that range then be precise, and use a byte-wise argument.
    """
    if isinstance(value, str):
        try:
            return value.encode("ascii")
        except UnicodeEncodeError:
            raise TypeError(f"{name} strings may not include unicode characters.")
    elif isinstance(value, bytes):
        return value

    seen_type = type(value).__name__
    raise TypeError(f"{name} must be bytes or str, but got {seen_type}.")


def enforce_url(value: Union["URL", bytes, str], *, name: str) -> "URL":
    """
    Type check for URL parameters.
    """
    if isinstance(value, (bytes, str)):
        return URL(value)
    elif isinstance(value, URL):
        return value

    seen_type = type(value).__name__
    raise TypeError(f"{name} must be a URL, bytes, or str, but got {seen_type}.")


def enforce_headers(
    value: Union[dict, list] = None, *, name: str
) -> List[Tuple[bytes, bytes]]:
    """
    Convienence function that ensure all items in request or response headers
    are either bytes or strings in the plain ASCII range.
    """
    if value is None:
        return []
    elif isinstance(value, (list, tuple)):
        return [
            (
                enforce_bytes(k, name="header name"),
                enforce_bytes(v, name="header value"),
            )
            for k, v in value
        ]
    elif isinstance(value, dict):
        return [
            (
                enforce_bytes(k, name="header name"),
                enforce_bytes(v, name="header value"),
            )
            for k, v in value.items()
        ]

    seen_type = type(value).__name__
    raise TypeError(f"{name} must be a list, but got {seen_type}.")


def enforce_stream(
    value: Union[bytes, Iterable[bytes], AsyncIterable[bytes]], *, name: str
) -> Union[Iterable[bytes], AsyncIterable[bytes]]:
    if value is None:
        return ByteStream(b"")
    elif isinstance(value, bytes):
        return ByteStream(value)
    return value


# * https://tools.ietf.org/html/rfc3986#section-3.2.3
# * https://url.spec.whatwg.org/#url-miscellaneous
# * https://url.spec.whatwg.org/#scheme-state
DEFAULT_PORTS = {
    b"ftp": 21,
    b"http": 80,
    b"https": 443,
    b"ws": 80,
    b"wss": 443,
}


def include_request_headers(
    headers: List[Tuple[bytes, bytes]],
    *,
    url: "URL",
    content: Union[None, bytes, Iterable[bytes], AsyncIterable[bytes]],
):
    headers_set = set([k.lower() for k, v in headers])

    if b"host" not in headers_set:
        default_port = DEFAULT_PORTS.get(url.scheme)
        if url.port is None or url.port == default_port:
            header_value = url.host
        else:
            header_value = b"%b:%d" % (url.host, url.port)
        headers = [(b"Host", header_value)] + headers

    if (
        content is not None
        and b"content-length" not in headers_set
        and b"transfer-encoding" not in headers_set
    ):
        if isinstance(content, bytes):
            content_length = str(len(content)).encode("ascii")
            headers += [(b"Content-Length", content_length)]
        else:
            headers += [(b"Transfer-Encoding", b"chunked")]  # pragma: nocover

    return headers


# Interfaces for byte streams...


class ByteStream:
    """
    A container for non-streaming content, and that supports both sync and async
    stream iteration.
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
        target=b'https://www.example.com/'
    )
    >>> request = httpcore.Request(
        method="GET",
        url=url
    )

    GET https://www.example.com/ HTTP/1.1

    Another example is constructing an 'OPTIONS *' request...

    >>> url = httpcore.URL(scheme=b'https', host=b'www.example.com', target=b'*')
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
        default_port = {b"http": 80, b"https": 443}[self.scheme]
        return Origin(
            scheme=self.scheme, host=self.host, port=self.port or default_port
        )

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

    def __repr__(self):
        return f"{self.__class__.__name__}(scheme={self.scheme!r}, host={self.host!r}, port={self.port!r}, target={self.target!r})"


class Request:
    def __init__(
        self,
        method: Union[bytes, str],
        url: Union[URL, bytes, str],
        *,
        headers: Union[dict, list] = None,
        content: Union[bytes, Iterable[bytes], AsyncIterable[bytes]] = None,
        extensions: dict = None,
    ) -> None:
        self.method: bytes = enforce_bytes(method, name="method")
        self.url: URL = enforce_url(url, name="url")
        self.headers: List[Tuple[bytes, bytes]] = enforce_headers(
            headers, name="headers"
        )
        self.stream: Union[Iterable[bytes], AsyncIterable[bytes]] = enforce_stream(
            content, name="content"
        )
        self.extensions = {} if extensions is None else extensions

    def __repr__(self):
        return f"<{self.__class__.__name__} [{self.method}]>"


class Response:
    """
    Another docstring

    Attributes:
        status: The HTTP status code of the response.
        headers: The HTTP response headers.
        stream: The content of the response body.
        extensions: ...
    """

    def __init__(
        self,
        status: int,
        *,
        headers: Union[dict, list] = None,
        content: Union[bytes, Iterable[bytes], AsyncIterable[bytes]] = None,
        extensions: dict = None,
    ) -> None:
        self.status: int = status
        self.headers: List[Tuple[bytes, bytes]] = enforce_headers(
            headers, name="headers"
        )
        self.stream: Union[Iterable[bytes], AsyncIterable[bytes]] = enforce_stream(
            content, name="content"
        )
        self.extensions: dict = {} if extensions is None else extensions

        self._stream_consumed = False

    @property
    def content(self) -> bytes:
        if not hasattr(self, "_content"):
            if isinstance(self.stream, Iterable):
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

    def read(self) -> bytes:
        if not isinstance(self.stream, Iterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to read an asynchronous response using 'response.read()'. "
                "You should use 'await response.aread()' instead."
            )
        if not hasattr(self, "_content"):
            self._content = b"".join([part for part in self.iter_stream()])
        return self._content

    def iter_stream(self) -> Iterator[bytes]:
        if not isinstance(self.stream, Iterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to stream an asynchronous response using 'for ... in response.iter_stream()'. "
                "You should use 'async for ... in response.aiter_stream()' instead."
            )
        if self._stream_consumed:
            raise RuntimeError(
                "Attempted to call 'for ... in response.iter_stream()' more than once."
            )
        self._stream_consumed = True
        for chunk in self.stream:
            yield chunk

    def close(self) -> None:
        if not isinstance(self.stream, Iterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to close an asynchronous response using 'response.close()'. "
                "You should use 'await response.aclose()' instead."
            )
        if hasattr(self.stream, "close"):
            self.stream.close()

    # Async interface...

    async def aread(self) -> bytes:
        if not isinstance(self.stream, AsyncIterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to read an synchronous response using 'await response.aread()'. "
                "You should use 'response.read()' instead."
            )
        if not hasattr(self, "_content"):
            self._content = b"".join([part async for part in self.aiter_stream()])
        return self._content

    async def aiter_stream(self) -> Iterator[bytes]:
        if not isinstance(self.stream, AsyncIterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to stream an synchronous response using 'async for ... in response.aiter_stream()'. "
                "You should use 'for ... in response.iter_stream()' instead."
            )
        if self._stream_consumed:
            raise RuntimeError(
                "Attempted to call 'async for ... in response.aiter_stream()' more than once."
            )
        self._stream_consumed = True
        async for chunk in self.stream:
            yield chunk

    async def aclose(self) -> None:
        if not isinstance(self.stream, AsyncIterable):  # pragma: nocover
            raise RuntimeError(
                "Attempted to close a synchronous response using 'await response.aclose()'. "
                "You should use 'response.close()' instead."
            )
        if hasattr(self.stream, "aclose"):
            await self.stream.aclose()
