from typing import AsyncIterator, Dict, List, Optional, Type
from types import TracebackType
from ..backends.base import NetworkBackend
from ..backends.trio import TrioBackend
from ..base import (
    ConnectionNotAvailable,
    Origin,
    RawRequest,
    RawResponse,
    AsyncByteStream,
)
from ..synchronization import Lock, Semaphore
from .connection import AsyncHTTPConnection
from .interfaces import AsyncConnectionInterface
import random
import itertools


class AsyncConnectionPool:
    def __init__(
        self,
        max_connections: int,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        self._max_keepalive_connections = max_keepalive_connections
        self._keepalive_expiry = keepalive_expiry

        self._pool: List[AsyncConnectionInterface] = []
        self._pool_lock = Lock()
        self._pool_semaphore = Semaphore(bound=max_connections)
        self._network_backend = (
            TrioBackend() if network_backend is None else network_backend
        )

    def get_origin(self, request: RawRequest) -> Origin:
        return request.url.origin

    def create_connection(self, origin: Origin) -> AsyncConnectionInterface:
        return AsyncHTTPConnection(
            origin=origin,
            keepalive_expiry=self._keepalive_expiry,
            network_backend=self._network_backend,
        )

    def _max_keepalive_exceeded(self) -> bool:
        """
        Return `True` if the number of connections currently in the pool
        is exceeding the `max_keepalive_connections` watermark.
        """
        return (
            self._max_keepalive_connections is not None
            and len(self._pool) > self._max_keepalive_connections
        )

    async def _add_to_pool(self, connection: AsyncConnectionInterface) -> None:
        """
        Add an HTTP connection to the pool.
        """
        async with self._pool_lock:
            self._pool.insert(0, connection)

    async def _remove_from_pool(self, connection: AsyncConnectionInterface) -> None:
        """
        Remove an HTTP connection from the pool.
        """
        async with self._pool_lock:
            self._pool.remove(connection)

    async def _get_from_pool(
        self, origin: Origin
    ) -> Optional[AsyncConnectionInterface]:
        """
        Return an available HTTP connection for the given origin,
        if one currently exists in the pool.
        """
        async with self._pool_lock:
            for idx, connection in enumerate(self._pool):
                if connection.get_origin() == origin and connection.is_available():
                    self._pool.pop(idx)
                    self._pool.insert(0, connection)
                    return connection

        return None

    async def _close_one_idle_connection(self) -> bool:
        """
        Close one IDLE connection from the pool, returning `True` if successful,
        and `False` otherwise.
        """
        async with self._pool_lock:
            for idx, connection in reversed(list(enumerate(self._pool))):
                closed = await connection.attempt_close()
                if closed:
                    self._pool.pop(idx)
                    await self._pool_semaphore.release()
                    return True
        return False

    async def _close_expired_connections(self) -> None:
        """
        Close any connections in the pool that have expired their keepalive.
        """
        async with self._pool_lock:
            for idx, connection in reversed(list(enumerate(self._pool))):
                if connection.has_expired():
                    closed = await connection.attempt_close()
                    if closed:
                        self._pool.pop(idx)
                        await self._pool_semaphore.release()

    async def pool_info(self) -> Dict[str, List[str]]:
        """
        Return a dictionary mapping origins to lists of connection info.

        {
            "http://example.com:80": [
                "HTTP/1.1, IDLE, Request Count: 1"
            ]
            "https://example.com:443": [
                "HTTP/1.1, ACTIVE, Request Count: 6",
                "HTTP/1.1, IDLE, Request Count: 9"
            ]
        }
        """
        async with self._pool_lock:
            old_style = {}
            for conn in self._pool:
                origin = conn.get_origin()
                old_style.setdefault(origin, [])
                old_style[origin].append(conn)

            return {
                str(origin): [conn.info() for conn in conns]
                for origin, conns in old_style.items()
            }

    async def handle_async_request(self, request: RawRequest) -> RawResponse:
        """
        Send an HTTP request, and return an HTTP response.
        """
        origin = self.get_origin(request)

        while True:
            existing_connection = await self._get_from_pool(origin)

            if existing_connection is not None:
                # An existing connection was available. This could be:
                #
                # * An IDLE HTTP/1.1 connection.
                # * An IDLE or ACTIVE HTTP/2 connection.
                # * An HTTP connection that is in the process of being
                #   opened, and that *might* result in an HTTP/2 connection.
                connection = existing_connection
            else:
                while True:
                    # If no existing connection are available, we need to make
                    # sure not to exceed the maximum allowable number of
                    # connections, before we create on and add it to the pool.

                    # Try to obtain a ticket from the semaphore without
                    # blocking. If we get one, then we're now good to go.
                    if await self._pool_semaphore.acquire_noblock():
                        break

                    # If we couldn't get a ticket from the semaphore, then
                    # attempt to close one IDLE connection from the pool,
                    # before looping again.
                    if not await self._close_one_idle_connection():
                        # If we couldn't get a ticket from the semaphore,
                        # and there are no IDLE connections that we can close
                        # then we need a blocking wait on the semaphore.
                        await self._pool_semaphore.acquire()
                        break

                # Create a new connection and add it to the pool.
                connection = self.create_connection(origin)
                await self._add_to_pool(connection)

            try:
                # We've selected a connection to use, let's send the request.
                response = await connection.handle_async_request(request)
            except ConnectionNotAvailable:
                # Turns out the connection wasn't able to handle the request
                # for us. This could be because:
                #
                # * Multiple requests attempted to reuse an existing HTTP/1.1
                #   connection in close concurrency.
                # * A request attempted to reuse an existing connection,
                #   that ended up being closed in close concurrency.
                # * Multiple requests were contending for an opening connection
                #   that ended up resulting in an HTTP/1.1 connection.
                # * The request was to an HTTP/2 connection, but the stream ID
                #   space became exhausted, or a global error occured.
                continue
            except BaseException as exc:
                # If an exception occurs we check if we can release the
                # the connection to the pool.
                await self.response_closed(connection)
                raise exc

            # When we return the response, we wrap the stream in a special class
            # that handles notifying the connection pool once the response
            # has been released.
            return RawResponse(
                status=response.status,
                headers=response.headers,
                stream=ConnectionPoolByteStream(response.stream, self, connection),
                extensions=response.extensions,
            )

    async def response_closed(self, connection: AsyncConnectionInterface) -> None:
        """
        This method acts as a callback once the request/response cycle is complete.

        It is called into from the `ConnectionPoolByteStream.aclose()` method.
        """
        if connection.is_closed():
            await self._remove_from_pool(connection)
            await self._pool_semaphore.release()

        # Close any connections that have expired their keepalive time.
        await self._close_expired_connections()

        # Where possible we want to close off IDLE connections, until we're not
        # exceeding the max_keepalive_connections config, and the the pool
        # semaphore is not blocked waiting.
        while (
            self._max_keepalive_exceeded() or await self._pool_semaphore.would_block()
        ):
            if not await self._close_one_idle_connection():
                break

    async def aclose(self):
        async with self._pool_lock:
            for connection in self._pool:
                await connection.aclose()
            self._pool = []

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ):
        await self.aclose()


class ConnectionPoolByteStream(AsyncByteStream):
    """
    A wrapper around the response byte stream, that additionally handles
    notifying the connection pool when the response has been closed.
    """

    def __init__(
        self,
        stream: AsyncByteStream,
        pool: AsyncConnectionPool,
        connection: AsyncConnectionInterface,
    ) -> None:
        self._stream = stream
        self._pool = pool
        self._connection = connection

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for part in self._stream:
            yield part

    async def aclose(self):
        try:
            await self._stream.aclose()
        finally:
            await self._pool.response_closed(self._connection)
