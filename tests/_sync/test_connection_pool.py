from httpcore import (
    ConnectionPool,
    UnsupportedProtocol,
)
from httpcore.backends.mock import MockBackend
from typing import List
import pytest
from tests import concurrency



def test_connection_pool_with_keepalive():
    """
    By default HTTP/1.1 requests should be returned to the connection pool.
    """
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with ConnectionPool(
        network_backend=network_backend,
    ) as pool:
        # Sending an intial request, which once complete will return to the pool, IDLE.
        with pool.stream("GET", "https://example.com/") as response:
            info = [repr(c) for c in pool.connections]
            assert info == [
                "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in pool.connections]
        assert info == [
            "<HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        ]

        # Sending a second request to the same origin will reuse the existing IDLE connection.
        with pool.stream("GET", "https://example.com/") as response:
            info = [repr(c) for c in pool.connections]
            assert info == [
                "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 2]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in pool.connections]
        assert info == [
            "<HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 2]>"
        ]

        # Sending a request to a different origin will not reuse the existing IDLE connection.
        with pool.stream("GET", "http://example.com/") as response:
            info = [repr(c) for c in pool.connections]
            assert info == [
                "<HTTPConnection ['http://example.com:80', HTTP/1.1, ACTIVE, Request Count: 1]>",
                "<HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 2]>",
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in pool.connections]
        assert info == [
            "<HTTPConnection ['http://example.com:80', HTTP/1.1, IDLE, Request Count: 1]>",
            "<HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 2]>",
        ]



def test_connection_pool_with_close():
    """
    HTTP/1.1 requests that include a 'Connection: Close' header should
    not be returned to the connection pool.
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

    with ConnectionPool(network_backend=network_backend) as pool:
        # Sending an intial request, which once complete will not return to the pool.
        with pool.stream(
            "GET", "https://example.com/", headers={"Connection": "close"}
        ) as response:
            info = [repr(c) for c in pool.connections]
            assert info == [
                "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in pool.connections]
        assert info == []



def test_connection_pool_with_exception():
    """
    HTTP/1.1 requests that result in an exception should not be returned to the
    connection pool.
    """
    network_backend = MockBackend([b"Wait, this isn't valid HTTP!"])

    with ConnectionPool(network_backend=network_backend) as pool:
        # Sending an initial request, which once complete will not return to the pool.
        with pytest.raises(Exception):
            pool.request("GET", "https://example.com/")

        info = [repr(c) for c in pool.connections]
        assert info == []



def test_connection_pool_with_immediate_expiry():
    """
    Connection pools with keepalive_expiry=0.0 should immediately expire
    keep alive connections.
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

    with ConnectionPool(
        keepalive_expiry=0.0,
        network_backend=network_backend,
    ) as pool:
        # Sending an intial request, which once complete will not return to the pool.
        with pool.stream("GET", "https://example.com/") as response:
            info = [repr(c) for c in pool.connections]
            assert info == [
                "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in pool.connections]
        assert info == []



def test_connection_pool_with_no_keepalive_connections_allowed():
    """
    When 'max_keepalive_connections=0' is used, IDLE connections should not
    be returned to the pool.
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

    with ConnectionPool(
        max_keepalive_connections=0, network_backend=network_backend
    ) as pool:
        # Sending an intial request, which once complete will not return to the pool.
        with pool.stream("GET", "https://example.com/") as response:
            info = [repr(c) for c in pool.connections]
            assert info == [
                "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            ]
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"
        info = [repr(c) for c in pool.connections]
        assert info == []



def test_connection_pool_concurrency():
    """
    HTTP/1.1 requests made in concurrency must not ever exceed the maximum number
    of allowable connection in the pool.
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

    def fetch(pool, domain, info_list):
        with pool.stream("GET", f"http://{domain}/") as response:
            info = [repr(c) for c in pool.connections]
            info_list.append(info)
            response.read()

    with ConnectionPool(
        max_connections=1, network_backend=network_backend
    ) as pool:
        info_list = []
        with concurrency.open_nursery() as nursery:
            for domain in ["a.com", "b.com", "c.com", "d.com", "e.com"]:
                nursery.start_soon(fetch, pool, domain, info_list)

        # Check that each time we inspect the connection pool, only a
        # single connection was established.
        for item in info_list:
            assert len(item) == 1
            assert item[0] in [
                "<HTTPConnection ['http://a.com:80', HTTP/1.1, ACTIVE, Request Count: 1]>",
                "<HTTPConnection ['http://b.com:80', HTTP/1.1, ACTIVE, Request Count: 1]>",
                "<HTTPConnection ['http://c.com:80', HTTP/1.1, ACTIVE, Request Count: 1]>",
                "<HTTPConnection ['http://d.com:80', HTTP/1.1, ACTIVE, Request Count: 1]>",
                "<HTTPConnection ['http://e.com:80', HTTP/1.1, ACTIVE, Request Count: 1]>",
            ]



def test_unsupported_protocol():
    with ConnectionPool() as pool:
        with pytest.raises(UnsupportedProtocol):
            pool.request("GET", "ftp://www.example.com/")

        with pytest.raises(UnsupportedProtocol):
            pool.request("GET", "://www.example.com/")
