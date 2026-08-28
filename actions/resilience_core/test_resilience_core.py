"""Pytest test suite za actions/resilience_core (Refaktor 1).

Preveri konsolidirane politike: retry, TokenBucket, circuit breaker,
RateLimitPolicy (sliding window + token bucket) in ResilienceExecutor.
Deterministično — brez realnih sleep (kratki delay-ji / injiciran čas).
"""

import asyncio
from typing import Any, List

import pytest
from fastapi.testclient import TestClient

from actions.resilience_core.main import app, executor
from actions.resilience_core.resilience import (
    CircuitBreaker,
    CircuitBreakerOpenException,
    CircuitConfig,
    CircuitState,
    RateLimitPolicy,
    ResilienceExecutor,
    ResiliencePolicyConfig,
    SlidingWindowRateLimiter,
    TokenBucket,
    retry,
    retry_async,
)


# ── retry ───────────────────────────────────────────────────────────────────
def test_retry_succeeds_after_failures():
    calls: List[int] = []

    def flaky() -> int:
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("boom")
        return 42

    assert retry(flaky, attempts=4, delay=0) == 42
    assert len(calls) == 3


def test_retry_exhausted_raises():
    def always_fails() -> None:
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        retry(always_fails, attempts=2, delay=0)


@pytest.mark.asyncio
async def test_retry_async():
    calls: List[int] = []

    async def flaky() -> int:
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("boom")
        return 7

    assert await retry_async(flaky, attempts=3, delay=0) == 7
    assert len(calls) == 2


# ── TokenBucket (konsolidiran iz rate_limiter) ─────────────────────────────
def test_token_bucket_basic():
    b = TokenBucket(capacity=2, rate=1.0)
    assert b.allow() is True
    assert b.allow() is True
    assert b.allow() is False


def test_token_bucket_negative_rejected():
    with pytest.raises(ValueError):
        TokenBucket(-1, 1)


# ── SlidingWindowRateLimiter ────────────────────────────────────────────────
def test_sliding_window_limiter():
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=10.0)
    assert limiter.is_allowed("k")[0] is True
    assert limiter.is_allowed("k")[0] is True
    ok, rem, reset = limiter.is_allowed("k")
    assert ok is False and rem == 0 and reset > 0


# ── Circuit breaker ─────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold():
    cb = CircuitBreaker("svc", CircuitConfig(failure_threshold=2, recovery_timeout=0.2))

    async def failing():
        raise ValueError("e")

    for _ in range(2):
        with pytest.raises(ValueError):
            await cb.execute(failing)
    assert cb.state == CircuitState.OPEN
    with pytest.raises(CircuitBreakerOpenException):
        await cb.execute(failing)


def test_circuit_breaker_status_fields():
    cb = CircuitBreaker("svc")
    status = cb.get_status()
    assert status["state"] == CircuitState.CLOSED
    assert status["service_name"] == "svc"


# ── RateLimitPolicy (sliding + token bucket) ────────────────────────────────
def test_rate_limit_policy_sliding_window():
    policy = RateLimitPolicy(ResiliencePolicyConfig(rate_limit_max=2, rate_limit_window=10.0))
    assert policy.is_allowed("a")[0] is True
    assert policy.is_allowed("a")[0] is True
    assert policy.is_allowed("a")[0] is False


def test_rate_limit_policy_token_bucket():
    policy = RateLimitPolicy(ResiliencePolicyConfig(
        rate_limit_max=1, rate_limit_window=10.0, rate_limit_strategy="token_bucket",
    ))
    assert policy.is_allowed("a")[0] is True
    assert policy.is_allowed("a")[0] is False
    assert policy.is_allowed("b")[0] is True  # izolacija ključev


# ── ResilienceExecutor (polna politika) ─────────────────────────────────────
@pytest.mark.asyncio
async def test_executor_ok():
    ex = ResilienceExecutor(ResiliencePolicyConfig(rate_limit_max=5, retry_attempts=3))
    result = await ex.execute("k", "svc", lambda: asyncio.sleep(0, result={"ok": True}))
    assert result == {"ok": True}


@pytest.mark.asyncio
async def test_executor_rate_limit_blocks():
    ex = ResilienceExecutor(ResiliencePolicyConfig(rate_limit_max=1, rate_limit_window=60.0))
    await ex.execute("k", "svc", lambda: asyncio.sleep(0, result=1))
    with pytest.raises(CircuitBreakerOpenException):
        await ex.execute("k", "svc", lambda: asyncio.sleep(0, result=2))


@pytest.mark.asyncio
async def test_executor_retries_transient():
    calls: List[int] = []

    async def flaky() -> int:
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("transient")
        return 9

    ex = ResilienceExecutor(ResiliencePolicyConfig(retry_attempts=4, retry_delay=0))
    assert await ex.execute("k", "svc", flaky) == 9
    assert len(calls) == 3


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_apply_and_health():
    client = TestClient(app)
    r = client.post("/apply", json={"key": "t", "service_name": "svc", "payload": {"x": 1}})
    assert r.status_code == 200
    assert r.json()["status"] == "OK"

    h = client.get("/health")
    assert h.json()["status"] == "UP"
