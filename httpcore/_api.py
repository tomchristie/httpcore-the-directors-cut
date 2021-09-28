from ._models import SyncByteStream, Request, Response, URL
from ._sync.connection_pool import ConnectionPool
from typing import Iterator, Union


def request(
    method: Union[bytes, str],
    url: Union[URL, bytes, str],
    *,
    headers: Union[dict, list] = None,
    stream: Iterator[bytes] = None,
    extensions: dict = None
) -> Response:
    """
    Sends an HTTP request, returning the response.

        response = httpcore.request("GET", "https://www.example.com/")

    Arguments:
        method: HTTP method for the request. Typically one of `"GET"`, `"OPTIONS"`,
                `"HEAD"`, `"POST"`, `"PUT"`, `"PATCH"`, or `"DELETE"`.
        url: ...
        headers: HTTP request headers. Either as a dictionary of str/bytes, or as a list of two-tuples of str/bytes.
        stream: The content of the request body.
        extensions: ...

    Returns:
        An instance of `httpcore.Response`.
    """
    with ConnectionPool() as pool:
        return pool.request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
            extensions=extensions,
        )
