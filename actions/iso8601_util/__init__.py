"""iso8601_util — ISO 8601 datum (YYYY-MM-DD) <-> datetime pretvorba (fasada).

Javni API:
    parse_iso(niz: str) -> datetime
    format_iso(dt: datetime | date) -> str

Logika živi v ``actions.data_format_utils`` (Refaktor 3).
"""

from .core import format_iso, parse_iso

__all__ = ["parse_iso", "format_iso"]
__version__ = "1.0.0"
