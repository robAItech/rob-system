"""api_version_manager — FastAPI aplikacija (API plast).

Expose: registracija verzij, weighted routing, deprecation politika in BC-break
detekcija. Exporta ``app`` (FastAPI) — v actions runtime pod
``/api/api_version_manager/*``.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from actions.api_version_manager.schemas import (
    BreakingCheckRequest,
    BreakingCheckResponse,
    DeprecationRequest,
    RouteRequest,
    RouteResponse,
    SemVerModel,
    VersionInfo,
    VersionRegisterRequest,
)
from actions.api_version_manager.version_manager import SemVer, VersionManager

app = FastAPI(title="Rob AI Studio - API Version Manager", version="1.0.0")
manager = VersionManager()


def _version_info(route) -> VersionInfo:
    return VersionInfo(
        tag=route.tag,
        version=str(route.version),
        weight=route.weight,
        active=route.active,
        deprecated=route.deprecated,
        sunset=route.sunset,
    )


@app.post("/versions", response_model=VersionInfo)
async def register_version(body: VersionRegisterRequest) -> JSONResponse:
    """Registriraj novo API verzijo s SemVer in težo."""
    route = manager.register_version(
        tag=body.tag,
        version=SemVer(major=body.version.major, minor=body.version.minor, patch=body.version.patch),
        weight=body.weight,
        active=body.active,
    )
    return JSONResponse(_version_info(route).model_dump())


@app.get("/versions", response_model=List[VersionInfo])
async def list_versions() -> JSONResponse:
    """Seznam registriranih verzij (razvrščenih po SemVer)."""
    return JSONResponse([_version_info(v).model_dump() for v in manager.list_versions()])


@app.post("/route", response_model=RouteResponse)
async def route(body: RouteRequest) -> JSONResponse:
    """Weighted izbor verzije (canary/blue-green/A-B) z deprecation opozorili."""
    selected = manager.route([(v.tag, v.weight) for v in body.versions])
    if selected is None:
        raise HTTPException(status_code=409, detail="no active candidate version")
    tag, version = selected
    warnings = manager.deprecation_headers(tag)
    return JSONResponse(
        RouteResponse(
            selected=tag, version=str(version), deprecation_warnings=warnings
        ).model_dump()
    )


@app.post("/versions/{tag}/deprecate")
async def deprecate(tag: str, body: DeprecationRequest) -> JSONResponse:
    """Označi verzijo kot deprecirano (Sunset + obvestilo)."""
    if not manager.deprecate(tag, notice=body.notice, sunset=body.sunset):
        raise HTTPException(status_code=404, detail="version not found")
    return JSONResponse({"tag": tag, "deprecated": True, "notice": body.notice})


@app.get("/deprecations", response_model=List[VersionInfo])
async def deprecations() -> JSONResponse:
    """Vse aktivne deprecation politike."""
    return JSONResponse([_version_info(v).model_dump() for v in manager.active_deprecations()])


@app.post("/check-bc", response_model=BreakingCheckResponse)
async def check_breaking(body: BreakingCheckRequest) -> JSONResponse:
    """BC-break detekcija med staro in novo JSON shemo → changelog."""
    is_breaking, changes = manager.detect_breaking_change(body.old_schema, body.new_schema)
    return JSONResponse(
        BreakingCheckResponse(is_breaking=is_breaking, changes=changes).model_dump()
    )


@app.get("/health")
async def health() -> Dict[str, Any]:
    """Health pregled modula."""
    return {"status": "UP", "versions": len(manager.versions)}
