"""rate_limiter.algorithms — FASADA nad actions.resilience_core (Refaktor 1).

Algoritem ``TokenBucket`` je konsolidiran v ``resilience_core``; ta modul ga
re-exporta, da obstoječi importi (`rate_limiter.py`, testi) delujejo naprej.
"""

from actions.resilience_core.resilience import TokenBucket

__all__ = ["TokenBucket"]
