from core import ConnectionPool, RawURL, RawRequest, ByteStream
import pytest


@pytest.mark.trio
async def test_connection_pool_with_keepalive():
    async with ConnectionPool(max_connections=1, max_keepalive_connections=1) as pool:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})

        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {"https://example.com:443": ["HTTP/1.1, IDLE"]}

        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {"https://example.com:443": ["HTTP/1.1, IDLE"]}


@pytest.mark.trio
async def test_connection_pool_with_close():
    async with ConnectionPool(max_connections=1, max_keepalive_connections=1) as pool:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [(b"connection", b"close")], ByteStream(), {})

        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {}


@pytest.mark.trio
async def test_connection_pool_with_no_keepalive_connections_allowed():
    async with ConnectionPool(max_connections=1, max_keepalive_connections=0) as pool:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})

        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {}



# @pytest.mark.trio
# async def test_request_with_connection_keepalive():
#     pool = ConnectionPool(max_connections=10)
#     assert pool.info() == {}
#
#     url = RawURL(b"https", b"example.com", 443, b"/")
#     request = RawRequest(b"GET", url, [], ByteStream(), {})
#
#     async with await pool.handle_request(request) as response:
#         assert pool.info() == {"https://example.com:443": ["HTTP/1.1, ACTIVE"]}
#
#     assert pool.info() == {"https://example.com:443": ["HTTP/1.1, IDLE"]}
#
#
# @pytest.mark.trio
# async def test_request_with_connection_close():
#     pool = ConnectionPool(max_connections=10)
#     assert pool.info() == {}
#
#     url = RawURL(b"https", b"example.com", 443, b"/")
#     request = RawRequest(b"GET", url, [], ByteStream(), {})
#
#     async with await pool.handle_request(request) as response:
#         assert pool.info() == {"https://example.com:443": ["HTTP/1.1, ACTIVE"]}
#
#     assert pool.info() == {}
