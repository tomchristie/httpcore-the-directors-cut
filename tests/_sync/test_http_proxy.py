from core import (
    HTTPProxy,
    Origin,
    URL,
    Request,
    ByteStream,
)
from core.backends.mock import MockBackend
from typing import List
import pytest
from tests import concurrency



def test_proxy_forwarding():
    """
    Send an HTTP request via a proxy.
    """
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPProxy(
        proxy_origin=Origin(scheme=b"http", host=b"localhost", port=8080),
        max_connections=10,
        network_backend=network_backend,
    ) as proxy:
        url = URL("http://example.com:80/")
        request = Request("GET", url, headers=[("Host", "example.com")])

        # Sending an intial request, which once complete will return to the pool, IDLE.
        with proxy.handle_request(request) as response:
            info = [repr(c) for c in proxy.connections]
            assert info == [
                "<ForwardHTTPConnection ['http://localhost:8080', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in proxy.connections]
        assert info == [
            "<ForwardHTTPConnection ['http://localhost:8080', HTTP/1.1, IDLE, Request Count: 1]>"
        ]



def test_proxy_tunneling():
    """
    Send an HTTPS request via a proxy.
    """
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n" b"\r\n",
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPProxy(
        proxy_origin=Origin(scheme=b"http", host=b"localhost", port=8080),
        max_connections=10,
        network_backend=network_backend,
    ) as proxy:
        url = URL("https://example.com:443/")
        request = Request("GET", url, headers=[("Host", "example.com")])

        # Sending an intial request, which once complete will return to the pool, IDLE.
        with proxy.handle_request(request) as response:
            info = [repr(c) for c in proxy.connections]
            assert info == [
                "<TunnelHTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in proxy.connections]
        assert info == [
            "<TunnelHTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        ]
