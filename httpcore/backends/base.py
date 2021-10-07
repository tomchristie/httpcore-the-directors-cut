from .._models import Origin

import ssl
import time
import typing


class NetworkStream:
    def read(self, max_bytes: int, timeout: float = None) -> bytes:
        raise NotImplementedError()  # pragma: nocover

    def write(self, buffer: bytes, timeout: float = None) -> None:
        raise NotImplementedError()  # pragma: nocover

    def close(self) -> None:
        raise NotImplementedError()  # pragma: nocover

    def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> "NetworkStream":
        raise NotImplementedError()  # pragma: nocover

    def get_extra_info(self, info: str) -> typing.Any:
        return None  # pragma: nocover


class NetworkBackend:
    def connect(
        self, origin: Origin, timeout: float = None, local_address: str = None
    ) -> NetworkStream:
        raise NotImplementedError()  # pragma: nocover

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)  # pragma: nocover


class AsyncNetworkStream:
    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        raise NotImplementedError()  # pragma: nocover

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        raise NotImplementedError()  # pragma: nocover

    async def aclose(self) -> None:
        raise NotImplementedError()  # pragma: nocover

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: bytes = None,
        timeout: float = None,
    ) -> "AsyncNetworkStream":
        raise NotImplementedError()  # pragma: nocover

    def get_extra_info(self, info: str) -> typing.Any:
        return None  # pragma: nocover


class AsyncNetworkBackend:
    async def connect(
        self, origin: Origin, timeout: float = None, local_address: str = None
    ) -> NetworkStream:
        raise NotImplementedError()  # pragma: nocover

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError()  # pragma: nocover
