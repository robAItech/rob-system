"""Pytest test suite for the retry_wrapper module.

Covers the documented contract of ``retry``:
- the first call happens immediately,
- on exceptions ``fn`` is re-invoked up to ``attempts`` times in total,
- between attempts the process sleeps for ``delay`` seconds, doubling after
  every failed attempt (0.1, 0.2, 0.4, ...),
- the value of the first successful invocation is returned,
- the last exception is raised once all attempts are exhausted.
"""

import time
from unittest import mock

import pytest

from retry_wrapper import retry


def test_returns_value_on_first_success():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert retry(fn) == "ok"
    assert len(calls) == 1


def test_retries_until_success():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("boom")
        return "recovered"

    with mock.patch.object(time, "sleep") as sleep:
        assert retry(fn, attempts=5) == "recovered"

    assert len(calls) == 3
    assert sleep.call_count == 2


def test_exhausts_attempts_and_raises_last_exception():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("boom")

    with mock.patch.object(time, "sleep"):
        with pytest.raises(ValueError, match="boom"):
            retry(fn, attempts=3)

    assert len(calls) == 3


def test_default_attempts_is_three():
    calls = []

    def fn():
        calls.append(1)
        raise RuntimeError("x")

    with mock.patch.object(time, "sleep"):
        with pytest.raises(RuntimeError):
            retry(fn)

    assert len(calls) == 3


def test_exponential_backoff_doubles_delay():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("boom")

    with mock.patch.object(time, "sleep") as sleep:
        with pytest.raises(ValueError):
            retry(fn, attempts=4, delay=0.1)

    sleep.assert_has_calls([mock.call(0.1), mock.call(0.2), mock.call(0.4)])


def test_no_sleep_when_single_attempt():
    def fn():
        raise ValueError("boom")

    with mock.patch.object(time, "sleep") as sleep:
        with pytest.raises(ValueError):
            retry(fn, attempts=1)

    sleep.assert_not_called()


def test_custom_initial_delay():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("boom")

    with mock.patch.object(time, "sleep") as sleep:
        with pytest.raises(ValueError):
            retry(fn, attempts=3, delay=0.5)

    sleep.assert_has_calls([mock.call(0.5), mock.call(1.0)])


def test_does_not_sleep_after_final_failure():
    calls = []

    def fn():
        calls.append(1)
        raise ValueError("boom")

    with mock.patch.object(time, "sleep") as sleep:
        with pytest.raises(ValueError):
            retry(fn, attempts=3)

    # Sleep happens only *between* attempts, never after the last one.
    assert sleep.call_count == 2
