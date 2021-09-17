from ..backends.base import AsyncNetworkStream
from .._models import Origin, Request, Response, ByteStream
from .interfaces import AsyncConnectionInterface


class AsyncHTTP2Connection(AsyncConnectionInterface):
    def __init__(
        self, origin: Origin, stream: AsyncNetworkStream, keepalive_expiry: float = None
    ) -> None:
        self._origin = origin
        self._network_stream = stream
        self._keepalive_expiry: Optional[float] = keepalive_expiry

    async def handle_async_request(self, request: Request) -> Response:
        return Response(
            status=200,
            headers={
                'Content-Length': '13',
                'Content-Type': 'text/plain'
            },
            stream=ByteStream(b'Hello, world!')
        )
