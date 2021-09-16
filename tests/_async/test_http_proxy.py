from httpcore import (
    AsyncHTTPProxy,
    Origin,
    AsyncByteStream,
)
from httpcore.backends.mock import AsyncMockBackend
from typing import List
import pytest
import trio as concurrency


@pytest.mark.anyio
async def test_proxy_forwarding():
    """
    Send an HTTP request via a proxy.
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
        # Sending an intial request, which once complete will return to the pool, IDLE.
        async with proxy.stream("GET", "http://example.com/") as response:
            info = [repr(c) for c in proxy.connections]
            assert info == [
                "<AsyncForwardHTTPConnection ['http://localhost:8080', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            await response.aread()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in proxy.connections]
        assert info == [
            "<AsyncForwardHTTPConnection ['http://localhost:8080', HTTP/1.1, IDLE, Request Count: 1]>"
        ]
        assert proxy.connections[0].is_idle()
        assert proxy.connections[0].is_available()
        assert not proxy.connections[0].is_closed()

        # A connection on a forwarding proxy can handle HTTP requests to any host.
        assert proxy.connections[0].can_handle_request(
            Origin(b"http", b"example.com", 80)
        )
        assert proxy.connections[0].can_handle_request(
            Origin(b"http", b"other.com", 80)
        )
        assert not proxy.connections[0].can_handle_request(
            Origin(b"https", b"example.com", 443)
        )
        assert not proxy.connections[0].can_handle_request(
            Origin(b"https", b"other.com", 443)
        )


@pytest.mark.anyio
async def test_proxy_tunneling():
    """
    Send an HTTPS request via a proxy.
    """
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n" b"\r\n",
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
        # Sending an intial request, which once complete will return to the pool, IDLE.
        async with proxy.stream("GET", "https://example.com/") as response:
            info = [repr(c) for c in proxy.connections]
            assert info == [
                "<AsyncTunnelHTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            await response.aread()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in proxy.connections]
        assert info == [
            "<AsyncTunnelHTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        ]
        assert proxy.connections[0].is_idle()
        assert proxy.connections[0].is_available()
        assert not proxy.connections[0].is_closed()

        # A connection on a tunneled proxy can only handle HTTPS requests to the same origin.
        assert not proxy.connections[0].can_handle_request(
            Origin(b"http", b"example.com", 80)
        )
        assert not proxy.connections[0].can_handle_request(
            Origin(b"http", b"other.com", 80)
        )
        assert proxy.connections[0].can_handle_request(
            Origin(b"https", b"example.com", 443)
        )
        assert not proxy.connections[0].can_handle_request(
            Origin(b"https", b"other.com", 443)
        )
