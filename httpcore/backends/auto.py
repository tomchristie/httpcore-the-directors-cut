import sniffio

from .base import AsyncNetworkStream, AsyncNetworkBackend
from .._models import Origin


class AutoBackend(AsyncNetworkBackend):
    async def _init_backend(self) -> None:
        if not (hasattr(self, "_backend")):
            backend = sniffio.current_async_library()
            if backend == "trio":
                from .trio import TrioBackend

                self._backend = TrioBackend()
            else:
                from .asyncio import AsyncIOBackend

                self._backend = AsyncIOBackend()

    async def connect(
        self, origin: Origin, timeout: float = None, local_address: str = None
    ) -> AsyncNetworkStream:
        await self._init_backend()
        return await self._backend.connect(
            origin, timeout=timeout, local_address=local_address
        )

    async def sleep(self, seconds: float) -> None:  # pragma: nocover
        await self._init_backend()
        return await self._backend.sleep(seconds)
