import core._models as httpcore
import pytest
from typing import AsyncIterator, Iterator, List


def test_url():
    url = httpcore.URL("https://www.example.com/")
    assert url == httpcore.URL(
        scheme="https", host="www.example.com", port=None, target="/"
    )
    assert bytes(url) == b"https://www.example.com/"


def test_url_with_port():
    url = httpcore.URL("https://www.example.com:443/")
    assert url == httpcore.URL(
        scheme="https", host="www.example.com", port=443, target="/"
    )
    assert bytes(url) == b"https://www.example.com:443/"


def test_url_cannot_include_unicode_strings():
    """
    URLs instantiated with strings outside of the plain ASCII range are disallowed,
    but the explicit for allows for these ambiguous cases to be precisely expressed.
    """
    with pytest.raises(RuntimeError):
        httpcore.URL("https://www.example.com/☺")

    httpcore.URL(scheme=b"https", host=b"www.example.com", target="/☺".encode("utf-8"))


def test_request():
    url = httpcore.URL("https://www.example.com/")
    request = httpcore.Request("GET", url)
    assert request.method == b"GET"
    assert request.url == url
    assert request.extensions == {}
    assert repr(request) == "<Request [b'GET']>"
    assert repr(request.stream) == "<ByteStream [0 bytes]>"


def test_response():
    response = httpcore.Response(200)
    assert response.status == 200
    assert response.headers == []
    assert response.extensions == {}
    assert repr(response) == "<Response [200]>"
    assert repr(response.stream) == "<ByteStream [0 bytes]>"


# Tests for reading and streaming sync byte streams...


class MockSyncByteStream(httpcore.SyncByteStream):
    def __init__(self, chunks: List[bytes]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        for chunk in self._chunks:
            yield chunk


def test_response_sync_read():
    stream = MockSyncByteStream([b"Hello, ", b"world!"])
    response = httpcore.Response(200, stream=stream)
    assert response.read() == b"Hello, world!"
    assert response.content == b"Hello, world!"


def test_response_sync_streaming():
    stream = MockSyncByteStream([b"Hello, ", b"world!"])
    with httpcore.Response(200, stream=stream) as response:
        content = b"".join([chunk for chunk in response.iter_stream()])
    assert content == b"Hello, world!"

    # We streamed the response rather than reading it, so .content is not available.
    with pytest.raises(RuntimeError):
        response.content

    # Once we've streamed the response, we can't access the stream again.
    with pytest.raises(RuntimeError):
        for chunk in response.iter_stream():
            pass


# Tests for reading and streaming async byte streams...


class MockAsyncByteStream(httpcore.AsyncByteStream):
    def __init__(self, chunks: List[bytes]) -> None:
        self._chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk


@pytest.mark.trio
async def test_response_async_read():
    stream = MockAsyncByteStream([b"Hello, ", b"world!"])
    response = httpcore.Response(200, stream=stream)
    assert await response.aread() == b"Hello, world!"
    assert response.content == b"Hello, world!"


@pytest.mark.trio
async def test_response_async_streaming():
    stream = MockAsyncByteStream([b"Hello, ", b"world!"])
    async with httpcore.Response(200, stream=stream) as response:
        content = b"".join([chunk async for chunk in response.aiter_stream()])
    assert content == b"Hello, world!"

    # We streamed the response rather than reading it, so .content is not available.
    with pytest.raises(RuntimeError):
        response.content

    # Once we've streamed the response, we can't access the stream again.
    with pytest.raises(RuntimeError):
        async for chunk in response.aiter_stream():
            pass
