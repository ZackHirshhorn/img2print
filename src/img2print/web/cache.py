"""A small thread-safe LRU cache with a memory budget, for uploads and built models."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any


class Cache:
    """Keeps the most recently used items until their total size passes max_bytes.

    Items unused for ttl seconds are dropped too. Sizes are given by the caller.
    """

    def __init__(self, max_bytes: int, ttl: float = 3600.0):
        self.max_bytes = max_bytes
        self.ttl = ttl
        self._items: OrderedDict[str, tuple[Any, int, float]] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, key: str, value: Any, size: int) -> None:
        with self._lock:
            self._items.pop(key, None)
            self._items[key] = (value, size, time.monotonic())
            self._evict()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                return None
            value, size, used = item
            if time.monotonic() - used > self.ttl:
                del self._items[key]
                return None
            self._items[key] = (value, size, time.monotonic())
            self._items.move_to_end(key)
            return value

    def __len__(self) -> int:
        return len(self._items)

    @property
    def size(self) -> int:
        return sum(s for _, s, _ in self._items.values())

    def _evict(self) -> None:
        now = time.monotonic()
        for key in [k for k, (_, _, used) in self._items.items() if now - used > self.ttl]:
            del self._items[key]
        total = self.size
        # Always keep the newest item, even when it alone is over budget.
        while total > self.max_bytes and len(self._items) > 1:
            _, (_, size, _) = self._items.popitem(last=False)
            total -= size
