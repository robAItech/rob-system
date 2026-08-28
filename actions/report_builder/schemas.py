"""report_builder — Pydantic V2 sheme s strogimi validatorji (API plast)."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

# Stroga validacija: brez tihe koercitve tipov; prazen niz ni dovoljen.
StrictText = Annotated[str, StringConstraints(strict=True, min_length=1)]


class BuildReportRequest(BaseModel):
    """Vhod za POST /api/report-builder/build."""

    model_config = ConfigDict(extra="forbid", strict=True)

    csv_tekst: StrictText = Field(..., description="Surovo CSV besedilo poročila")


class BuildReportResponse(BaseModel):
    """Izhod: ``{naslov_slug: [vrstice]}``."""

    model_config = ConfigDict(extra="allow")

    report: Dict[str, List[Dict[str, Any]]]


class SummaryDocument(BaseModel):
    """A Markdown summary document: H1 title, paragraphs and bullet points.

    Prestavljeno iz nekdanjega samostojnega ``actions.markdown_summary`` (glej
    arhitekturno konsolidacijo: markdown izhod je zdaj adapter v report_builder).
    Strict Pydantic V2 model: no extra fields, no coercion, no blank text and
    exactly three bullet points.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    title: str = Field(min_length=1, max_length=200, description="H1 naslov dokumenta.")
    paragraphs: List[str] = Field(
        min_length=1, description="Eden ali več odstavkov (vsebina povzetka)."
    )
    bullet_points: List[str] = Field(
        min_length=3,
        max_length=3,
        description="Natanko 3 točke prednosti avtonomnega AI inženirstva.",
    )

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        """Strict validator: naslov ne sme biti prazen ali samo presledki."""
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("title must not be blank")
        return cleaned

    @field_validator("paragraphs")
    @classmethod
    def paragraphs_must_be_non_blank(cls, value: List[str]) -> List[str]:
        """Strict validator: vsak odstavek mora biti neprazen."""
        cleaned = [p.strip() for p in value]
        if any(not p for p in cleaned):
            raise ValueError("paragraphs must not contain blank entries")
        return cleaned

    @field_validator("bullet_points")
    @classmethod
    def exactly_three_bullet_points(cls, value: List[str]) -> List[str]:
        """Strict validator: natanko 3 neprazne točke."""
        cleaned = [p.strip() for p in value]
        if len(cleaned) != 3:
            raise ValueError("bullet_points must contain exactly 3 items")
        if any(not p for p in cleaned):
            raise ValueError("bullet_points must not contain blank entries")
        return cleaned