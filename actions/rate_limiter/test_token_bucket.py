"""Pytest test suite za token-bucket strategijo actions/rate_limiter.

Testi verifikacijo pogodbe algoritma TokenBucket (allow/take/refill/cap) in
njegovo integracijo v RateLimiter prek ``config.strategy="token_bucket"``.
Uporabljajo injiciran fiktivni časovni vir, zato so deterministični (brez sleep).
"""

from actions.rate_limiter.algorithms import TokenBucket
from actions.rate_limiter.rate_limiter import RateLimiter
from actions.rate_limiter.schemas import RateLimitConfig


class FakeClock:
    """Nadomestni časovni vir za deterministično testiranje."""

    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def test_initial_bucket_is_full():
    clock = FakeClock(100.0)
    bucket = TokenBucket(capacity=3, rate=1.0, clock=clock)
    assert bucket.allow() is True
    assert bucket.allow() is True
    assert bucket.allow() is True
    # Bazen je prazen — brez pretečenega časa ni novega žetona.
    assert bucket.allow() is False


def test_take_consumes_tokens():
    clock = FakeClock(0.0)
    bucket = TokenBucket(capacity=2, rate=5.0, clock=clock)
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False


def test_refill_over_time():
    clock = FakeClock(0.0)
    bucket = TokenBucket(capacity=1, rate=1.0, clock=clock)
    assert bucket.allow() is True    # porabi edini žeton
    assert bucket.allow() is False   # bazen prazen
    clock.advance(0.5)
    assert bucket.allow() is False   # pri rate=1 še ni polnega žetona
    clock.advance(0.5)
    assert bucket.allow() is True    # po 1s se je nabral 1 žeton


def test_capacity_never_exceeded():
    clock = FakeClock(0.0)
    bucket = TokenBucket(capacity=2, rate=10.0, clock=clock)
    bucket.take()
    clock.advance(10.0)              # nabralo bi se 100 žetonov — cap = 2
    assert bucket.take() is True
    assert bucket.take() is True
    assert bucket.take() is False


def test_rate_zero_means_no_refill():
    clock = FakeClock(0.0)
    bucket = TokenBucket(capacity=1, rate=0.0, clock=clock)
    assert bucket.take() is True
    clock.advance(100.0)
    assert bucket.take() is False


def test_negative_arguments_rejected():
    try:
        TokenBucket(-1, 1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative capacity")

    try:
        TokenBucket(1, -1)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for negative rate")


def test_tokens_property_after_refill():
    clock = FakeClock(0.0)
    bucket = TokenBucket(capacity=5, rate=2.0, clock=clock)
    bucket.take()                    # 4 žetoni
    clock.advance(1.0)               # +2 → 5 (cap)
    assert bucket.tokens == 5.0
    clock.advance(0.5)               # +1 → 5 (cap), ne 6
    assert bucket.tokens == 5.0


# ── Integracija: RateLimiter z strategijo token_bucket ──────────────────────
def test_rate_limiter_token_bucket_strategy():
    limiter = RateLimiter(RateLimitConfig(
        max_requests=2, window_seconds=10.0, strategy="token_bucket",
    ))
    # Najprej 2 zahtevi dovoljeni (vedro polno = capacity 2).
    ok1, rem1, _ = limiter.is_allowed("client_a")
    assert ok1 is True
    assert rem1 == 1
    ok2, rem2, _ = limiter.is_allowed("client_a")
    assert ok2 is True
    assert rem2 == 0
    # Vedro prazno → 3. zahteva blokirana; reset = celo okno.
    ok3, rem3, reset3 = limiter.is_allowed("client_a")
    assert ok3 is False
    assert rem3 == 0
    assert reset3 == 10.0


def test_rate_limiter_token_bucket_isolates_keys():
    limiter = RateLimiter(RateLimitConfig(
        max_requests=1, window_seconds=5.0, strategy="token_bucket",
    ))
    assert limiter.is_allowed("client_a")[0] is True
    assert limiter.is_allowed("client_b")[0] is True
    assert limiter.is_allowed("client_a")[0] is False
    assert limiter.is_allowed("client_b")[0] is False


def test_rate_limiter_default_strategy_still_sliding_window():
    limiter = RateLimiter(RateLimitConfig(max_requests=2, window_seconds=0.5))
    assert limiter.config.strategy == "sliding_window"
    ok1, _, _ = limiter.is_allowed("k")
    ok2, _, _ = limiter.is_allowed("k")
    ok3, _, _ = limiter.is_allowed("k")
    assert (ok1, ok2, ok3) == (True, True, False)
