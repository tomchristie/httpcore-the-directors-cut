from .base import ByteStream, ConnectionInterface, ConnectionNotAvailable, Origin, RawRequest, RawResponse
from .synchronization import Lock
from types import TracebackType
from typing import AsyncIterator, Callable, Tuple, List, Type
import enum
import time


class HTTPConnectionState(enum.IntEnum):
    NEW = 0
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


class HTTP11Connection(ConnectionInterface):
    def __init__(self, origin: Origin, keepalive_expiry: float=None) -> None:
        self._origin = origin
        self._keepalive_expiry = keepalive_expiry
        self._expire_at: float = None
        self._connection_close = False
        self._state = HTTPConnectionState.NEW
        self._state_lock = Lock()
        self._request_count = 0

    async def handle_request(self, request: RawRequest) -> RawResponse:
        async with self._state_lock:
            if self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE):
                self._request_count += 1
                self._state = HTTPConnectionState.ACTIVE
                self._expire_at = None
            else:
                raise ConnectionNotAvailable()

        try:
            await self._send_request_headers(request)
            await self._send_request_body(request)
            (
                http_version,
                status_code,
                reason_phrase,
                headers,
            ) =  await self._receive_response_headers()
            return RawResponse(
                status=status_code,
                headers=headers,
                stream=HTTPConnectionByteStream(
                    aiterator=self._receive_response_body(),
                    aclose_func=self._response_closed,
                ),
                extensions={
                    'http_version': http_version,
                    'reason_phrase': reason_phrase
                }
            )
        except BaseException as exc:
            await self.aclose()
            raise exc

    async def _send_request_headers(self, request: RawRequest) -> None:
        pass

    async def _send_request_body(self, request: RawRequest) -> None:
        pass

    async def _receive_response_headers(self) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]]]:
        return (b'OK', 200, b'HTTP/1.1', [(b'Content-Length', b'13')])

    async def _receive_response_body(self) -> AsyncIterator[bytes]:
        yield b"Hello, world!"

    async def _response_closed(self) -> None:
        async with self._state_lock:
            if self._connection_close:
                self._state = HTTPConnectionState.CLOSED
                # self._stream.close()
            else:
                self._state = HTTPConnectionState.IDLE
                if self._keepalive_expiry is not None:
                    self._expire_at = self._now() + self._keepalive_expiry

    async def attempt_close(self) -> bool:
        async with self._state_lock:
            closed = self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE)
            if closed:
                self._state = HTTPConnectionState.CLOSED

        return closed

    async def aclose(self) -> None:
        self._state = HTTPConnectionState.CLOSED

    def get_origin(self) -> Origin:
        return self._origin

    def is_available(self) -> bool:
        # Note that HTTP/1.1 connections in the "NEW" state are not treated as
        # being "available". The control flow which created the connection will
        # be able to send an outgoing request, but the connection will not be
        # acquired from the connection pool for any other request.
        return self._state == HTTPConnectionState.IDLE

    def has_expired(self) -> bool:
        return self._expire_at is not None and self._now() > self._expire_at

    def is_idle(self) -> bool:
        return self._state == HTTPConnectionState.IDLE

    def is_closed(self) -> bool:
        return self._state == HTTPConnectionState.CLOSED

    def _now(self) -> float:
        return time.monotonic()

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} [{self._state.name}, "
            f"Request Count: {self._request_count}]>"
        )

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None
    ):
        await self.aclose()


class HTTPConnectionByteStream(ByteStream):
    def __init__(self, aiterator: AsyncIterator[bytes], aclose_func: Callable):
        self._aiterator = aiterator
        self._aclose_func = aclose_func

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._aiterator:
            yield chunk

    async def aclose(self) -> None:
        await self._aclose_func()
