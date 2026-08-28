"""zgradi__s8 — Pydantic V2 sheme s strogimi validatorji.

Sheme veljajo za generiranje Markdown poročila (arhitektura, uporaba,
navodila za zagon). Vse sheme uporabljajo ``extra="forbid"`` in validatorje,
ki zavrnejo prazne vrednosti, da neveljavni vhodi padejo čim prej.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReportSection(BaseModel):
    """En razdelek Markdown poročila (H2 naslov + vsebina)."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, description="Naslov razdelka (H2).")
    body: str = Field(min_length=1, description="Vsebina razdelka (Markdown).")

    @field_validator("title", "body")
    @classmethod
    def _reject_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("vrednost ne sme biti prazna")
        return value


class ReportRequest(BaseModel):
    """Vhodna zahteva za generiranje Markdown poročila."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, description="Glavni naslov poročila (H1).")
    sections: List[ReportSection] = Field(
        min_length=1, description="Razdelki poročila (vsaj en)."
    )

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("title ne sme biti prazen")
        return value


class ReportResponse(BaseModel):
    """Izhod: generirano Markdown poročilo."""

    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, description="Ime ciljne datoteke.")
    markdown: str = Field(min_length=1, description="Vsebina poročila (Markdown).")

    @field_validator("markdown")
    @classmethod
    def _must_start_with_h1(cls, value: str) -> str:
        if not value.lstrip().startswith("# "):
            raise ValueError("markdown se mora začeti z naslovom H1 (# ...)")
        return value