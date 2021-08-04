import pytest
import ssl
import urllib
from core import (
    AsyncConnectionPool,
    Request,
    URL,
)


def parse(url_string: str) -> URL:
    parsed = urllib.parse.urlparse(url_string)
    scheme = parsed.scheme.encode("ascii")
    host = parsed.hostname.encode("ascii")
    port = parsed.port
    path = parsed.path or "/"
    target = f"{path}?{parsed.query}".rstrip("?").encode("ascii")
    return URL(scheme=scheme, host=host, port=port, target=target)


@pytest.mark.trio
async def test_request(httpbin):
    async with AsyncConnectionPool() as pool:
        url = parse(httpbin.url)
        request = Request("GET", url, headers=[("Host", url.host)])
        async with await pool.handle_async_request(request) as response:
            assert response.status == 200


@pytest.mark.trio
async def test_request(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    async with AsyncConnectionPool(ssl_context=ssl_context) as pool:
        url = parse(httpbin_secure.url)
        request = Request("GET", url, headers=[("Host", url.host)])
        async with await pool.handle_async_request(request) as response:
            assert response.status == 200
