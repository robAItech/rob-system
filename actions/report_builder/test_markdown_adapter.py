"""Pytest testna zbirka za Markdown izhodni adapter (nekdanji markdown_summary).

Arhitekturna konsolidacija: preverja, da so sposobnosti nekdanjega samostojnega
``actions.markdown_summary`` (SummaryDocument shema, render, generate) zdaj del
``actions.report_builder`` — kot output driver/adapter.
"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from actions.report_builder.markdown import (
    default_document,
    generate_summary,
    render_markdown,
    render_report_as_markdown,
    write_summary_file,
)
from actions.report_builder.report_builder import build_report_markdown
from actions.report_builder.schemas import SummaryDocument


# ── SummaryDocument shema (strogi validatorji) ──────────────────────────────
def test_summary_document_valid():
    doc = SummaryDocument(
        title="Naslov", paragraphs=["A"], bullet_points=["1", "2", "3"]
    )
    assert doc.title == "Naslov"


def test_summary_document_rejects_extra_fields():
    with pytest.raises(ValidationError):
        SummaryDocument(title="T", paragraphs=["A"], bullet_points=["1", "2", "3"], extra="x")


def test_summary_document_rejects_blank_title():
    with pytest.raises(ValidationError):
        SummaryDocument(title="   ", paragraphs=["A"], bullet_points=["1", "2", "3"])


def test_summary_document_requires_exactly_three_bullets():
    with pytest.raises(ValidationError):
        SummaryDocument(title="T", paragraphs=["A"], bullet_points=["1", "2"])


# ── render_markdown ─────────────────────────────────────────────────────────
def test_render_markdown_h1_paragraphs_bullets():
    md = render_markdown(
        SummaryDocument(
            title="Prednosti", paragraphs=["Prvi.", "Drugi."], bullet_points=["a", "b", "c"]
        )
    )
    assert md.startswith("# Prednosti")
    assert "Prvi." in md
    assert "- a" in md and "- b" in md and "- c" in md
    # Natanko 3 točke.
    assert md.count("- ") == 3


def test_default_document_roundtrip():
    md = render_markdown(default_document())
    assert md.startswith("# Prednosti avtonomnega AI inženirstva")
    assert md.count("- ") == 3


# ── write / generate ────────────────────────────────────────────────────────
def test_write_summary_file(tmp_path):
    target = tmp_path / "summary.md"
    path = write_summary_file(default_document(), target)
    assert path == target
    assert target.exists()
    assert target.read_text(encoding="utf-8").startswith("# ")


@pytest.mark.asyncio
async def test_generate_summary_async(tmp_path):
    target = tmp_path / "gen.md"
    path = await generate_summary(default_document(), target)
    assert path.exists()


# ── build_report_markdown (report → Markdown) ───────────────────────────────
def test_build_report_markdown_renders_sections():
    csv_tekst = (
        "naslov,opis\n"
        "Prvi del,besedilo1\n"
        "Drugi del,besedilo3\n"
    )
    md = build_report_markdown(csv_tekst, title="Moj raport")
    assert md.startswith("# Moj raport")
    assert "## prvi-del" in md
    assert "## drugi-del" in md
    # Oznaka vrstice = prva vrednost (naslov), ki vodi sekcijo.
    assert "- Prvi del" in md
    assert "- Drugi del" in md


def test_render_report_as_markdown_empty():
    # Prazen raport → le H1 naslov (dokument ni "nič", vedno ima glavo).
    assert render_report_as_markdown({}) == "# Poročilo\n"
