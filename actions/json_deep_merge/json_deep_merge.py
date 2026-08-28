"""json_deep_merge — FASADA nad actions.data_format_utils (Refaktor 3).

Logika ``deep_merge`` je konsolidirana v ``data_format_utils``; ta modul
ostaja kot stabilen javni API (re-export) za obstoječe uporabnike.
"""

from actions.data_format_utils.formats import deep_merge

__all__ = ["deep_merge"]
