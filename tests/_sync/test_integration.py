import pytest
import ssl
import urllib
from core import (
    ConnectionPool,
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



def test_request(httpbin):
    with ConnectionPool() as pool:
        url = parse(httpbin.url)
        request = Request("GET", url, headers=[("Host", url.host)])
        with pool.handle_request(request) as response:
            assert response.status == 200



def test_request(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with ConnectionPool(ssl_context=ssl_context) as pool:
        url = parse(httpbin_secure.url)
        request = Request("GET", url, headers=[("Host", url.host)])
        with pool.handle_request(request) as response:
            assert response.status == 200
