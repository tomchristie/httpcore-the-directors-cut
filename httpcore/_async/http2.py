from .._models import ByteStream, Request, Response
from .interfaces import AsyncConnectionInterface


class AsyncHTTP2Connection(AsyncConnectionInterface):
    async def handle_async_request(self, request: Request) -> Response:
        return Response(
            status=200,
            headers=[(b"Content-Length", b"13")],
            stream=ByteStream(b"Hello, world.")
        )
