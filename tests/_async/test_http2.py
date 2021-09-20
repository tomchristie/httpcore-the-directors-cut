from httpcore import (
    AsyncHTTP2Connection,
    ByteStream,
    Origin,
    ConnectionNotAvailable,
    RemoteProtocolError,
    LocalProtocolError,
)
from httpcore.backends.mock import AsyncMockStream
import hpack
import hyperframe.frame
import pytest


@pytest.mark.anyio
async def test_http2_connection():
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(
                stream_id=1, data=b"Hello, world!", flags=["END_STREAM"]
            ).serialize(),
        ]
    )
    async with AsyncHTTP2Connection(origin=origin, stream=stream) as conn:
        response = await conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"


@pytest.mark.anyio
async def test_http2_connection_post_request():
    origin = Origin(b"https", b"example.com", 443)
    stream = AsyncMockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            hyperframe.frame.HeadersFrame(
                stream_id=1,
                data=hpack.Encoder().encode(
                    [
                        (b":status", b"200"),
                        (b"content-type", b"plain/text"),
                    ]
                ),
                flags=["END_HEADERS"],
            ).serialize(),
            hyperframe.frame.DataFrame(
                stream_id=1, data=b"Hello, world!", flags=["END_STREAM"]
            ).serialize(),
        ]
    )
    async with AsyncHTTP2Connection(origin=origin, stream=stream) as conn:
        response = await conn.request(
            "POST",
            "https://example.com/",
            headers={b"content-length": b"17"},
            stream=ByteStream(b'{"data": "upload"}'),
        )
        assert response.status == 200
        assert response.content == b"Hello, world!"
