from ..base import Origin


class NetworkStream:
    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        raise NotImplementedError()  # pragma: nocover

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        raise NotImplementedError()  # pragma: nocover

    async def aclose(self) -> None:
        raise NotImplementedError()  # pragma: nocover


class NetworkBackend:
    async def connect(self, origin: Origin) -> NetworkStream:
        raise NotImplementedError()  # pragma: nocover