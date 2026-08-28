"""secret_rotation — FastAPI aplikacija (API plast).

Expose: registracija skrivnosti, rotacija (double-buffer), aktivacija, status,
due scheduler, revoke in audit sled. Exporta ``app`` — v actions runtime pod
``/api/secret_rotation/*``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from actions.secret_rotation.rotation import SecretRotationManager
from actions.secret_rotation.schemas import (
    AuditEntryResponse,
    RotationRequest,
    RotationResponse,
    SecretRegisterRequest,
    SecretStatusResponse,
    RevokeRequest,
)

app = FastAPI(title="Rob AI Studio - Secret Rotation", version="1.0.0")
manager = SecretRotationManager()


def _iso_ts(ts: float) -> str:
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts, tz=_dt.timezone.utc).isoformat()


@app.post("/secrets", response_model=SecretStatusResponse)
async def register_secret(body: SecretRegisterRequest) -> JSONResponse:
    """Registriraj novo skrivnost z rotacijsko politiko (interval v dnevih)."""
    state = manager.register_secret(
        name=body.name,
        kind=body.kind,
        rotation_interval_days=body.rotation_interval_days,
    )
    return JSONResponse(manager.to_response(state))


@app.get("/status", response_model=List[SecretStatusResponse])
async def status_all() -> JSONResponse:
    """Stanje vseh skrivnosti (vrednosti maskirane)."""
    return JSONResponse([manager.to_response(s) for s in manager.all_statuses()])


@app.get("/status/{name}", response_model=SecretStatusResponse)
async def status_one(name: str) -> JSONResponse:
    """Stanje ene skrivnosti; 404, če ne obstaja."""
    state = manager.status_of(name)
    if state is None:
        raise HTTPException(status_code=404, detail="secret not found")
    return JSONResponse(manager.to_response(state))


@app.post("/rotate", response_model=RotationResponse)
async def rotate(body: RotationRequest) -> JSONResponse:
    """Pripravi novo vrednost (staged) — stara ostaja aktivna (zero-downtime)."""
    state = manager.rotate(body.name)
    if state is None:
        raise HTTPException(status_code=404, detail="secret not found or revoked")
    return JSONResponse(
        RotationResponse(
            name=body.name,
            action="rotated",
            next_rotation_at=_iso_ts(state.next_rotation_at) if state.next_rotation_at else None,
        ).model_dump()
    )


@app.post("/activate", response_model=RotationResponse)
async def activate(body: RotationRequest) -> JSONResponse:
    """Promoviraj staged → aktivna (double-buffer preklop)."""
    state = manager.activate(body.name)
    if state is None:
        raise HTTPException(status_code=404, detail="secret not found or revoked")
    return JSONResponse(
        RotationResponse(
            name=body.name,
            action="activated",
            next_rotation_at=_iso_ts(state.next_rotation_at) if state.next_rotation_at else None,
        ).model_dump()
    )


@app.get("/due", response_model=List[SecretStatusResponse])
async def due() -> JSONResponse:
    """Skrivnosti, katerih rotacija je zapadla (scheduler tick)."""
    return JSONResponse([manager.to_response(s) for s in manager.due_secrets()])


@app.post("/revoke")
async def revoke(body: RevokeRequest) -> JSONResponse:
    """Takojšen umik skrivnosti (auto-revoke ob sumljivih dogodkih)."""
    if not manager.revoke(body.name, reason=body.reason):
        raise HTTPException(status_code=404, detail="secret not found")
    return JSONResponse({"name": body.name, "revoked": True, "reason": body.reason})


@app.get("/audit", response_model=List[AuditEntryResponse])
async def audit() -> JSONResponse:
    """Audit sled vseh rotacij/aktivacij/umikov."""
    return JSONResponse(
        [
            {"name": a.name, "action": a.action, "detail": a.detail, "at": _iso_ts(a.at)}
            for a in manager.audit
        ]
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP", "secrets": len(manager.secrets), "due": len(manager.due_secrets())}
