from .._models import AsyncByteStream, Origin, Request, Response, URL
from typing import Dict, List, Tuple, Union


HeadersAsList = List[Tuple[Union[bytes, str], Union[bytes, str]]]
HeadersAsDict = Dict[Union[bytes, str], Union[bytes, str]]


class AsyncRequestInterface:
    async def request(
        self,
        method: Union[bytes, str],
        url: Union[URL, bytes, str],
        *,
        headers: Union[HeadersAsList, HeadersAsDict] = None,
        stream: AsyncByteStream = None,
        extensions: dict = None
    ):
        request = Request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
            extensions=extensions,
        )
        async with await self.handle_async_request(request) as response:
            await response.aread()
        return response

    async def handle_async_request(self, request: Request) -> Response:
        raise NotImplementedError()  # pragma: nocover


class AsyncConnectionInterface(AsyncRequestInterface):
    async def attempt_aclose(self) -> bool:
        raise NotImplementedError()  # pragma: nocover

    async def aclose(self) -> None:
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
