"""retry_wrapper — FASADA nad actions.resilience_core (Refaktor 1).

Logika retry z eksponentnim backoffom je konsolidirana v ``resilience_core``;
ta modul ostaja kot stabilen javni API (re-export) za obstoječe uporabnike.
"""

from actions.resilience_core.resilience import retry

__all__ = ["retry"]
