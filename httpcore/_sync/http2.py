from .._models import ByteStream, Origin, Request, Response
from ..backends.base import NetworkStream
from .._exceptions import LocalProtocolError, RemoteProtocolError
from .interfaces import ConnectionInterface

import functools
import types
import typing

import h2.config
import h2.connection
import h2.events
import h2.settings


def has_body_headers(request: Request) -> bool:
    return any(
        [
            k.lower() == b"content-length" or k.lower() == b"transfer-encoding"
            for k, v in request.headers
        ]
    )


class HTTP2Connection(ConnectionInterface):
    READ_NUM_BYTES = 64 * 1024
    CONFIG = h2.config.H2Configuration(validate_inbound_headers=False)

    def __init__(self, origin: Origin, stream: NetworkStream):
        self._origin = origin
        self._network_stream = stream
        self._h2_state = h2.connection.H2Connection(config=self.CONFIG)
        self._events = {}

    def handle_request(self, request: Request) -> Response:
        self._send_connection_init(request)
        stream_id = self._h2_state.get_next_available_stream_id()

        self._events[stream_id] = []
        self._send_request_headers(request, stream_id=stream_id)
        self._send_request_body(request, stream_id=stream_id)
        status, headers = self._receive_response(request, stream_id=stream_id)

        return Response(
            status=status,
            headers=headers,
            stream=HTTP2ConnectionByteStream(self, request, stream_id=stream_id),
            extensions={"stream_id": stream_id, "http_version": b"HTTP/2"},
        )

    def _send_connection_init(self, request: Request) -> None:
        """
        The HTTP/2 connection requires some initial setup before we can start
        using individual request/response streams on it.
        """
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        # Need to set these manually here instead of manipulating via
        # __setitem__() otherwise the H2Connection will emit SettingsUpdate
        # frames in addition to sending the undesired defaults.
        self._h2_state.local_settings = h2.settings.Settings(
            client=True,
            initial_values={
                # Disable PUSH_PROMISE frames from the server since we don't do anything
                # with them for now.  Maybe when we support caching?
                h2.settings.SettingCodes.ENABLE_PUSH: 0,
                # These two are taken from h2 for safe defaults
                h2.settings.SettingCodes.MAX_CONCURRENT_STREAMS: 100,
                h2.settings.SettingCodes.MAX_HEADER_LIST_SIZE: 65536,
            },
        )

        # Some websites (*cough* Yahoo *cough*) balk at this setting being
        # present in the initial handshake since it's not defined in the original
        # RFC despite the RFC mandating ignoring settings you don't know about.
        del self._h2_state.local_settings[
            h2.settings.SettingCodes.ENABLE_CONNECT_PROTOCOL
        ]

        self._h2_state.initiate_connection()
        self._h2_state.increment_flow_control_window(2 ** 24)
        data_to_send = self._h2_state.data_to_send()
        self._network_stream.write(data_to_send, timeout)

    # Sending the request...

    def _send_request_headers(self, request: Request, stream_id: int) -> None:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        end_stream = not has_body_headers(request)

        # In HTTP/2 the ':authority' pseudo-header is used instead of 'Host'.
        # In order to gracefully handle HTTP/1.1 and HTTP/2 we always require
        # HTTP/1.1 style headers, and map them appropriately if we end up on
        # an HTTP/2 connection.
        authority = [v for k, v in request.headers if k.lower() == b"host"][0]

        headers = [
            (b":method", request.method),
            (b":authority", authority),
            (b":scheme", request.url.scheme),
            (b":path", request.url.target),
        ] + [
            (k.lower(), v)
            for k, v in request.headers
            if k.lower()
            not in (
                b"host",
                b"transfer-encoding",
            )
        ]

        self._h2_state.send_headers(stream_id, headers, end_stream=end_stream)
        self._h2_state.increment_flow_control_window(2 ** 24, stream_id=stream_id)
        data_to_send = self._h2_state.data_to_send()
        self._network_stream.write(data_to_send, timeout)

    def _send_request_body(self, request: Request, stream_id: int) -> None:
        if not has_body_headers(request):
            return

        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("write", None)

        for data in request.stream:
            while data:
                max_flow = self._wait_for_outgoing_flow(request, stream_id)
                chunk_size = min(len(data), max_flow)
                chunk, data = data[:chunk_size], data[chunk_size:]
                self._h2_state.send_data(stream_id, chunk)
                data_to_send = self._h2_state.data_to_send()
                self._network_stream.write(data_to_send, timeout)

        self._h2_state.end_stream(stream_id)
        data_to_send = self._h2_state.data_to_send()
        self._network_stream.write(data_to_send, timeout)

    # Receiving the response...

    def _receive_response(
        self, request: Request, stream_id: int
    ) -> typing.Tuple[int, typing.List[typing.Tuple[bytes, bytes]]]:
        while True:
            event = self._receive_stream_event(request, stream_id)
            if isinstance(event, h2.events.ResponseReceived):
                break

        status_code = 200
        headers = []
        for k, v in event.headers:
            if k == b":status":
                status_code = int(v.decode("ascii", errors="ignore"))
            elif not k.startswith(b":"):
                headers.append((k, v))

        return (status_code, headers)

    def _receive_response_body(
        self, request: Request, stream_id: int
    ) -> typing.Iterator[bytes]:
        while True:
            event = self._receive_stream_event(request, stream_id)
            if isinstance(event, h2.events.DataReceived):
                amount = event.flow_controlled_length
                self._acknowledge_received_data(
                    request, stream_id, amount
                )
                yield event.data
            elif isinstance(event, (h2.events.StreamEnded, h2.events.StreamReset)):
                break

    def _receive_stream_event(
        self, request: Request, stream_id: int
    ) -> h2.events.Event:
        while not self._events.get(stream_id):
            self._receive_events(request)
        return self._events[stream_id].pop(0)

    def _receive_events(self, request: Request) -> None:
        timeouts = request.extensions.get("timeout", {})
        read_timeout = timeouts.get("read", None)
        write_timeout = timeouts.get("write", None)

        data = self._network_stream.read(self.READ_NUM_BYTES, read_timeout)
        if data == b"":
            raise RemoteProtocolError("Server disconnected")

        events = self._h2_state.receive_data(data)
        for event in events:
            event_stream_id = getattr(event, "stream_id", 0)

            if hasattr(event, "error_code"):
                raise RemoteProtocolError(event)

            if event_stream_id in self._events:
                self._events[event_stream_id].append(event)

        data_to_send = self._h2_state.data_to_send()
        self._network_stream.write(data_to_send, write_timeout)

    def _response_closed(self, stream_id: int) -> None:
        del self._events[stream_id]

    def close(self):
        self._network_stream.close()

    # Flow control

    def _wait_for_outgoing_flow(self, request: Request, stream_id: int) -> int:
        """
        Returns the maximum allowable outgoing flow for a given stream.

        If the allowable flow is zero, then waits on the network until
        WindowUpdated frames have increased the flow rate.
        https://tools.ietf.org/html/rfc7540#section-6.9
        """
        local_flow = self._h2_state.local_flow_control_window(stream_id)
        max_frame_size = self._h2_state.max_outbound_frame_size
        flow = min(local_flow, max_frame_size)
        while flow == 0:
            self._receive_events(request)
            local_flow = self._h2_state.local_flow_control_window(stream_id)
            max_frame_size = self._h2_state.max_outbound_frame_size
            flow = min(local_flow, max_frame_size)
        return flow

    def _acknowledge_received_data(
        self, request: Request, stream_id: int, amount: int
    ) -> None:
        timeouts = request.extensions.get("timeout", {})
        timeout = timeouts.get("read", None)

        self._h2_state.acknowledge_received_data(amount, stream_id)
        data_to_send = self._h2_state.data_to_send()
        self._network_stream.write(data_to_send, timeout)

    # These context managers are not used in the standard flow, but are
    # useful for testing or working with connection instances directly.

    def __enter__(self) -> "HTTP2Connection":
        return self

    def __exit__(
        self,
        exc_type: typing.Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: types.TracebackType = None,
    ) -> None:
        self.close()


class HTTP2ConnectionByteStream(ByteStream):
    def __init__(
        self, connection: HTTP2Connection, request: Request, stream_id: int
    ) -> None:
        self._connection = connection
        self._request = request
        self._stream_id = stream_id

    def __iter__(self) -> typing.Iterator[bytes]:
        for chunk in self._connection._receive_response_body(
            self._request, self._stream_id
        ):
            yield chunk

    def close(self) -> None:
        self._connection._response_closed(self._stream_id)
