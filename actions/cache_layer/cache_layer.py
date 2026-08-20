import asyncio
import time
from collections import OrderedDict
from typing import Any, Optional, Dict
from actions.cache_layer.schemas import CacheStats

class CacheLayer:
    def __init__(self, max_size: int = 1000, metrics=None):
        self.max_size = max_size
        self.cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.lock = asyncio.Lock()
        # Centralni observability sink — cache NE vzdržuje lastnega loggerja,
        # ampak svoje metrike delegira v MetricsRegistry (če je podan).
        self.metrics = metrics

    async def _record_metric(self, name: str) -> None:
        """Delegira števec v centralni metrics sink, če obstaja."""
        if self.metrics is not None:
            await self.metrics.record_counter(name, 1.0)

    async def set(self, key: str, value: Any, ttl_seconds: Optional[float] = None) -> None:
        async with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            else:
                if len(self.cache) >= self.max_size:
                    self.cache.popitem(last=False)  # Odstrani najstarejši element (LRU)
                    self.evictions += 1
                    await self._record_metric("cache_evictions")

            expires_at = time.time() + ttl_seconds if ttl_seconds else None
            self.cache[key] = {"value": value, "expires_at": expires_at}

    async def get(self, key: str) -> Optional[Any]:
        async with self.lock:
            if key not in self.cache:
                self.misses += 1
                await self._record_metric("cache_misses")
                return None

            entry = self.cache[key]
            if entry["expires_at"] and time.time() > entry["expires_at"]:
                del self.cache[key]
                self.misses += 1
                await self._record_metric("cache_misses")
                return None

            self.cache.move_to_end(key)
            self.hits += 1
            await self._record_metric("cache_hits")
            return entry["value"]

    async def delete(self, key: str) -> bool:
        async with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    async def flush(self) -> None:
        async with self.lock:
            self.cache.clear()
            self.hits = 0
            self.misses = 0
            self.evictions = 0

    async def get_stats(self) -> CacheStats:
        async with self.lock:
            return CacheStats(
                hits=self.hits,
                misses=self.misses,
                evictions=self.evictions,
                current_size=len(self.cache),
                max_size=self.max_size
            )
