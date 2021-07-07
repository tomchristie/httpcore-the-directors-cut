from typing import Any, AsyncIterator, List, Tuple


class Origin:
    def __init__(self, scheme: bytes, host: bytes, port: int) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port

    def __hash__(self) -> int:
        origin_tuple = (self.scheme, self.host, self.port)
        return hash(origin_tuple)

    def __eq__(self, other: Any) -> bool:
        return (
            isinstance(other, Origin)
            and self.scheme == other.scheme
            and self.host == other.host
            and self.port == other.port
        )

    def __str__(self):
        scheme = self.scheme.decode("ascii")
        host = self.host.decode("ascii")
        port = str(self.port)
        return f"{scheme}://{host}:{port}"


class RawURL:
    def __init__(self, scheme: bytes, host: bytes, port: int, target: bytes) -> None:
        self.scheme = scheme
        self.host = host
        self.port = port
        self.target = target

    @property
    def origin(self) -> Origin:
        return Origin(self.scheme, self.host, self.port)


class ConnectionNotAvailable(Exception):
    pass
