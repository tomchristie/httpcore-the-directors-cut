import enum
import time
from types import TracebackType
from typing import AsyncIterator, Callable, List, Optional, Tuple, Type, Union

import h11

from .._models import AsyncByteStream, Origin, Request, Response
from ..backends.base import AsyncNetworkStream
from .._exceptions import (
    map_exceptions,
    ConnectionNotAvailable,
    LocalProtocolError,
    RemoteProtocolError,
)
from .._synchronization import AsyncLock
from .interfaces import AsyncConnectionInterface

H11Event = Union[
    h11.Request,
    h11.Response,
    h11.InformationalResponse,
    h11.Data,
    h11.EndOfMessage,
    h11.ConnectionClosed,
]


class HTTPConnectionState(enum.IntEnum):
    NEW = 0
    ACTIVE = 1
    IDLE = 2
    CLOSED = 3


class AsyncHTTP11Connection(AsyncConnectionInterface):
    READ_NUM_BYTES = 64 * 1024

    def __init__(
        self, origin: Origin, stream: AsyncNetworkStream, keepalive_expiry: float = None
    ) -> None:
        self._origin = origin
        self._network_stream = stream
        self._keepalive_expiry: Optional[float] = keepalive_expiry
        self._expire_at: Optional[float] = None
        self._state = HTTPConnectionState.NEW
        self._state_lock = AsyncLock()
        self._request_count = 0
        self._h11_state = h11.Connection(our_role=h11.CLIENT)

    async def handle_async_request(self, request: Request) -> Response:
        if not self.can_handle_request(request.url.origin):
            raise ConnectionNotAvailable(
                f"Attempted to send request to {request.url.origin} on connection to {self._origin}"
            )

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
                status,
                reason_phrase,
                headers,
            ) = await self._receive_response_headers(request)

            return Response(
                status=status,
                headers=headers,
                content=HTTP11ConnectionByteStream(self, request),
                extensions={
                    "http_version": http_version,
                    "reason_phrase": reason_phrase,
                    "stream": self._network_stream,
                },
            )
        except BaseException as exc:
            await self.aclose()
            raise exc

    # Sending the request...

    async def _send_request_headers(self, request: Request) -> None:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        with map_exceptions({h11.LocalProtocolError: LocalProtocolError}):
            event = h11.Request(
                method=request.method,
                target=request.url.target,
                headers=request.headers,
            )
        await self._send_event(event, timeout=timeout)

    async def _send_request_body(self, request: Request) -> None:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        assert isinstance(request.stream, AsyncByteStream)
        async for chunk in request.stream:
            event = h11.Data(data=chunk)
            await self._send_event(event)

        event = h11.EndOfMessage()
        await self._send_event(event, timeout=timeout)

    async def _send_event(self, event: H11Event, timeout: float = None) -> None:
        bytes_to_send = self._h11_state.send(event)
        await self._network_stream.write(bytes_to_send, timeout=timeout)

    # Receiving the response...

    async def _receive_response_headers(
        self, request: Request
    ) -> Tuple[bytes, int, bytes, List[Tuple[bytes, bytes]]]:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("read", None)

        while True:
            event = await self._receive_event(timeout=timeout)
            if isinstance(event, h11.Response):
                break

        http_version = b"HTTP/" + event.http_version

        # h11 version 0.11+ supports a `raw_items` interface to get the
        # raw header casing, rather than the enforced lowercase headers.
        headers = event.headers.raw_items()

        return http_version, event.status_code, event.reason, headers

    async def _receive_response_body(self, request: Request) -> AsyncIterator[bytes]:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("read", None)

        while True:
            event = await self._receive_event(timeout=timeout)
            if isinstance(event, h11.Data):
                yield bytes(event.data)
            elif isinstance(event, (h11.EndOfMessage, h11.PAUSED)):
                break

    async def _receive_event(self, timeout: float = None) -> H11Event:
        while True:
            with map_exceptions({h11.RemoteProtocolError: RemoteProtocolError}):
                event = self._h11_state.next_event()

            if event is h11.NEED_DATA:
                data = await self._network_stream.read(
                    self.READ_NUM_BYTES, timeout=timeout
                )
                self._h11_state.receive_data(data)
            else:
                return event

    async def _response_closed(self) -> None:
        async with self._state_lock:
            if (
                self._h11_state.our_state is h11.DONE
                and self._h11_state.their_state is h11.DONE
            ):
                self._state = HTTPConnectionState.IDLE
                self._h11_state.start_next_cycle()
                if self._keepalive_expiry is not None:
                    now = time.monotonic()
                    self._expire_at = now + self._keepalive_expiry
            else:
                await self.aclose()

    # Once the connection is no longer required...

    async def aclose(self) -> None:
        # Note that this method unilaterally closes the connection, and does
        # not have any kind of locking in place around it.
        # For task-safe/thread-safe operations call into 'attempt_close' instead.
        self._state = HTTPConnectionState.CLOSED
        await self._network_stream.aclose()

    # The AsyncConnectionInterface methods provide information about the state of
    # the connection, allowing for a connection pooling implementation to
    # determine when to reuse and when to close the connection...

    def can_handle_request(self, origin: Origin) -> bool:
        return origin == self._origin

    def is_available(self) -> bool:
        # Note that HTTP/1.1 connections in the "NEW" state are not treated as
        # being "available". The control flow which created the connection will
        # be able to send an outgoing request, but the connection will not be
        # acquired from the connection pool for any other request.
        return self._state == HTTPConnectionState.IDLE

    def has_expired(self) -> bool:
        now = time.monotonic()
        return self._expire_at is not None and now > self._expire_at

    def is_idle(self) -> bool:
        return self._state == HTTPConnectionState.IDLE

    def is_closed(self) -> bool:
        return self._state == HTTPConnectionState.CLOSED

    async def attempt_aclose(self) -> bool:
        async with self._state_lock:
            if self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE):
                await self.aclose()
                return True
        return False

    def info(self) -> str:
        origin = str(self._origin)
        return f"{origin!r}, HTTP/1.1, {self._state.name}, Request Count: {self._request_count}"

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        origin = str(self._origin)
        return f"<{class_name} [{origin!r}, {self._state.name}, Request Count: {self._request_count}]>"

    # These context managers are not used in the standard flow, but are
    # useful for testing or working with connection instances directly.

    async def __aenter__(self) -> "AsyncHTTP11Connection":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        await self.aclose()


class HTTP11ConnectionByteStream(AsyncByteStream):
    def __init__(self, connection: AsyncHTTP11Connection, request: Request) -> None:
        self._connection = connection
        self._request = request

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for chunk in self._connection._receive_response_body(self._request):
            yield chunk

    async def aclose(self) -> None:
        await self._connection._response_closed()
