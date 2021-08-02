__all__ = [
    'ConnectionNotAvailable',
    'UnsupportedProtocol'
]


class UnsupportedProtocol(Exception):
    pass


class ConnectionNotAvailable(Exception):
    pass
