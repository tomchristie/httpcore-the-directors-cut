import pytest
import ssl
from core import (
    AsyncConnectionPool,
    Request,
    URL,
)


@pytest.mark.trio
async def test_request(httpbin):
    async with AsyncConnectionPool() as pool:
        request = Request("GET", httpbin.url)
        async with await pool.handle_async_request(request) as response:
            assert response.status == 200


@pytest.mark.trio
async def test_request(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    async with AsyncConnectionPool(ssl_context=ssl_context) as pool:
        request = Request("GET", httpbin_secure.url)
        async with await pool.handle_async_request(request) as response:
            assert response.status == 200
