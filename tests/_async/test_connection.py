from httpcore import (
    AsyncHTTPConnection,
    Origin,
    AsyncByteStream,
    ConnectionNotAvailable,
)
from httpcore.backends.mock import AsyncMockBackend
import pytest
from typing import List


@pytest.mark.trio
async def test_http_connection():
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        assert not conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert repr(conn) == "<AsyncHTTPConnection [CONNECTING]>"

        async with conn.stream("GET", "https://example.com/") as response:
            assert (
                repr(conn)
                == "<AsyncHTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            )
            await response.aread()

        assert response.status == 200
        assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<AsyncHTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        )


@pytest.mark.trio
async def test_concurrent_requests_not_available_on_http11_connections():
    """
    Attempting to issue a request against an already active HTTP/1.1 connection
    will raise a `ConnectionNotAvailable` exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        async with conn.stream("GET", "https://example.com/"):
            with pytest.raises(ConnectionNotAvailable):
                await conn.request("GET", "https://example.com/")


@pytest.mark.trio
async def test_request_to_incorrect_origin():
    """
    A connection can only send requests whichever origin it is connected to.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = AsyncMockBackend([])
    async with AsyncHTTPConnection(
        origin=origin, network_backend=network_backend
    ) as conn:
        with pytest.raises(RuntimeError):
            await conn.request("GET", "https://other.com/")
