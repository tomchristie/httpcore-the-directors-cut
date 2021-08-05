from ._models import SyncByteStream, Request, Response, URL
from ._sync.connection_pool import ConnectionPool
from typing import Dict, List, Tuple, Union


HeadersAsList = List[Tuple[Union[bytes, str], Union[bytes, str]]]
HeadersAsDict = Dict[Union[bytes, str], Union[bytes, str]]


def request(
    method: Union[bytes, str],
    url: Union[URL, bytes, str],
    *,
    headers: Union[HeadersAsList, HeadersAsDict] = None,
    stream: SyncByteStream = None,
    extensions: dict = None
) -> Response:
    with ConnectionPool() as pool:
        return pool.request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
            extensions=extensions
        )
