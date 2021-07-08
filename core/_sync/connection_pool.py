from typing import Iterator, Dict, List, Optional, Type
from types import TracebackType
from ..backends.base import AsyncNetworkBackend
from ..backends.trio import TrioBackend
from ..base import (
    ConnectionNotAvailable,
    Origin,
    RawRequest,
    RawResponse,
    ByteStream,
)
from ..synchronization import Lock, Semaphore
from .connection import HTTPConnection
from .interfaces import ConnectionInterface
import random
import itertools


class ConnectionPool:
    def __init__(
        self,
        max_connections: int,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        network_backend: AsyncNetworkBackend = None,
    ) -> None:
        self._max_keepalive_connections = max_keepalive_connections
        self._keepalive_expiry = keepalive_expiry

        self._num_connections = 0
        self._pool: Dict[Origin, List[ConnectionInterface]] = {}
        self._pool_lock = Lock()
        self._pool_semaphore = Semaphore(bound=max_connections)
        self._network_backend = (
            TrioBackend() if network_backend is None else network_backend
        )

    def get_origin(self, request: RawRequest) -> Origin:
        return request.url.origin

    def create_connection(self, origin: Origin) -> ConnectionInterface:
        return HTTPConnection(
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
            and self._num_connections > self._max_keepalive_connections
        )

    def _add_to_pool(self, connection: ConnectionInterface) -> None:
        """
        Add an HTTP connection to the pool.
        """
        origin = connection.get_origin()
        with self._pool_lock:
            self._pool.setdefault(origin, [])
            self._pool[origin].append(connection)
            self._num_connections += 1

    def _remove_from_pool(self, connection: ConnectionInterface) -> None:
        """
        Remove an HTTP connection from the pool.
        """
        origin = connection.get_origin()
        with self._pool_lock:
            self._pool[origin].remove(connection)
            self._num_connections -= 1
            if not self._pool[origin]:
                self._pool.pop(origin)

    def _get_from_pool(
        self, origin: Origin
    ) -> Optional[ConnectionInterface]:
        """
        Return an available HTTP connection for the given origin,
        if one currently exists in the pool.
        """
        with self._pool_lock:
            available_connections = self._pool.get(origin, [])
            available_connections = [
                c for c in available_connections if c.is_available()
            ]

        if available_connections:
            return random.choice(available_connections)
        return None

    def _close_one_idle_connection(self) -> bool:
        """
        Close one IDLE connection from the pool, returning `True` if successful,
        and `False` otherwise.
        """
        with self._pool_lock:
            idle_connections = list(itertools.chain.from_iterable(self._pool.values()))
            idle_connections = [c for c in idle_connections if c.is_idle()]

        random.shuffle(idle_connections)
        for connection in idle_connections:
            closed = connection.attempt_close()
            if closed:
                self._remove_from_pool(connection)
                self._pool_semaphore.release()
                return True
        return False

    def _close_expired_connections(self) -> None:
        """
        Close any connections in the pool that have expired their keepalive.
        """
        with self._pool_lock:
            expired_connections = list(
                itertools.chain.from_iterable(self._pool.values())
            )
            expired_connections = [c for c in expired_connections if c.has_expired()]

        for connection in expired_connections:
            closed = connection.attempt_close()
            if closed:
                self._remove_from_pool(connection)
                self._pool_semaphore.release()

    def pool_info(self) -> Dict[str, List[str]]:
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
        with self._pool_lock:
            return {
                str(origin): [conn.info() for conn in conns]
                for origin, conns in self._pool.items()
            }

    def handle_request(self, request: RawRequest) -> RawResponse:
        """
        Send an HTTP request, and return an HTTP response.
        """
        origin = self.get_origin(request)

        while True:
            existing_connection = self._get_from_pool(origin)

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
                    if self._pool_semaphore.acquire_noblock():
                        break

                    # If we couldn't get a ticket from the semaphore, then
                    # attempt to close one IDLE connection from the pool,
                    # before looping again.
                    if not self._close_one_idle_connection():
                        # If we couldn't get a ticket from the semaphore,
                        # and there are no IDLE connections that we can close
                        # then we need a blocking wait on the semaphore.
                        self._pool_semaphore.acquire()
                        break

                # Create a new connection and add it to the pool.
                connection = self.create_connection(origin)
                self._add_to_pool(connection)

            try:
                # We've selected a connection to use, let's send the request.
                response = connection.handle_request(request)
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
                self.response_closed(connection)
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

    def response_closed(self, connection: ConnectionInterface) -> None:
        """
        This method acts as a callback once the request/response cycle is complete.

        It is called into from the `ConnectionPoolByteStream.close()` method.
        """
        if connection.is_closed():
            self._remove_from_pool(connection)
            self._pool_semaphore.release()

        # Close any connections that have expired their keepalive time.
        self._close_expired_connections()

        # Where possible we want to close off IDLE connections, until we're not
        # exceeding the max_keepalive_connections config, and the the pool
        # semaphore is not blocked waiting.
        while (
            self._max_keepalive_exceeded() or self._pool_semaphore.would_block()
        ):
            if not self._close_one_idle_connection():
                break

    def close(self):
        with self._pool_lock:
            for connections in self._pool.values():
                for connection in connections:
                    connection.close()
            self._pool = {}

    def __enter__(self):
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ):
        self.close()


class ConnectionPoolByteStream(ByteStream):
    """
    A wrapper around the response byte stream, that additionally handles
    notifying the connection pool when the response has been closed.
    """

    def __init__(
        self,
        stream: ByteStream,
        pool: ConnectionPool,
        connection: ConnectionInterface,
    ) -> None:
        self._stream = stream
        self._pool = pool
        self._connection = connection

    def __iter__(self) -> Iterator[bytes]:
        for part in self._stream:
            yield part

    def close(self):
        try:
            self._stream.close()
        finally:
            self._pool.response_closed(self._connection)