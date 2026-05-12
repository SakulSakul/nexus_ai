"""LRU prompt cache. thread-safe."""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Optional


class LRUCache:
    def __init__(self, capacity: int = 256):
        self._capacity = capacity
        self._data: "OrderedDict[str, str]" = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _hash(*parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8"))
            h.update(b"\x00")
        return h.hexdigest()

    def get(self, *parts: str) -> Optional[str]:
        key = self._hash(*parts)
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
            return None

    def set(self, value: str, *parts: str) -> None:
        key = self._hash(*parts)
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._capacity:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
