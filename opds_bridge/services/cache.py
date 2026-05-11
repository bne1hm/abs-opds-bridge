import threading
import time
from typing import Any, Dict, Optional, Tuple


class Cache:
    def __init__(self, default_ttl: int = 60, maxsize: int = 512):
        if maxsize <= 0:
            raise ValueError(f"maxsize must be > 0, got {maxsize}")
        self._lock = threading.Lock()
        self._store: Dict[str, Tuple[float, Any]] = {}
        self.default_ttl = default_ttl
        self.maxsize = maxsize

    def _evict_expired(self):
        now = time.time()
        expired = [k for k, (exp, _) in self._store.items() if now > exp]
        for k in expired:
            self._store.pop(k, None)

    def get(self, key: str):
        with self._lock:
            rec = self._store.get(key)
            if not rec:
                return None
            expires, value = rec
            if time.time() > expires:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        ttl = ttl if ttl is not None else self.default_ttl
        with self._lock:
            if key in self._store:
                self._store[key] = (time.time() + ttl, value)
                return
            if len(self._store) >= self.maxsize:
                self._evict_expired()
            if len(self._store) >= self.maxsize:
                oldest_key = min(self._store, key=lambda k: self._store[k][0])
                self._store.pop(oldest_key, None)
            self._store[key] = (time.time() + ttl, value)
