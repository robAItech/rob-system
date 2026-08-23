"""Core Domain Logic: retry wrapper with exponential backoff."""

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(fn: Callable[[], T], attempts: int = 3, delay: float = 0.1) -> T:
    """Invoke ``fn``, retrying on exception with exponential backoff.

    The first call happens immediately. On each exception ``fn`` is called
    again up to ``attempts`` times in total; between attempts the process
    sleeps for ``delay`` seconds, doubling after every failed attempt
    (0.1, 0.2, 0.4, ...).

    Args:
        fn: Zero-argument callable to invoke.
        attempts: Maximum number of invocations (including the first).
        delay: Initial sleep between retries, in seconds.

    Returns:
        The value returned by the first successful invocation of ``fn``.

    Raises:
        The last exception raised by ``fn`` once all attempts are exhausted.
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