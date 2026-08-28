"""pii_masking_sanitizer — FastAPI aplikacija (API plast).

Expose: registracija PII polj, maskiranje strukture, redakcija besedila +
health. Exporta ``app`` — v runtime pod ``/api/pii_masking_sanitizer/*``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from actions.pii_masking_sanitizer.pii import PIIMasker
from actions.pii_masking_sanitizer.schemas import (
    MaskRequest,
    MaskResponse,
    RedactRequest,
    RedactResponse,
    RegisterFieldRequest,
)

app = FastAPI(title="Rob AI Studio - PII Masking Sanitizer", version="1.0.0")
masker = PIIMasker()

# Privzeto registrirana pogosta PII polja (GDPR/HIPAA).
for _name, _cat, _strat in (
    ("email", "email", "partial"),
    ("iban", "iban", "partial"),
    ("phone", "phone", "mask"),
    ("ssn", "ssn", "mask"),
):
    masker.register_field(_name, _cat, _strat)


@app.post("/fields")
async def register_field(body: RegisterFieldRequest) -> JSONResponse:
    """Registriraj PII polje."""
    field = masker.register_field(body.name, body.category, body.strategy)
    return JSONResponse({"name": field.name, "category": field.category, "strategy": field.strategy})


@app.post("/mask", response_model=MaskResponse)
async def mask(body: MaskRequest) -> JSONResponse:
    """Maskiraj registrirana PII polja v strukturi."""
    return JSONResponse(MaskResponse(masked=masker.mask(body.data)).model_dump())


@app.post("/redact", response_model=RedactResponse)
async def redact(body: RedactRequest) -> JSONResponse:
    """Redakcija e-pošt/telefonov/IBAN v prostem besedilu."""
    return JSONResponse(RedactResponse(redacted=masker.redact_text(body.text)).model_dump())


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP", "fields": sorted(masker.fields.keys())}
