"""csv_parser — FASADA nad actions.data_format_utils (Refaktor 3).

Logika ``parse_csv``/``to_csv`` je konsolidirana v ``data_format_utils``;
ta modul ostaja kot stabilen javni API (re-export) za obstoječe uporabnike
(npr. report_builder).
"""

from actions.data_format_utils.formats import parse_csv, to_csv

__all__ = ["parse_csv", "to_csv"]
