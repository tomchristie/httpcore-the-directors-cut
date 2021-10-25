import ssl
from types import TracebackType
from typing import Iterable, Iterator, List, Optional, Type

from ..backends.sync import SyncBackend
from ..backends.base import NetworkBackend
from .._exceptions import ConnectionNotAvailable, UnsupportedProtocol
from .._ssl import default_ssl_context
from .._synchronization import Lock, Semaphore
from .._models import Origin, Request, Response
from .connection import HTTPConnection
from .interfaces import ConnectionInterface, RequestInterface


class ConnectionPool(RequestInterface):
    """
    A connection pool for making HTTP requests.
    """

    def __init__(
        self,
        ssl_context: ssl.SSLContext = None,
        max_connections: int = 10,
        max_keepalive_connections: int = None,
        keepalive_expiry: float = None,
        http1: bool = True,
        http2: bool = False,
        retries: int = 0,
        local_address: str = None,
        uds: str = None,
        network_backend: NetworkBackend = None,
    ) -> None:
        """
        A connection pool for making HTTP requests.

        Parameters:
            ssl_context: An SSL context to use for verifying connections.
                         If not specified, the default `httpcore.default_ssl_context()`
                         will be used.
            max_connections: The maximum number of concurrent HTTP connections that the pool
                             should allow. Any attempt to send a request on a pool that would
                             exceed this amount will block until a connection is available.
            max_keepalive_connections: The maximum number of idle HTTP connections that will
                                       be maintained in the pool.
            keepalive_expiry: The duration in seconds that an idle HTTP connection may be
                              maintained for before being expired from the pool.
            http1: A boolean indicating if HTTP/1.1 requests should be supported by the connection
                   pool. Defaults to True.
            http2: A boolean indicating if HTTP/2 requests should be supported by the connection
                   pool. Defaults to False.
            retries: The maximum number of retries when trying to establish a connection.
            local_address: Local address to connect from. Can also be used to connect using
                           a particular address family. Using `local_address="0.0.0.0"` will
                           connect using an `AF_INET` address (IPv4), while using `local_address="::"`
                           will connect using an `AF_INET6` address (IPv6).
            uds: Path to a Unix Domain Socket to use instead of TCP sockets.
            network_backend: A backend instance to use for handling network I/O.
        """
        if max_keepalive_connections is None:
            max_keepalive_connections = max_connections - 1

        if ssl_context is None:
            ssl_context = default_ssl_context()

        self._ssl_context = ssl_context

        # We always close off keep-alives to allow at least one slot
        # in the connection pool. There are more nifty strategies that we
        # could use, but this keeps things nice and simple.
        self._max_keepalive_connections = min(
            max_keepalive_connections, max_connections - 1
        )
        self._keepalive_expiry = keepalive_expiry
        self._http1 = http1
        self._http2 = http2
        self._retries = retries
        self._local_address = local_address
        self._uds = uds

        self._pool: List[ConnectionInterface] = []
        self._pool_lock = Lock()
        self._pool_semaphore = Semaphore(bound=max_connections)
        self._network_backend = (
            SyncBackend() if network_backend is None else network_backend
        )

    def create_connection(self, origin: Origin) -> ConnectionInterface:
        return HTTPConnection(
            origin=origin,
            ssl_context=self._ssl_context,
            keepalive_expiry=self._keepalive_expiry,
            http1=self._http1,
            http2=self._http2,
            retries=self._retries,
            local_address=self._local_address,
            uds=self._uds,
            network_backend=self._network_backend,
        )

    def _add_to_pool(self, connection: ConnectionInterface) -> None:
        """
        Add an HTTP connection to the pool.
        """
        with self._pool_lock:
            self._pool.insert(0, connection)

    def _remove_from_pool(self, connection: ConnectionInterface) -> None:
        """
        Remove an HTTP connection from the pool.
        """
        with self._pool_lock:
            self._pool.remove(connection)

    def _get_from_pool(
        self, origin: Origin
    ) -> Optional[ConnectionInterface]:
        """
        Return an available HTTP connection for the given origin,
        if one currently exists in the pool.
        """
        with self._pool_lock:
            for idx, connection in enumerate(self._pool):
                if connection.can_handle_request(origin) and connection.is_available():
                    self._pool.pop(idx)
                    self._pool.insert(0, connection)
                    return connection

        return None

    def _close_one_idle_connection(self) -> bool:
        """
        Close one IDLE connection from the pool, returning `True` if successful,
        and `False` otherwise.
        """
        with self._pool_lock:
            for idx, connection in reversed(list(enumerate(self._pool))):
                closed = connection.attempt_aclose()
                if closed:
                    self._pool.pop(idx)
                    self._pool_semaphore.release()
                    return True
        return False

    def _close_expired_connections(self) -> None:
        """
        Close any connections in the pool that have expired their keepalive.
        """
        with self._pool_lock:
            for idx, connection in reversed(list(enumerate(self._pool))):
                if connection.has_expired():
                    closed = connection.attempt_aclose()
                    if closed:
                        self._pool.pop(idx)
                        self._pool_semaphore.release()

    @property
    def connections(self) -> List[ConnectionInterface]:
        """
        Return a list of the connections currently in the pool.

        For example:

        ```python
        >>> pool.connections
        [
            <HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 6]>,
            <HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 9]> ,
            <HTTPConnection ['http://example.com:80', HTTP/1.1, IDLE, Request Count: 1]>,
        ]
        ```
        """
        return list(self._pool)

    def handle_request(self, request: Request) -> Response:
        """
        Send an HTTP request, and return an HTTP response.

        This is the core implementation that is called into by `.request()` or `.stream()`.
        """
        scheme = request.url.scheme.decode()
        if scheme == "":
            raise UnsupportedProtocol(
                f"Request URL is missing an 'http://' or 'https://' protocol."
            )
        if scheme not in ("http", "https"):
            raise UnsupportedProtocol(
                f"Request URL has an unsupported protocol '{scheme}://'."
            )

        while True:
            existing_connection = self._get_from_pool(request.url.origin)

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
                        timeouts = request.extensions.get("timeout", {})
                        timeout = timeouts.get("pool", None)
                        self._pool_semaphore.acquire(timeout=timeout)
                        break

                # Create a new connection and add it to the pool.
                connection = self.create_connection(request.url.origin)
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
                continue  # pragma: nocover
            except BaseException as exc:
                # If an exception occurs we check if we can release the
                # the connection to the pool.
                self.response_closed(connection)
                raise exc

            # When we return the response, we wrap the stream in a special class
            # that handles notifying the connection pool once the response
            # has been released.
            assert isinstance(response.stream, Iterable)
            return Response(
                status=response.status,
                headers=response.headers,
                content=ConnectionPoolByteStream(response.stream, self, connection),
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
        # exceeding the max_keepalive_connections.
        while len(self._pool) > self._max_keepalive_connections:
            if not self._close_one_idle_connection():
                break  # pragma: nocover

    def close(self) -> None:
        with self._pool_lock:
            for connection in self._pool:
                connection.close()
            self._pool = []

    def __enter__(self) -> "ConnectionPool":
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        self.close()


class ConnectionPoolByteStream:
    """
    A wrapper around the response byte stream, that additionally handles
    notifying the connection pool when the response has been closed.
    """

    def __init__(
        self,
        stream: Iterable[bytes],
        pool: ConnectionPool,
        connection: ConnectionInterface,
    ) -> None:
        self._stream = stream
        self._pool = pool
        self._connection = connection

    def __iter__(self) -> Iterator[bytes]:
        for part in self._stream:
            yield part

    def close(self) -> None:
        try:
            if hasattr(self._stream, "close"):
                self._stream.close()
        finally:
            self._pool.response_closed(self._connection)
