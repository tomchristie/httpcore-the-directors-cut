## Quickstart

Installation:

```shell
$ pip install git+https://github.com/tomchristie/httpcore-the-directors-cut
```

Send an HTTP request:

```python
import httpcore

response = httpcore.request("GET", "https://www.example.com/")

print(response)
# <Response [200]>
print(response.status)
# 200
print(response.headers)
# [(b'Accept-Ranges', b'bytes'), (b'Age', b'557328'), (b'Cache-Control', b'max-age=604800'), ...]
print(response.content)
# b'<!doctype html>\n<html>\n<head>\n<title>Example Domain</title>\n\n<meta charset="utf-8"/>\n ...'
```

## Connection pools

The top-level `httpcore.request()` function is provided for convenience. In practice whenever you're working with `httpcore` you'll want to use the connection pooling functionality that it provides.

```python
import httpcore

pool = httpcore.ConnectionPool()
response = pool.request("GET", "https://www.example.com/")
```

The huge benefit that connection pools provide is that once you've sent an initial request, the connection to the host can usually be reused by subsequent requests.

This requires less resources that having to reconnect on each request, and is far quicker for the following requests.

```python
import httpcore
import time

pool = httpcore.ConnectionPool()
for index in range(5):
    started = time.perf_counter()
    response = pool.request("GET", "https://www.example.com/")
    elapsed = time.perf_counter() - started
    print(f"Request {index}: {elapsed:.3f} seconds.")

# Will print something similar to this:
#
# Request 0: 0.471 seconds.
# Request 1: 0.114 seconds.
# Request 2: 0.115 seconds.
# Request 3: 0.112 seconds.
# Request 4: 0.112 seconds.
```

## Requests, responses, and URLs

Request instances in `httpcore` are deliberately simple, and only include the essential information required to represent an HTTP request.

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
