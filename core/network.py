class NetworkStream:
    async def read(self, max_bytes: int, timeout: float = None) -> bytes:
        pass

    async def write(self, buffer: bytes, timeout: float = None) -> None:
        pass

    async def aclose(self) -> None:
        pass
