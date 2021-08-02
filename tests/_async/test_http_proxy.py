from core import (
    AsyncHTTPProxy,
    Origin,
    RawURL,
    AsyncRawRequest,
    AsyncByteStream,
)
from core.backends.mock import AsyncMockBackend
from typing import List
import pytest
import trio as concurrency


@pytest.mark.trio
async def test_connection_pool_with_keepalive():
    """
    By default HTTP/1.1 requests should be returned to the connection pool.
    """
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with AsyncHTTPProxy(
        proxy_origin=Origin(scheme=b"http", host=b"localhost", port=8080),
        max_connections=10,
        network_backend=network_backend,
    ) as proxy:
        url = RawURL(b"http", b"example.com", 80, b"/")
        request = AsyncRawRequest(b"GET", url, [(b"Host", b"example.com")])

        # Sending an intial request, which once complete will return to the pool, IDLE.
        async with await proxy.handle_async_request(request) as response:
            info = await proxy.pool_info()
            assert info == [
                "'http://localhost:8080', HTTP/1.1, ACTIVE, Request Count: 1"
            ]
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await proxy.pool_info()
        assert info == ["'http://localhost:8080', HTTP/1.1, IDLE, Request Count: 1"]
