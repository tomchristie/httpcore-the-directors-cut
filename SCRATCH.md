Working notes...

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
    def connect(self) -> dict:
        ...

    def start_tls(self, stream: NetworkStream) -> dict:
        ...
```
