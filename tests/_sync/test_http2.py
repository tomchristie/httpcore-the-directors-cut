from httpcore import (
    HTTP2Connection,
    ByteStream,
    Origin,
    ConnectionNotAvailable,
    RemoteProtocolError,
    LocalProtocolError,
)
from httpcore.backends.mock import MockStream
import hpack
import hyperframe.frame
import pytest



def test_http2_connection():
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
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
            b""
        ]
    )
    with HTTP2Connection(origin=origin, stream=stream) as conn:
        response = conn.request("GET", "https://example.com/")
        assert response.status == 200
        assert response.content == b"Hello, world!"



def test_http2_connection_post_request():
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
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
            b""
        ]
    )
    with HTTP2Connection(origin=origin, stream=stream) as conn:
        response = conn.request(
            "POST",
            "https://example.com/",
            headers={b"content-length": b"17"},
            stream=ByteStream(b'{"data": "upload"}'),
        )
        assert response.status == 200
        assert response.content == b"Hello, world!"



def test_http11_connection_with_remote_protocol_error():
    """
    If a remote protocol error occurs, then no response will be returned,
    and the connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream([b"Wait, this isn't valid HTTP!", b""])
    with HTTP2Connection(origin=origin, stream=stream) as conn:
        with pytest.raises(RemoteProtocolError) as exc_info:
            conn.request("GET", "https://example.com/")



def test_http11_connection_with_stream_cancelled():
    """
    If a remote protocol error occurs, then no response will be returned,
    and the connection will not be reusable.
    """
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
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
            hyperframe.frame.RstStreamFrame(
                stream_id=1, error_code=8
            ).serialize(),
            b""
        ]
    )
    with HTTP2Connection(origin=origin, stream=stream) as conn:
        with pytest.raises(RemoteProtocolError) as exc_info:
            conn.request("GET", "https://example.com/")



def test_http2_connection_with_flow_control():
    origin = Origin(b"https", b"example.com", 443)
    stream = MockStream(
        [
            hyperframe.frame.SettingsFrame().serialize(),
            # Initial available flow: 65,535
            hyperframe.frame.WindowUpdateFrame(stream_id=0, window_increment=10000).serialize(),
            hyperframe.frame.WindowUpdateFrame(stream_id=1, window_increment=10000).serialize(),
            # Available flow: 75,535
            hyperframe.frame.WindowUpdateFrame(stream_id=0, window_increment=10000).serialize(),
            hyperframe.frame.WindowUpdateFrame(stream_id=1, window_increment=10000).serialize(),
            # Available flow: 85,535
            hyperframe.frame.WindowUpdateFrame(stream_id=0, window_increment=10000).serialize(),
            hyperframe.frame.WindowUpdateFrame(stream_id=1, window_increment=10000).serialize(),
            # Available flow: 95,535
            hyperframe.frame.WindowUpdateFrame(stream_id=0, window_increment=10000).serialize(),
            hyperframe.frame.WindowUpdateFrame(stream_id=1, window_increment=10000).serialize(),
            # Available flow: 105,535
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
                stream_id=1, data=b"100,000 bytes received", flags=["END_STREAM"]
            ).serialize(),
            b""
        ]
    )
    with HTTP2Connection(origin=origin, stream=stream) as conn:
        response = conn.request(
            "POST",
            "https://example.com/",
            headers={b"content-length": b"100000"},
            stream=ByteStream(b'x' * 100000)
        )
        assert response.status == 200
        assert response.content == b"100,000 bytes received"
