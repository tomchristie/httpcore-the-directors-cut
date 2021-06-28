from core import ConnectionPool, RawURL, RawRequest, ByteStream
import pytest


@pytest.mark.trio
async def test_connection_pool_with_keepalive():
    """
    By default HTTP/1.1 requests should be returned to the connection pool.
    """
    async with ConnectionPool(max_connections=1, max_keepalive_connections=1) as pool:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})

        # Sending an intial request, which once complete will return to the pool, IDLE.
        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE, Request Count: 1"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {"https://example.com:443": ["HTTP/1.1, IDLE, Request Count: 1"]}

        # Sending a second request to the same origin will reuse the existing IDLE connection.
        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE, Request Count: 2"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {"https://example.com:443": ["HTTP/1.1, IDLE, Request Count: 2"]}

        # Sending a request to a different origin will not reuse the existing IDLE connection.
        url = RawURL(b"http", b"example.com", 80, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})

        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"http://example.com:80": ["HTTP/1.1, ACTIVE, Request Count: 1"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {"http://example.com:80": ["HTTP/1.1, IDLE, Request Count: 1"]}


@pytest.mark.trio
async def test_connection_pool_with_close():
    """
    HTTP/1.1 requests that include a 'Connection: Close' header should
    not be returned to the connection pool.
    """
    async with ConnectionPool(max_connections=1, max_keepalive_connections=1) as pool:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [(b"connection", b"close")], ByteStream(), {})

        # Sending an intial request, which once complete will not return to the pool.
        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE, Request Count: 1"]}
            body = await response.stream.aread()

        assert response.status == 200
        assert body == b"Hello, world!"
        info = await pool.pool_info()
        assert info == {}


@pytest.mark.trio
async def test_connection_pool_with_no_keepalive_connections_allowed():
    """
    When 'max_keepalive_connections=0' is used, IDLE connections should not
    be returned to the pool.
    """
    async with ConnectionPool(max_connections=1, max_keepalive_connections=0) as pool:
        url = RawURL(b"https", b"example.com", 443, b"/")
        request = RawRequest(b"GET", url, [], ByteStream(), {})

        # Sending an intial request, which once complete will not return to the pool.
        async with await pool.handle_request(request) as response:
            info = await pool.pool_info()
            assert info == {"https://example.com:443": ["HTTP/1.1, ACTIVE, Request Count: 1"]}
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
