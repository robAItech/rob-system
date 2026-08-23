"""report_builder — Pydantic V2 sheme s strogimi validatorji (API plast)."""

from __future__ import annotations

from typing import Annotated, Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

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