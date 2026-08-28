"""resilience_core — konsolidirano jedro odpornostnih politik (Refaktor 1).

Vsebuje: retry, TokenBucket, SlidingWindowRateLimiter, CircuitBreaker in
enotno ``ResilienceExecutor`` politiko (rate-limit → circuit → retry).

Nekdanji samostojni moduli (retry_wrapper, circuit_breaker, rate_limiter
algoritmi) so zdaj fasade nad tem jednom.
"""

from actions.resilience_core.resilience import (
    retry,
    retry_async,
    TokenBucket,
    SlidingWindowRateLimiter,
    CircuitState,
    CircuitConfig,
    CircuitBreaker,
    CircuitBreakerOpenException,
    ResiliencePolicyConfig,
    RateLimitPolicy,
    ResilienceExecutor,
)

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
