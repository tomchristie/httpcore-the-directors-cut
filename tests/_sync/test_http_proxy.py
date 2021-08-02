from core import (
    HTTPProxy,
    Origin,
    RawURL,
    RawRequest,
    ByteStream,
)
from core.backends.mock import MockBackend
from typing import List
import pytest
from tests import concurrency



def test_connection_pool_with_keepalive():
    """
    By default HTTP/1.1 requests should be returned to the connection pool.
    """
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPProxy(
        proxy_origin=Origin(scheme=b"http", host=b"localhost", port=8080),
        max_connections=10,
        network_backend=network_backend,
    ) as proxy:
        url = RawURL(b"http", b"example.com", 80, b"/")
        request = RawRequest(b"GET", url, [(b"Host", b"example.com")])

        # Sending an intial request, which once complete will return to the pool, IDLE.
        with proxy.handle_request(request) as response:
            info = proxy.pool_info()
            assert info == [
                "'http://localhost:8080', HTTP/1.1, ACTIVE, Request Count: 1"
            ]
            body = response.stream.read()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = proxy.pool_info()
        assert info == ["'http://localhost:8080', HTTP/1.1, IDLE, Request Count: 1"]
