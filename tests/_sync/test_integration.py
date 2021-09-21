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



def test_extra_info(httpbin_secure):
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    with ConnectionPool(ssl_context=ssl_context) as pool:
        with pool.stream("GET", httpbin_secure.url) as response:
            assert response.status == 200
            stream = response.extensions["stream"]

            ssl_object = stream.get_extra_info("ssl_object")
            assert ssl_object.version() == "TLSv1.3"

            local_addr = stream.get_extra_info("client_addr")
            assert local_addr[0] == "127.0.0.1"

            remote_addr = stream.get_extra_info("server_addr")
            assert "https://%s:%d" % remote_addr == httpbin_secure.url

            invalid = stream.get_extra_info("invalid")
            assert invalid is None
