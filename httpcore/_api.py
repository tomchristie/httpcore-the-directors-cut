from ._models import SyncByteStream, Request, Response, URL
from ._sync.connection_pool import ConnectionPool
from typing import Iterator, Union


def request(
    method: Union[bytes, str],
    url: Union[URL, bytes, str],
    *,
    headers: Union[dict, list] = None,
    content: Union[bytes, Iterator[bytes]] = None,
    extensions: dict = None
) -> Response:
    """
    Sends an HTTP request, returning the response.

        response = httpcore.request("GET", "https://www.example.com/")

    Arguments:
        method: The HTTP method for the request. Typically one of `"GET"`, `"OPTIONS"`,
                `"HEAD"`, `"POST"`, `"PUT"`, `"PATCH"`, or `"DELETE"`.
        url: ...
        headers: The HTTP request headers. Either as a dictionary of str/bytes, or as a list of two-tuples of str/bytes.
        content: The content of the request body. Either as bytes, or as a bytes iterator.
        extensions: ...

    Returns:
        An instance of `httpcore.Response`.
    """
    with ConnectionPool() as pool:
        return pool.request(
            method=method,
            url=url,
            headers=headers,
            content=content,
            extensions=extensions,
        )
