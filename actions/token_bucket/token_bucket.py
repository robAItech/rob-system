"""Core Domain Logic — TokenBucket rate limiter (actions/token_bucket)."""

from __future__ import annotations

import threading
import time
from typing import Callable, Optional

#: Tovarniški časovni vir. Testi ga nadomestijo z injicirano fiktivno uro.
DEFAULT_CLOCK: Callable[[], float] = time.monotonic


class TokenBucket:
    """Algoritem vedra z žetoni (token bucket) za omejevanje hitrosti.

    Vedro ima kapaciteto ``capacity`` žetonov in se polni s hitrostjo
    ``rate`` žetonov na sekundo (z zgornjo mejo ``capacity``). Vsak klic
    ``allow()``/``take()`` porabi en žeton, če je na voljo.

    Argumenti:
        capacity: maksimalno število žetonov v vedru (>= 0).
        rate: hitrost polnjenja v žetonih na sekundo (>= 0; 0 = brez polnjenja).
        clock: opcijski časovni vir ``() -> float`` (privzeto ``time.monotonic``);
               uporablja se izključno za testiranje.

    Izzove ``ValueError``, če je ``capacity`` ali ``rate`` negativen.
    """

    def __init__(
        self,
        capacity: float,
        rate: float,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
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
        """Dopolni žetone glede na pretečeni čas (kliči pod zaklepom)."""
        now = self._clock()
        if self.rate > 0:
            elapsed = now - self._updated
            if elapsed > 0:
                self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
                self._updated = now
        else:
            self._updated = now

    def _consume(self) -> bool:
        """Porabi en žeton, če je na voljo (kliči pod zaklepom)."""
        self._refill()
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    def allow(self) -> bool:
        """``True``, če je žeton na voljo — če je, ga porabi.

        Nikoli ne blokira; neuspeh pomeni, da je vedro trenutno prazno.
        """
        with self._lock:
            return self._consume()

    def take(self) -> bool:
        """Sinonim za ``allow()``: porabi en žeton, če je na voljo."""
        with self._lock:
            return self._consume()