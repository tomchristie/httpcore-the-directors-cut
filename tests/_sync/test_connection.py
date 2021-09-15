from httpcore import (
    HTTPConnection,
    Origin,
    ByteStream,
    ConnectionNotAvailable,
)
from httpcore.backends.mock import MockBackend
import pytest
from typing import List



def test_http_connection():
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        assert not conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert repr(conn) == "<HTTPConnection [CONNECTING]>"

        with conn.stream("GET", "https://example.com/") as response:
            assert (
                repr(conn)
                == "<HTTPConnection ['https://example.com:443', HTTP/1.1, ACTIVE, Request Count: 1]>"
            )
            response.read()

        assert response.status == 200
        assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<HTTPConnection ['https://example.com:443', HTTP/1.1, IDLE, Request Count: 1]>"
        )



def test_concurrent_requests_not_available_on_http11_connections():
    """
    Attempting to issue a request against an already active HTTP/1.1 connection
    will raise a `ConnectionNotAvailable` exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )

    with HTTPConnection(
        origin=origin, network_backend=network_backend, keepalive_expiry=5.0
    ) as conn:
        with conn.stream("GET", "https://example.com/"):
            with pytest.raises(ConnectionNotAvailable):
                conn.request("GET", "https://example.com/")



def test_request_to_incorrect_origin():
    """
    A connection can only send requests whichever origin it is connected to.
    """
    origin = Origin(b"https", b"example.com", 443)
    network_backend = MockBackend([])
    with HTTPConnection(
        origin=origin, network_backend=network_backend
    ) as conn:
        with pytest.raises(RuntimeError):
            conn.request("GET", "https://other.com/")
