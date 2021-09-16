from .base import AsyncNetworkStream, AsyncNetworkBackend
from .._models import Origin


class AutoBackend(AsyncNetworkBackend):
    def __init__(self, ssl_context: ssl.SSLContext = None) -> None:
        self._ssl_context = ssl_context

    async def _init_backend(self) -> None:
        if not (hasattr(self, "_backend")):
            from .trio import TrioBackend

            self._backend = TrioBackend(ssl_context=self._ssl_context)

    async def connect(self, origin: Origin) -> AsyncNetworkStream:
        await self._init_backend()
        return await self._backend.connect(origin)
