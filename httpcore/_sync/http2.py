from .._models import ByteStream, Request, Response
from .interfaces import ConnectionInterface


class HTTP2Connection(ConnectionInterface):
    def handle_request(self, request: Request) -> Response:
        return Response(
            status=200,
            headers=[(b"Content-Length", b"13")],
            stream=ByteStream(b"Hello, world.")
        )
