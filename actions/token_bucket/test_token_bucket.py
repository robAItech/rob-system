"""Pytest test suite za actions/token_bucket — TokenBucket rate limiter.

Testi verifikacijo pogodbe iz direktive: razred ``TokenBucket(capacity, rate)``
z metodama ``allow()`` in ``take()``. Uporabljajo injiciran fiktivni časovni
vir, zato so deterministični (brez ``sleep``).
"""

try:
    from actions.token_bucket import TokenBucket
except ImportError:  # pragma: no cover - odvisno od sys.path pri poganjanju
    try:
        from actions.token_bucket.token_bucket import TokenBucket
    except ImportError:
        from token_bucket import TokenBucket


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
