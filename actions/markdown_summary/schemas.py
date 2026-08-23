"""Pydantic V2 schemas for the markdown_summary module.

Architectural guideline mapping:
  - sheme: Pydantic V2 s strogimi validatorji -> ConfigDict(strict=True) +
    field_validator za prazne vrednosti in natanko 3 točke.
"""

from typing import List

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SummaryDocument(BaseModel):
    """A Markdown summary document: H1 title, paragraphs and bullet points.

    Strict Pydantic V2 model: no extra fields, no coercion, no blank text and
    exactly three bullet points (per directive: "3 točkami").
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