from core import (
    HTTP11Connection,
    Origin,
    RawRequest,
    RawURL,
    ByteStream,
    ConnectionNotAvailable,
    NetworkStream,
)
import pytest
from typing import List


class MockNetworkStream(NetworkStream):
    def __init__(self, buffer: List[bytes]) -> None:
        self._buffer = buffer

    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        if not self._buffer:
            return b''
        return self._buffer.pop(0)

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        pass

    async def aclose(self) -> None:
        pass


@pytest.mark.trio
async def test_http11_connection():
    origin = Origin(b"https", b"example.com", 443)
    stream = MockNetworkStream([
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: plain/text\r\n",
        b"Content-Length: 13\r\n",
        b"\r\n",
        b"Hello, world!",
    ])
    async with HTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [(b"Host", b"example.com")], ByteStream(), {})
        async with await conn.handle_request(request) as response:
            content = await response.stream.aread()
            assert response.status == 200
            assert content == b"Hello, world!"

        assert conn.get_origin() == origin
        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert repr(conn) == "<HTTP11Connection [IDLE, Request Count: 1]>"


@pytest.mark.trio
async def test_http11_connection_handles_one_active_request():
    """
    Attempting to send a request while one is already in-flight will raise
    a ConnectionNotAvailable exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockNetworkStream([
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: plain/text\r\n",
        b"Content-Length: 13\r\n",
        b"\r\n",
        b"Hello, world!",
    ])
    async with HTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [(b"Host", b"example.com")], ByteStream(), {})
        async with await conn.handle_request(request) as response:
            with pytest.raises(ConnectionNotAvailable):
                await conn.handle_request(request)


@pytest.mark.trio
async def test_http11_connection_attempt_close():
    """
    A connection can only be closed when it is idle.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockNetworkStream([
        b"HTTP/1.1 200 OK\r\n",
        b"Content-Type: plain/text\r\n",
        b"Content-Length: 13\r\n",
        b"\r\n",
        b"Hello, world!",
    ])
    async with HTTP11Connection(
        origin=origin, stream=stream, keepalive_expiry=5.0
    ) as conn:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [(b"Host", b"example.com")], ByteStream(), {})
        async with await conn.handle_request(request) as response:
            content = await response.stream.aread()
            assert response.status == 200
            assert content == b"Hello, world!"
            assert not await conn.attempt_close()
        assert await conn.attempt_close()
