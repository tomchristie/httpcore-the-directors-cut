import pytest
import ssl
from core import (
    ConnectionPool,
    Request,
    URL,
)



def test_request(httpbin):
    with ConnectionPool() as pool:
        request = Request("GET", httpbin.url)
        with pool.handle_request(request) as response:
            assert response.status == 200



def test_request(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with ConnectionPool(ssl_context=ssl_context) as pool:
        request = Request("GET", httpbin_secure.url)
        with pool.handle_request(request) as response:
            assert response.status == 200
