from contextlib import contextmanager
from .._models import SyncByteStream, Origin, Request, Response, URL
from typing import Dict, List, Tuple, Union


HeadersAsList = List[Tuple[Union[bytes, str], Union[bytes, str]]]
HeadersAsDict = Dict[Union[bytes, str], Union[bytes, str]]


class RequestInterface:
    def request(
        self,
        method: Union[bytes, str],
        url: Union[URL, bytes, str],
        *,
        headers: Union[HeadersAsList, HeadersAsDict] = None,
        stream: SyncByteStream = None,
        extensions: dict = None
    ):
        request = Request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
            extensions=extensions,
        )
        response = self.handle_request(request)
        try:
            response.read()
        finally:
            response.close()
        return response

    @contextmanager
    def stream(
        self,
        method: Union[bytes, str],
        url: Union[URL, bytes, str],
        *,
        headers: Union[HeadersAsList, HeadersAsDict] = None,
        stream: SyncByteStream = None,
        extensions: dict = None
    ):
        request = Request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
            extensions=extensions,
        )
        response = self.handle_request(request)
        try:
            yield response
        finally:
            response.close()

    def handle_request(self, request: Request) -> Response:
        raise NotImplementedError()  # pragma: nocover


class ConnectionInterface(RequestInterface):
    def attempt_aclose(self) -> bool:
        raise NotImplementedError()  # pragma: nocover

    def close(self) -> None:
        raise NotImplementedError()  # pragma: nocover

    def info(self) -> str:
        raise NotImplementedError()  # pragma: nocover

    def can_handle_request(self, origin: Origin) -> bool:
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
