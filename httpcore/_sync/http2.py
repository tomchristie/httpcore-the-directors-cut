from ..backends.base import NetworkStream
from .._models import Origin, Request, Response, ByteStream
from .interfaces import ConnectionInterface


class HTTP2Connection(ConnectionInterface):
    def __init__(
        self, origin: Origin, stream: NetworkStream, keepalive_expiry: float = None
    ) -> None:
        self._origin = origin
        self._network_stream = stream
        self._keepalive_expiry: Optional[float] = keepalive_expiry

    def handle_request(self, request: Request) -> Response:
        return Response(
            status=200,
            headers={
                'Content-Length': '13',
                'Content-Type': 'text/plain'
            },
            stream=ByteStream(b'Hello, world!')
        )
