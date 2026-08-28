"""report_builder — gradnja poročil iz CSV besedila + Markdown izhodni adapter.

Javni API:
    build_report(csv_tekst) -> dict {naslov_slug: [vrstice]}
    build_report_markdown(csv_tekst, title) -> str
    render_markdown(document: SummaryDocument) -> str

Arhitekturna konsolidacija (2.3): nekdanji samostojni ``actions.markdown_summary``
je absorbiran kot output driver/adapter tega modula.
"""

from actions.report_builder.report_builder import build_report, build_report_async, build_report_markdown
from actions.report_builder.markdown import render_markdown, render_report_as_markdown, default_document, generate_summary
from actions.report_builder.schemas import SummaryDocument

__all__ = [
    "build_report",
    "build_report_async",
    "build_report_markdown",
    "render_markdown",
    "render_report_as_markdown",
    "default_document",
    "generate_summary",
    "SummaryDocument",
]
