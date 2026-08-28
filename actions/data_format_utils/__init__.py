"""data_format_utils — konsolidirane formatne funkcije (Refaktor 3).

Javni API:
    parse_csv(text, delimiter) / to_csv(rows, delimiter)
    parse_iso(niz) / format_iso(dt)
    deep_merge(a, b)

Nekdanji samostojni moduli (csv_parser, iso8601_util, json_deep_merge) so
zdaj fasade nad tem jednom.
"""

from actions.data_format_utils.formats import (
    parse_csv,
    to_csv,
    parse_iso,
    format_iso,
    deep_merge,
)

__all__ = ["parse_csv", "to_csv", "parse_iso", "format_iso", "deep_merge"]
