"""report_builder — gradnja poročil iz CSV besedila.

Javni API:
    build_report(csv_tekst) -> dict {naslov_slug: [vrstice]}
"""

from actions.report_builder.report_builder import build_report, build_report_async

__all__ = ["build_report", "build_report_async"]