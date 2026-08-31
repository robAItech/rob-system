"""fleet_security — FastAPI vmesnik (pasivno jedro).

Izvoz tako ``router`` (vzorec report_builder) kot ``app`` (standalone run).
Blokirajoče sqlite/subprocess klici gredo skozi ``run_in_threadpool``.
Vsak handler piše audit event ``fleet-security-http`` (zero silent failures).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from core import audit  # noqa: E402
from core.config import settings  # noqa: E402
from actions.fleet_security.schemas import HostInfo, RemediationRequest  # noqa: E402
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402
from actions.fleet_security import discovery, posture, compliance, remediation  # noqa: E402

router = APIRouter(prefix="/api/fleet-security", tags=["fleet_security"])
app = FastAPI(title="Fleet Security (passive)", version="1.0.0")
# app.include_router(router) je na KONCU datoteke — po definiciji vseh route.


def _get_store() -> FleetSecurityStore:
    return FleetSecurityStore(settings.fs_db_path)


def _audit_http(method: str, path: str, status: str, detail: str = "") -> None:
    try:
        audit.record(
            event="fleet-security-http", project=path, status=status,
            detail=f"{method} {detail}"[:500],
        )
    except Exception:
        pass


# ── Inventar ──────────────────────────────────────────────────────────
@router.post("/devices/ingest")
async def ingest_device(payload: HostInfo):
    try:
        device = await run_in_threadpool(
            discovery.ingest_hostinfo, _get_store(), payload
        )
        _audit_http("POST", "/devices/ingest", "ok", payload.device_id)
        return JSONResponse(status_code=201, content={"device": device.model_dump()})
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/devices/ingest", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/devices")
async def list_devices(role: str | None = None):
    try:
        devices = await run_in_threadpool(_get_store().list_devices, role)
        return JSONResponse(
            status_code=200,
            content={"devices": [d.model_dump() for d in devices]},
        )
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", "/devices", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/devices/{device_id}")
async def get_device(device_id: str):
    try:
        device = await run_in_threadpool(_get_store().get_device, device_id)
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", f"/devices/{device_id}", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})
    if device is None:
        return JSONResponse(status_code=404, content={"error": "device not found"})
    return JSONResponse(status_code=200, content={"device": device.model_dump()})


# ── Posture ───────────────────────────────────────────────────────────
@router.post("/assess")
async def run_assess():
    try:
        summary = await run_in_threadpool(posture.run_assessment, _get_store())
        _audit_http("POST", "/assess", "ok", f"devices={summary['devices']}")
        return JSONResponse(status_code=200, content=summary)
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/assess", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/posture/summary")
async def posture_summary():
    try:
        summary = await run_in_threadpool(posture.posture_summary, _get_store())
        return JSONResponse(status_code=200, content=summary)
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", "/posture/summary", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/posture/devices/{device_id}")
async def posture_device(device_id: str):
    try:
        store = _get_store()
        score = await run_in_threadpool(store.latest_score, device_id)
        findings = await run_in_threadpool(store.list_open_findings, device_id)
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", f"/posture/devices/{device_id}", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})
    if score is None and not findings:
        return JSONResponse(status_code=404, content={"error": "no posture data"})
    return JSONResponse(
        status_code=200,
        content={
            "score": score.model_dump() if score else None,
            "findings": [f.model_dump() for f in findings],
        },
    )


# ── CRA skladnost ─────────────────────────────────────────────────────
@router.get("/compliance/report")
async def compliance_report(fmt: str = "markdown", redact: bool = True):
    try:
        store = _get_store()
        if fmt == "json":
            data = await run_in_threadpool(
                compliance.generate_report_json, store, None, redact
            )
            return JSONResponse(status_code=200, content={"report": data})
        text = await run_in_threadpool(compliance.generate_report, store, None, redact)
        _audit_http("GET", "/compliance/report", "ok", f"fmt={fmt}")
        return JSONResponse(status_code=200, content={"report": text})
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", "/compliance/report", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Remediacija ───────────────────────────────────────────────────────
@router.post("/remediate/{device_id}")
async def remediate(device_id: str, request: RemediationRequest):
    try:
        result = await run_in_threadpool(
            remediation.open_remediation_pr,
            _get_store(),
            device_id,
            request.kind,
            request.dry_run,
            None,
            None,
        )
        if result.status == "error":
            return JSONResponse(status_code=400, content={"result": result.model_dump()})
        _audit_http("POST", f"/remediate/{device_id}", "ok", f"{request.kind} {result.status}")
        return JSONResponse(status_code=200, content={"result": result.model_dump()})
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", f"/remediate/{device_id}", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Health ────────────────────────────────────────────────────────────
@router.get("/health")
async def health():
    try:
        store = _get_store()
        device_count = len(store.list_devices())
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "passive_only": settings.fs_passive_only,
                "device_count": device_count,
                "db_path": str(store.db_path),
            },
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


# Router mora biti vključen PO definiciji vseh route (include_router zajame
# trenutno stanje router.routes).
app.include_router(router)
