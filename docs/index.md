# HTTPCore

[![Test Suite](https://github.com/encode/httpcore/workflows/Test%20Suite/badge.svg)](https://github.com/encode/httpcore/actions)
[![Package version](https://badge.fury.io/py/httpcore.svg)](https://pypi.org/project/httpcore/)

> *Do one thing, and do it well.*

The HTTP Core package provides a minimal low-level HTTP client, which does
one thing only. Sending HTTP requests.

It does not provide any high level model abstractions over the API,
does not handle redirects, multipart uploads, building authentication headers,
transparent HTTP caching, URL parsing, session cookie handling,
content or charset decoding, handling JSON, environment based configuration
defaults, or any of that Jazz.

Some things HTTP Core does do:

* Sending HTTP requests.
* Provides both sync and async interfaces.
* Supports HTTP/1.1 and HTTP/2.
* Async backend support for `asyncio`, `trio` and `curio`.
* Automatic connection pooling.
* HTTP(S) proxy support.

## Installation

For HTTP/1.1 only support, install with...

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

---

# API Reference

* Quickstart
    * `httpcore.request()`
    * `httpcore.stream()`
* Requests, Responses, and URLs
    * `httpcore.Request`
    * `httpcore.Response`
    * `httpcore.URL`
* Connection Pools
    * `httpcore.ConnectionPool`
* Proxies
    * `httpcore.HTTPProxy`
* Connections
    * `httpcore.HTTPConnection`
    * `httpcore.HTTP11Connection`
    * `httpcore.HTTP2Connection`
* Async Support
    * `httpcore.AsyncConnectionPool`
    * `httpcore.AsyncHTTPProxy`
    * `httpcore.AsyncHTTPConnection`
    * `httpcore.AsyncHTTP11Connection`
    * `httpcore.AsyncHTTP2Connection`
* Network Backends
    * `httpcore.backends.sync.SyncBackend`
    * `httpcore.backends.auto.AutoBackend`
    * `httpcore.backends.asyncio.AsyncioBackend`
    * `httpcore.backends.trio.TrioBackend`
    * `httpcore.backends.mock.MockBackend`
    * `httpcore.backends.mock.AsyncMockBackend`
    * `httpcore.backends.base.NetworkBackend`
    * `httpcore.backends.base.AsyncNetworkBackend`
