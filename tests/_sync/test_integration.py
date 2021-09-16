import pytest
import ssl
from httpcore import (
    ConnectionPool,
    Request,
    URL,
)



def test_request(httpbin):
    with ConnectionPool() as pool:
        response = pool.request("GET", httpbin.url)
        assert response.status == 200



def test_ssl_request(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with ConnectionPool(ssl_context=ssl_context) as pool:
        response = pool.request("GET", httpbin_secure.url)
        assert response.status == 200
