from core import (
    HTTP11Connection,
    Origin,
    Request,
    URL,
    ConnectionNotAvailable,
)
from core.backends.mock import MockStream
import pytest
from typing import List


def test_http11_connection():
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    with HTTP11Connection(origin=origin, stream=stream, keepalive_expiry=5.0) as conn:
        request = Request("GET", "https://example.com/")
        with conn.handle_request(request) as response:
            response.read()
            assert response.status == 200
            assert response.content == b"Hello, world!"

        assert conn.is_idle()
        assert not conn.is_closed()
        assert conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<HTTP11Connection ['https://example.com:443', IDLE, Request Count: 1]>"
        )


def test_http11_connection_unread_response():
    """
    If the client releases the response without reading it to termination,
    then the connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    with HTTP11Connection(origin=origin, stream=stream, keepalive_expiry=5.0) as conn:
        request = Request("GET", "https://example.com/")
        with conn.handle_request(request) as response:
            assert response.status == 200

        assert not conn.is_idle()
        assert conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<HTTP11Connection ['https://example.com:443', CLOSED, Request Count: 1]>"
        )


def test_http11_connection_with_network_error():
    """
    If a network error occurs, then no response will be returned, and the
    connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream([b"Wait, this isn't valid HTTP!"])
    with HTTP11Connection(origin=origin, stream=stream, keepalive_expiry=5.0) as conn:
        request = Request("GET", "https://example.com/")
        with pytest.raises(Exception):
            conn.handle_request(request)

        assert not conn.is_idle()
        assert conn.is_closed()
        assert not conn.is_available()
        assert not conn.has_expired()
        assert (
            repr(conn)
            == "<HTTP11Connection ['https://example.com:443', CLOSED, Request Count: 1]>"
        )


def test_http11_connection_handles_one_active_request():
    """
    Attempting to send a request while one is already in-flight will raise
    a ConnectionNotAvailable exception.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    with HTTP11Connection(origin=origin, stream=stream, keepalive_expiry=5.0) as conn:
        request = Request("GET", "https://example.com/")
        with conn.handle_request(request) as response:
            with pytest.raises(ConnectionNotAvailable):
                conn.handle_request(request)


def test_http11_connection_attempt_close():
    """
    A connection can only be closed when it is idle.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
        [
            b"HTTP/1.1 200 OK\r\n",
            b"Content-Type: plain/text\r\n",
            b"Content-Length: 13\r\n",
            b"\r\n",
            b"Hello, world!",
        ]
    )
    with HTTP11Connection(origin=origin, stream=stream, keepalive_expiry=5.0) as conn:
        request = Request("GET", "https://example.com/")
        with conn.handle_request(request) as response:
            response.read()
            assert response.status == 200
            assert response.content == b"Hello, world!"
            assert not conn.attempt_aclose()
        assert conn.attempt_aclose()


def test_request_to_incorrect_origin():
    """
    A connection can only send requests whichever origin it is connected to.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream([])
    with HTTP11Connection(origin=origin, stream=stream) as conn:
        request = Request("GET", "https://other.com/")
        with pytest.raises(RuntimeError):
            conn.handle_request(request)
