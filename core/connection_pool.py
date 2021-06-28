from typing import AsyncIterator, Dict, List, Type
from types import TracebackType
from .base import ByteStream, ConnectionInterface, RawRequest, RawResponse, Origin, NewConnectionRequired
from .connection import HTTPConnection
from .synchronization import Lock, Semaphore
import random
import itertools


class ConnectionPool:
    def __init__(
        self,
        max_connections: int,
        max_keepalive_connections: int = None,
    ) -> None:
        self._max_keepalive_connections = max_keepalive_connections

        self._pool: Dict[Origin, List[ConnectionInterface]] = {}
        self._pool_lock = Lock()
        self._pool_semaphore = Semaphore(bound=max_connections)

    def get_origin(self, request: RawRequest) -> Origin:
        return request.url.origin

    def create_connection(self, origin: Origin) -> ConnectionInterface:
        return HTTPConnection(origin=origin)

    async def _add_to_pool(self, connection: ConnectionInterface) -> None:
        """
        Add an HTTP connection to the pool.
        """
        origin = connection.get_origin()
        async with self._pool_lock:
            self._pool.setdefault(origin, [])
            self._pool[origin].append(connection)

    async def _remove_from_pool(self, connection: ConnectionInterface) -> None:
        """
        Remove an HTTP connection from the pool.
        """
        origin = connection.get_origin()
        async with self._pool_lock:
            self._pool[origin].remove(connection)
            if not self._pool[origin]:
                self._pool.pop(origin)

    async def _close_one_idle_connection(self) -> bool:
        """
        Close one IDLE connection from the pool, returning `True` if successful,
        and `False` otherwise.
        """
        async with self._pool_lock:
            connections = list(itertools.chain.from_iterable(self._pool.values()))

        random.shuffle(connections)
        for connection in connections:
            if connection.is_idle():
                closed = await connection.attempt_close()
                if closed:
                    await self._remove_from_pool(connection)
                    await self._pool_semaphore.release()
                    return True
        return False

    async def _get_available_connections(self, origin: Origin) -> List[ConnectionInterface]:
        """
        Return a list of any HTTP connections that are currently available for reuse,
        filtered to a signle given origin.
        """
        async with self._pool_lock:
            available_connections = self._pool.get(origin, [])
            return [c for c in available_connections if c.is_available()]

    async def _count_existing_connections(self) -> int:
        """
        Return the number of HTTP connections currently in the connection pool.
        """
        async with self._pool_lock:
            return sum([len(conns) for conns in self._pool.values()])

    async def pool_info(self) -> Dict[str, List[str]]:
        async with self._pool_lock:
            return {
                str(origin): [conn.info() for conn in conns]
                for origin, conns in self._pool.items()
            }

    async def handle_request(self, request: RawRequest) -> RawResponse:
        """
        Send an HTTP request, and return an HTTP response.
        """
        origin = self.get_origin(request)

        while True:
            available_connections = await self._get_available_connections(origin)

            if available_connections:
                # An existing connection was available. This could be:
                #
                # * An IDLE HTTP/1.1 connection.
                # * An IDLE or ACTIVE HTTP/2 connection.
                # * An HTTP connection that is in the process of being
                #   opened, and that *might* result in an HTTP/2 connection.
                connection = random.choice(available_connections)
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
                response = await connection.handle_request(request)
            except NewConnectionRequired:
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
                pass
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
                extensions=response.extensions
            )

    async def response_closed(self, connection: ConnectionInterface) -> None:
        if connection.is_closed():
            await self._remove_from_pool(connection)
            await self._pool_semaphore.release()

        if self._max_keepalive_connections is not None:
            num_connections = await self._count_existing_connections()
            while num_connections > self._max_keepalive_connections:
                if await self._close_one_idle_connection():
                    num_connections -= 1
                else:
                    break

    async def aclose(self):
        async with self._pool_lock:
            for connections in self._pool.values():
                for connection in connections:
                    await connection.aclose()
            self._pool = {}

    async def __aenter__(self):
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None
    ):
        await self.aclose()


class ConnectionPoolByteStream(ByteStream):
    """
    A wrapper around the response byte stream, that additionally handles
    notifying the connection pool when the response has been closed.
    """
    def __init__(self, stream: ByteStream, pool: ConnectionPool, connection: ConnectionInterface) -> None:
        self._stream = stream
        self._pool  = pool
        self._connection = connection

    async def __aiter__(self) -> AsyncIterator[bytes]:
        async for part in self._stream:
            yield part

    async def aclose(self):
        try:
            await self._stream.aclose()
        finally:
            await self._pool.response_closed(self._connection)
