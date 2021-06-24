import trio
from types import TracebackType
from typing import Type


class Lock:
    def __init__(self):
        self._lock = trio.Lock()

    async def __aenter__(self):
        await self._lock.acquire()

    async def __aexit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None
    ):
        self._lock.release()


class Semaphore:
    def __init__(self, bound: int):
        self._limiter = trio.CapacityLimiter(bound)

    async def acquire(self):
        await self._limiter.acquire()

    def release(self):
        self._limiter.release()
