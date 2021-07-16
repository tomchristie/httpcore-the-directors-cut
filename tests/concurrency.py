from typing import Iterator, Dict, List, Optional, Type
from types import TracebackType
import threading


class Nursery:
    def __init__(self) -> None:
        self._threads = []

    def __enter__(self) -> "Nursery":
        return self

    def __exit__(
        self,
        exc_type: Type[BaseException] = None,
        exc_value: BaseException = None,
        traceback: TracebackType = None,
    ) -> None:
        for thread in self._threads:
            thread.start()
        for thread in self._threads:
            thread.join()

    def start_soon(self, func, *args):
        thread = threading.Thread(target=func, args=args)
        self._threads.append(thread)


def open_nursery() -> Nursery:
    return Nursery()
