"""RateLimiter — jedro domenske logike s podporo za več strategij.

Privzeta strategija je **sliding window** (zgodovina zahtev v oknu). Od
arhitekturne konsolidacije (``token_bucket`` je absorbiran v ``rate_limiter``)
podpiramo tudi strategijo **token bucket** prek ``config.strategy`` — vedro z
žetoni, ki se polni s hitrostjo ``max_requests / window_seconds``.

Vmesnik ``is_allowed(key) -> (allowed, remaining, reset_in_seconds)`` ostaja
nespremenjen, zato middleware (``core/actions_runtime``) in API plast delujeta
brez sprememb.
"""

import time
from collections import defaultdict
from typing import Dict, List, Tuple

from actions.rate_limiter.algorithms import TokenBucket
from actions.rate_limiter.schemas import RateLimitConfig


class RateLimiter:
    """Omejevalnik hitrosti z izbiro strategije prek ``RateLimitConfig``."""

    def __init__(self, config: RateLimitConfig = RateLimitConfig()):
        self.config = config
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self._buckets: Dict[str, TokenBucket] = {}

    def is_allowed(self, key: str) -> Tuple[bool, int, float]:
        """Ali je zahteva za ``key`` dovoljena? (strategija iz ``config.strategy``)."""
        if self.config.strategy == "token_bucket":
            return self._is_allowed_token_bucket(key)
        return self._is_allowed_sliding_window(key)

    # ── Strategija 1: sliding window ────────────────────────────────────────
    def _is_allowed_sliding_window(self, key: str) -> Tuple[bool, int, float]:
        """Klasično drseče okno: štejemo zahteve v zadnjem ``window_seconds``."""
        now = time.time()
        window_start = now - self.config.window_seconds

        # Očisti zastarele časovne žige znotraj okna
        self.requests[key] = [t for t in self.requests[key] if t > window_start]

        current_count = len(self.requests[key])

        if current_count < self.config.max_requests:
            self.requests[key].append(now)
            remaining = self.config.max_requests - (current_count + 1)
            return True, remaining, 0.0
        else:
            oldest_request = self.requests[key][0]
            reset_in = max(0.0, oldest_request + self.config.window_seconds - now)
            return False, 0, round(reset_in, 3)

    # ── Strategija 2: token bucket ──────────────────────────────────────────
    def _is_allowed_token_bucket(self, key: str) -> Tuple[bool, int, float]:
        """Token bucket: eno vedro na ključ, polnjenje ``max_requests/okno``.

        Kapaciteta vedra = ``max_requests``; hitrost polnjenja = kolikokrat na
        okno sme klient zahtevati. Ob praznem vedru je reset čas = celo okno.
        """
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = TokenBucket(
                capacity=float(self.config.max_requests),
                rate=float(self.config.max_requests) / self.config.window_seconds,
            )
            self._buckets[key] = bucket

        if bucket.allow():
            remaining = int(max(0.0, bucket.tokens))
            return True, remaining, 0.0
        return False, 0, round(self.config.window_seconds, 3)


__all__ = ["RateLimiter", "TokenBucket"]
