import ssl

import sniffio

from .base import AsyncNetworkStream, AsyncNetworkBackend
from .._models import Origin


class AutoBackend(AsyncNetworkBackend):
    def __init__(self, ssl_context: ssl.SSLContext = None) -> None:
        self._ssl_context = ssl_context

    async def _init_backend(self) -> None:
        if not (hasattr(self, "_backend")):
            backend = sniffio.current_async_library()
            if backend == "trio":
                from .trio import TrioBackend
                self._backend = TrioBackend(ssl_context=self._ssl_context)
            else:
                from .asyncio import AsyncIOBackend
                self._backend = AsyncIOBackend(ssl_context=self._ssl_context)

    async def connect(
        self, origin: Origin, timeout: float = None
    ) -> AsyncNetworkStream:
        await self._init_backend()
        return await self._backend.connect(origin, timeout=timeout)
