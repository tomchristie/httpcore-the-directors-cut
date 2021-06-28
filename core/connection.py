from .base import ByteStream, ConnectionInterface, NewConnectionRequired, Origin, RawRequest, RawResponse
from .synchronization import Lock
from typing import AsyncIterator
import enum


class HTTPConnectionState(enum.IntEnum):
    NEW = 0
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


class HTTPConnection(ConnectionInterface):
    def __init__(self, origin: Origin) -> None:
        self._origin = origin
        self._connection_close = False
        self._state = HTTPConnectionState.NEW
        self._state_lock = Lock()
        self._request_count = 0

    async def handle_request(self, request: RawRequest) -> RawResponse:
        async with self._state_lock:
            self._request_count += 1
            if self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE):
                self._state = HTTPConnectionState.ACTIVE
            else:
                raise NewConnectionRequired()

        self._connection_close = any([
            (k.lower(), v.lower()) == (b'connection', b'close')
            for k, v in request.headers
        ])

        return RawResponse(
            status=200,
            headers=[(b'Content-Length', b'13')],
            stream=HTTPConnectionByteStream(b"Hello, world!", self),
            extensions={
                'http_version': b'HTTP/1.1',
                'reason_phrase': b'OK'
            }
        )

    async def response_closed(self) -> None:
        async with self._state_lock:
            if self._connection_close:
                self._state = HTTPConnectionState.CLOSED
                # self._stream.close()
            else:
                self._state = HTTPConnectionState.IDLE

    async def attempt_close(self) -> bool:
        async with self._state_lock:
            closed = self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE)
            if closed:
                self._state = HTTPConnectionState.CLOSED

        return closed

    async def aclose(self) -> None:
        self._state = HTTPConnectionState.CLOSED

    def info(self) -> str:
        return f"HTTP/1.1, {self._state.name}, Request Count: {self._request_count}"

    def get_origin(self) -> Origin:
        return self._origin

    def is_available(self) -> bool:
        # Note that HTTP/1.1 connections in the "NEW" state are not treated as
        # being "available". The control flow which created the connection will
        # be able to send an outgoing request, but the connection will not be
        # acquired from the connection pool for any other request.
        return self._state == HTTPConnectionState.IDLE

    def has_expired(self) -> bool:
        return False

    def is_idle(self) -> bool:
        return self._state == HTTPConnectionState.IDLE

    def is_closed(self) -> bool:
        return self._state == HTTPConnectionState.CLOSED


class HTTPConnectionByteStream(ByteStream):
    def __init__(self, content: bytes, connection: HTTPConnection):
        self._content = content
        self._connection = connection

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._content

    async def aclose(self) -> None:
        await self._connection.response_closed()
