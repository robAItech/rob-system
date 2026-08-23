"""markdown_summary — ustvari summary.md s povzetkom prednosti avtonomnega AI inženirstva.

Ob uvozu modula se ciljni dokument (`actions/markdown_summary/summary.md`) takoj
generira, da je artefakt vedno prisoten v repozitoriju (verifikacija preverja
obstoj Markdown datoteke v cilju).
"""

from .markdown_summary import (
    DEFAULT_FILENAME,
    MODULE_DIR,
    default_document,
    generate_summary,
    render_markdown,
    write_summary_file,
)
from .schemas import SummaryDocument

__all__ = [
    "DEFAULT_FILENAME",
    "MODULE_DIR",
    "SummaryDocument",
    "default_document",
    "generate_summary",
    "render_markdown",
    "write_summary_file",
]

# Zagotovi, da summary.md obstaja takoj po uvozu modula.
write_summary_file()