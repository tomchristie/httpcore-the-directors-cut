from core import HTTP11Connection, Origin, RawRequest, RawURL, ByteStream, ConnectionNotAvailable
import pytest


@pytest.mark.trio
async def test_http11_connection():
    origin = Origin(b"https", b"example.com", 443)
    async with HTTP11Connection(origin=origin, keepalive_expiry=5.0) as conn:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})
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
    async with HTTP11Connection(origin=origin, keepalive_expiry=5.0) as conn:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})
        async with await conn.handle_request(request) as response:
            with pytest.raises(ConnectionNotAvailable):
                await conn.handle_request(request)


@pytest.mark.trio
async def test_http11_connection_attempt_close():
    """
    A connection can only be closed when it is idle.
    """
    origin = Origin(b"https", b"example.com", 443)
    async with HTTP11Connection(origin=origin, keepalive_expiry=5.0) as conn:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})
        async with await conn.handle_request(request) as response:
            content = await response.stream.aread()
            assert response.status == 200
            assert content == b"Hello, world!"
            assert not await conn.attempt_close()
        assert await conn.attempt_close()
