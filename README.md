Installation:

```shell
$ pip install git+https://github.com/tomchristie/httpcore-the-directors-cut
```

Usage:

```python
import httpcore

pool = httpcore.ConnectionPool()
request = httpcore.Request("GET", "https://www.example.com/")
with pool.handle_request(request) as response:
    response.read()
```

Request instances in httpcore are deliberately simple, and only include the essential information required to represent an HTTP request.

Properties on the request are plain byte-wise representations.

```python
>>> request = httpcore.Request("GET", "https://www.example.com/")
>>> request.method
b"GET"
>>> request.url
httpcore.URL(scheme=b"https", host=b"www.example.com", port=None, target=b"/")
>>> request.headers
[(b'Host', b'www.example.com')]
>>> request.stream
<httpcore.ByteStream [0 bytes]>
```

The interface is liberal in the types that it accepts, but specific in the properties that it uses to represent them. For example, headers may be specified as a dictionary of strings, but internally are represented as a list of `(byte, byte)` tuples.

```python
>>> headers = {"User-Agent": "custom"}
>>> request = httpcore.Request("GET", "https://www.example.com/", headers=headers)
>>> request.headers
[(b'Host', b'www.example.com'), (b"User-Agent", b"custom")]
