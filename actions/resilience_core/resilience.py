"""resilience_core — konsolidirano jedro odpornostnih politik (Refaktor 1).

Arhitekturna revizija (2026): nekdanja `retry_wrapper`, `circuit_breaker` in del
`rate_limiter`-ja so konsolidirani v ENO jedro. Tu živi:
  - `retry` (eksponentni backoff, nekoč retry_wrapper),
  - `CircuitBreaker` + `CircuitBreakerOpenException` (nekoč circuit_breaker),
  - `TokenBucket` in `SlidingWindowRateLimiter` (nekoč del rate_limiter),
  - `RateLimitPolicy` — enotna politika (rate-limit → circuit → retry).

Stari moduli (`retry_wrapper`, `circuit_breaker`, `rate_limiter.algorithms`)
so zdaj tanke fasade, ki re-exportajo od tod — zato javni API in runtime
veriga delujeta nespremenjeno, logika pa je na enem mestu.
"""

from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")
DEFAULT_CLOCK: Callable[[], float] = time.monotonic


# ── Retry z eksponentnim backoffom (nekoč actions.retry_wrapper) ────────────
def retry(fn: Callable[[], T], attempts: int = 3, delay: float = 0.1) -> T:
    """Pokliči ``fn``, ob izjemi ponovi z eksponentnim backoffom.

    Prvi klic gre takoj. Ob vsaki izjemi se ``fn`` pokliče znova, do ``attempts``
    krat skupaj; med poskusi se spi ``delay``, ki se po vsakem neuspehu podvoji
    (0.1, 0.2, 0.4, ...). Ob izčrpanju se dvigne zadnja izjema.
    """
    current_delay = delay
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception:
            if attempt >= attempts:
                raise
            time.sleep(current_delay)
            current_delay *= 2


async def retry_async(
    fn: Callable[[], Awaitable[T]], attempts: int = 3, delay: float = 0.1
) -> T:
    """Async različica ``retry`` (backoff prek ``asyncio.sleep``)."""
    current_delay = delay
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except Exception:
            if attempt >= attempts:
                raise
            await asyncio.sleep(current_delay)
            current_delay *= 2


# ── Token bucket (nekoč actions.rate_limiter.algorithms.TokenBucket) ────────
class TokenBucket:
    """Vedro z žetoni za omejevanje hitrosti (cap + polnjenje s hitrostjo)."""

    def __init__(self, capacity: float, rate: float, clock: Optional[Callable[[], float]] = None):
        if capacity < 0:
            raise ValueError("capacity must be >= 0")
        if rate < 0:
            raise ValueError("rate must be >= 0")
        self.capacity = float(capacity)
        self.rate = float(rate)
        self._clock = clock or DEFAULT_CLOCK
        self._tokens = float(capacity)
        self._updated = self._clock()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = self._clock()
        if self.rate > 0:
            elapsed = now - self._updated
            if elapsed > 0:
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._updated = now
        else:
            self._updated = now

    @property
    def tokens(self) -> float:
        with self._lock:
            self._refill()
            return self._tokens

    def allow(self) -> bool:
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

    def take(self) -> bool:
        """Sinonim za ``allow()``: porabi en žeton, če je na voljo."""
        return self.allow()


class SlidingWindowRateLimiter:
    """Drseče okno: šteje zahteve v zadnjih ``window_seconds`` (nekoč del rate_limiter)."""

    def __init__(self, max_requests: int = 5, window_seconds: float = 1.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int, float]:
        now = time.time()
        window_start = now - self.window_seconds
        self.requests[key] = [t for t in self.requests[key] if t > window_start]
        current_count = len(self.requests[key])
        if current_count < self.max_requests:
            self.requests[key].append(now)
            return True, self.max_requests - (current_count + 1), 0.0
        oldest = self.requests[key][0]
        return False, 0, round(max(0.0, oldest + self.window_seconds - now), 3)


# ── Circuit breaker (nekoč actions.circuit_breaker) ─────────────────────────
class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class CircuitConfig:
    failure_threshold: int = 3
    recovery_timeout: float = 0.2
    half_open_success_threshold: int = 2


class CircuitBreakerOpenException(Exception):
    pass


class CircuitBreaker:
    """Circuit breaker: CLOSED → OPEN (ob pragu napak) → HALF_OPEN (po recovery)."""

    def __init__(self, service_name: str, config: CircuitConfig = CircuitConfig()):
        self.service_name = service_name
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.total_requests = 0
        self.last_state_change = time.time()

    def _update_state(self, new_state: CircuitState) -> None:
        self.state = new_state
        self.last_state_change = time.time()
        if new_state == CircuitState.CLOSED:
            self.failure_count = 0
            self.success_count = 0

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == CircuitState.OPEN:
            if now - self.last_state_change >= self.config.recovery_timeout:
                self._update_state(CircuitState.HALF_OPEN)
                return True
            return False
        return True

    async def execute(self, func: Callable[[], Awaitable[Any]]) -> Any:
        self.total_requests += 1
        if not self.can_execute():
            raise CircuitBreakerOpenException(f"Circuit for '{self.service_name}' is OPEN.")
        try:
            result = await func()
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise e

    def on_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.half_open_success_threshold:
                self._update_state(CircuitState.CLOSED)
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def on_failure(self) -> None:
        self.failure_count += 1
        if self.state == CircuitState.HALF_OPEN:
            self._update_state(CircuitState.OPEN)
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._update_state(CircuitState.OPEN)

    def get_status(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "state": self.state,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "total_requests": self.total_requests,
        }


# ── Enotna politika odpornosti (Refaktor 1 — ResiliencePolicy) ──────────────
@dataclass
class ResiliencePolicyConfig:
    """Deklarativna politika: rate-limit + circuit breaker + retry."""

    rate_limit_max: int = 5
    rate_limit_window: float = 1.0
    rate_limit_strategy: str = "sliding_window"   # sliding_window | token_bucket
    circuit_failure_threshold: int = 3
    circuit_recovery_timeout: float = 0.2
    circuit_half_open_success_threshold: int = 2
    retry_attempts: int = 3
    retry_delay: float = 0.1


class RateLimitPolicy:
    """Rate-limit del politike: sliding window ali token bucket po ključu."""

    def __init__(self, config: ResiliencePolicyConfig):
        self.config = config
        self._windows: Dict[str, SlidingWindowRateLimiter] = {}
        self._buckets: Dict[str, TokenBucket] = {}

    def _bucket(self, key: str) -> TokenBucket:
        if key not in self._buckets:
            self._buckets[key] = TokenBucket(
                capacity=float(self.config.rate_limit_max),
                rate=float(self.config.rate_limit_max) / max(self.config.rate_limit_window, 1e-9),
            )
        return self._buckets[key]

    def _window(self, key: str) -> SlidingWindowRateLimiter:
        if key not in self._windows:
            self._windows[key] = SlidingWindowRateLimiter(
                max_requests=self.config.rate_limit_max,
                window_seconds=self.config.rate_limit_window,
            )
        return self._windows[key]

    def is_allowed(self, key: str) -> tuple[bool, int, float]:
        if self.config.rate_limit_strategy == "token_bucket":
            bucket = self._bucket(key)
            if bucket.allow():
                return True, int(max(0.0, bucket.tokens)), 0.0
            return False, 0, round(self.config.rate_limit_window, 3)
        return self._window(key).is_allowed(key)


class ResilienceExecutor:
    """Polna politika: rate-limit → circuit → retry okoli ene async naloge.

    ```python
    ex = ResilienceExecutor(ResiliencePolicyConfig(...))
    result = await ex.execute("client_a", "svc", lambda: asyncio.sleep(0, result="ok"))
    ```
    """

    def __init__(self, config: ResiliencePolicyConfig = ResiliencePolicyConfig()):
        self.config = config
        self.limit = RateLimitPolicy(config)
        self.circuits: Dict[str, CircuitBreaker] = {}

    def _circuit(self, service_name: str) -> CircuitBreaker:
        if service_name not in self.circuits:
            self.circuits[service_name] = CircuitBreaker(
                service_name=service_name,
                config=CircuitConfig(
                    failure_threshold=self.config.circuit_failure_threshold,
                    recovery_timeout=self.config.circuit_recovery_timeout,
                    half_open_success_threshold=self.config.circuit_half_open_success_threshold,
                ),
            )
        return self.circuits[service_name]

    async def execute(self, key: str, service_name: str, fn: Callable[[], Awaitable[T]]) -> T:
        """Rate-limit preverba → circuit → retry loop (async)."""
        allowed, _, _ = self.limit.is_allowed(key)
        if not allowed:
            raise CircuitBreakerOpenException("RATE_LIMIT_EXCEEDED")
        circuit = self._circuit(service_name)
        current_delay = self.config.retry_delay
        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                return await circuit.execute(fn)
            except CircuitBreakerOpenException:
                raise
            except Exception:
                if attempt >= self.config.retry_attempts:
                    raise
                await asyncio.sleep(current_delay)
                current_delay *= 2
        raise RuntimeError("unreachable")  # pragma: no cover


__all__ = [
    "retry",
    "retry_async",
    "TokenBucket",
    "SlidingWindowRateLimiter",
    "CircuitState",
    "CircuitConfig",
    "CircuitBreaker",
    "CircuitBreakerOpenException",
    "ResiliencePolicyConfig",
    "RateLimitPolicy",
    "ResilienceExecutor",
]
