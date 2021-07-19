import pytest
import urllib
from core import (
    AsyncConnectionPool,
    RawURL,
    RawRequest,
)


def parse(url_string: str) -> RawURL:
    parsed = urllib.parse.urlparse(url_string)
    scheme = parsed.scheme.encode("ascii")
    host = parsed.hostname.encode("ascii")
    port = parsed.port
    path = parsed.path or "/"
    target = f"{path}?{parsed.query}".rstrip("?").encode("ascii")
    return RawURL(scheme, host, port, target)


@pytest.mark.trio
async def test_request(httpbin):
    async with AsyncConnectionPool(max_connections=10) as pool:
        url = parse(httpbin.url)
        request = RawRequest(b"GET", url, [(b"Host", url.host)])
        async with await pool.handle_async_request(request) as response:
            assert response.status == 200
