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
        self._semaphore = trio.Semaphore(initial_value=bound, max_value=bound)

    async def acquire_noblock(self) -> bool:
        try:
            self._semaphore.acquire_nowait()
        except trio.WouldBlock:
            return False
        return True

    async def acquire(self) -> None:
        await self._semaphore.acquire()

    async def release(self) -> None:
        self._semaphore.release()

    async def would_block(self) -> bool:
        return self._semaphore.value == 0
