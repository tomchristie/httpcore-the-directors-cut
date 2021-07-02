from typing import Any, AsyncIterator, List, Set, Tuple, Type
from types import TracebackType


class ByteStream:
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield b""  # pragma: nocover

    async def aclose(self) -> None:
        pass  # pragma: nocover

    async def aread(self) -> bytes:
        return b"".join([part async for part in self])


class Origin:
    def __init__(self, scheme: bytes, host: bytes, port: int) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port

    def __hash__(self) -> int:
        origin_tuple = (self.scheme, self.host, self.port)
        return hash(origin_tuple)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Origin)
            and self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __str__(self):
        scheme = self.scheme.decode("ascii")
        host = self.host.decode("ascii")
        port = str(self.port)
        return f"{scheme}://{host}:{port}"


class RawURL:
    def __init__(self, scheme: bytes, host: bytes, port: int, target: bytes) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.target = target

    @property
    def origin(self) -> Origin:
        return Origin(self.scheme, self.host, self.port)


class RawRequest:
    def __init__(
        self,
        method: bytes,
        url: RawURL,
        headers: List[Tuple[bytes, bytes]],
        stream: ByteStream,
        extensions: dict,
    ) -> None:
        self.method = method
        self.url = url
        self.headers = headers
        self.stream = stream
        self.extensions = extensions


class RawResponse:
    def __init__(
        self,
        status: int,
        headers: List[Tuple[bytes, bytes]],
        stream: ByteStream,
        extensions: dict,
    ) -> None:
        self.status = status
        self.headers = headers
        self.stream = stream
        self.extensions = extensions

    async def __aenter__(self) -> "RawResponse":
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


class ConnectionInterface:
    async def handle_request(self, request: RawRequest) -> RawResponse:
        raise NotImplementedError()  # pragma: nocover

    async def attempt_aclose(self) -> bool:
        raise NotImplementedError()  # pragma: nocover

    async def aclose(self) -> None:
        raise NotImplementedError()  # pragma: nocover

    def info(self) -> str:
        raise NotImplementedError()  # pragma: nocover

    def get_origin(self) -> Origin:
        raise NotImplementedError()  # pragma: nocover

    def is_available(self) -> bool:
        """
        Return `True` if the connection is currently able to accept an outgoing request.

        An HTTP/1.1 connection will only be available if it is currently idle.

        An HTTP/2 connection will be available so long as the stream ID space is
        not yet exhausted, and the connection is not in an error state.

        While the connection is being established we may not yet know if it is going
        to result in an HTTP/1.1 or HTTP/2 connection. The connection should be
        treated as being available, but might ultimately raise `NewConnectionRequired`
        required exceptions if multiple requests are attempted over a connection
        that ends up being established as HTTP/1.1.
        """
        raise NotImplementedError()  # pragma: nocover

    def has_expired(self) -> bool:
        """
        Return `True` if the connection is in a state where it should be closed.

        This either means that the connection is idle and it has passed the
        expiry time on its keep-alive, or that server has sent an EOF.
        """
        raise NotImplementedError()  # pragma: nocover

    def is_idle(self) -> bool:
        """
        Return `True` if the connection is currently idle.
        """
        raise NotImplementedError()  # pragma: nocover

    def is_closed(self) -> bool:
        """
        Return `True` if the connection has been closed.

        Used when a response is closed to determine if the connection may be
        returned to the connection pool or not.
        """
        raise NotImplementedError()  # pragma: nocover


class ConnectionNotAvailable(Exception):
    pass
