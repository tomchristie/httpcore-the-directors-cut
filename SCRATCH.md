Working notes...

Change pool, so that it is a plain ol' list...

```python
[
    <HTTPConnection "https://www.example.com:443", OPENING, Request Count: 1>
    <HTTPConnection "http://www.example.com:80", HTTP/1.1, ACTIVE, Request Count: 6>
    <HTTPConnection "http://www.example.com:80", HTTP/1.1, IDLE, Request Count: 1>
    <HTTPConnection "http://www.example.com:80", HTTP/1.1, IDLE, Request Count: 3>
]
```

* Always select the most recent available connection first.
* Always expire the oldest connections first.
* Push a connection to the top of the stack whenever a request is sent on it.

Change exception to `ConnectionNotAvailable`.

* Guard against multiple closes on a stream.
* RuntimeError if making a request against a pool that has been closed.
* RuntimeError if making a request against a connection, with an invalid origin.

```python
class ForwardProxy:
    def handle_request(self, request: RawRequest) -> RawResponse:
        proxy_url = RawURL(
            scheme=self.proxy_scheme,
            host=self.proxy_host,
            port=self.proxy_port,
            target=bytes(request.url)
        )
        proxy_request = RawRequest(
            method=request.method,
            url=proxy_url,
            headers=self.proxy_headers + request.headers,
            stream=request.stream
            extensions=request.extensions
        )
        return self._connection.handle_request(proxy_request)

    def close(self):
        self._connection.close()
```


```python
class TunnelProxy:
    def handle_request(self, request: RawRequest) -> RawResponse:
        with self._connect_lock:
            if self._connection is None:
                proxy_url = RawURL(
                    scheme=self.proxy_scheme,
                    host=self.proxy_host,
                    port=self.proxy_port,
                    target=request.url.netloc
                )
                proxy_request = RawRequest(
                    method="CONNECT",
                    url=proxy_url,
                    headers=self.proxy_headers,
                )
                connection = HTTPConnection()
                response = connection.handle_request(proxy_request)
                stream = response.extensions["stream"]
                stream = stream.start_tls()
                self._connection = HTTPConnection(stream=stream)
        return self._connection.handle_request(request)

    def close(self):
        self._connection.close()
```


```python
class NetworkStream:
    def read(self, max_bytes: int, timeout: float = None) -> bytes:
        ...

    def write(self, buffer: bytes, timeout: float = None) -> None:
        ...

    def close(self) -> None:
        ...
```


```python
class NetworkConnector:
    def connect(self, origin: Origin) -> dict:
        ...

    def start_tls(self, stream: NetworkStream) -> dict:
        ...
```

https://http2-explained.haxx.se
https://http3-explained.haxx.se
