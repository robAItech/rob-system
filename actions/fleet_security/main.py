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
from actions.fleet_security.schemas import (  # noqa: E402
    HostInfo,
    ModelRecordRequest,
    NetworkObservation,
    PromptHardeningRequest,
    RedTeamRunRequest,
    RemediationRequest,
    TelemetrySample,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402
from actions.fleet_security import (  # noqa: E402
    discovery,
    posture,
    compliance,
    remediation,
    monitor,
    redteam,
    supplychain,
    threatintel,
)

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


# ── Monitor (Phase 2, Skin A) ─────────────────────────────────────────
@router.post("/monitor/telemetry")
async def ingest_telemetry(payload: TelemetrySample):
    try:
        res = await run_in_threadpool(monitor.ingest_telemetry, _get_store(), payload)
        _audit_http("POST", "/monitor/telemetry", "ok", payload.device_id)
        return JSONResponse(status_code=201, content=res)
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/monitor/telemetry", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/monitor/network")
async def ingest_network(payload: NetworkObservation):
    try:
        res = await run_in_threadpool(
            monitor.ingest_network_observation, _get_store(), payload
        )
        _audit_http("POST", "/monitor/network", "ok", payload.device_id)
        return JSONResponse(status_code=201, content=res)
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/monitor/network", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/monitor/run")
async def run_monitor():
    try:
        summary = await run_in_threadpool(monitor.run_monitor_pass, _get_store())
        _audit_http(
            "POST", "/monitor/run", "ok",
            f"findings={summary['findings_detected']}",
        )
        return JSONResponse(status_code=200, content=summary)
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/monitor/run", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/monitor/anomalies")
async def monitor_anomalies(device_id: str | None = None):
    try:
        findings = await run_in_threadpool(_get_store().list_open_findings, device_id)
        monitor_findings = [
            f.model_dump()
            for f in findings
            if f.category in monitor.MONITOR_CATEGORIES
        ]
        return JSONResponse(status_code=200, content={"findings": monitor_findings})
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", "/monitor/anomalies", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/monitor/summary")
async def monitor_summary_ep():
    try:
        summary = await run_in_threadpool(monitor.monitor_summary, _get_store())
        return JSONResponse(status_code=200, content=summary)
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", "/monitor/summary", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Red team (Phase 3, SIMULACIJA samo) ──────────────────────────────
@router.post("/redteam/run")
async def redteam_run(payload: RedTeamRunRequest):
    try:
        target = redteam.MockBrainTarget(secure=payload.mock_mode == "secure")
        policy = (
            tuple(payload.policy) if payload.policy is not None else None
        )
        selected = None
        if payload.payload_ids is not None:
            by_id = {p["id"]: p for p in redteam.PAYLOAD_LIBRARY}
            selected = [by_id[i] for i in payload.payload_ids if i in by_id]
        res = await run_in_threadpool(
            redteam.run_red_team, _get_store(), payload.robot_id, target,
            payload.system_prompt, policy, selected, None,
        )
        _audit_http("POST", "/redteam/run", "ok", payload.robot_id)
        return JSONResponse(status_code=200, content=res)
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/redteam/run", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/redteam/runs")
async def redteam_runs(device_id: str | None = None):
    try:
        runs = await run_in_threadpool(_get_store().list_redteam_runs, device_id)
        return JSONResponse(status_code=200, content={"runs": runs})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/redteam/harden")
async def redteam_harden(payload: PromptHardeningRequest):
    try:
        hardened, diff = redteam.harden_system_prompt(payload.system_prompt)
        _audit_http("POST", "/redteam/harden", "ok", payload.robot_id)
        return JSONResponse(status_code=200, content={"hardened": hardened, "diff": diff})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/redteam/harden/pr")
async def redteam_harden_pr(payload: PromptHardeningRequest):
    try:
        result = await run_in_threadpool(
            redteam.open_prompt_hardening_pr, _get_store(), payload.robot_id,
            payload.system_prompt, payload.dry_run, None, None,
        )
        _audit_http("POST", "/redteam/harden/pr", "ok", payload.robot_id)
        return JSONResponse(status_code=200, content={"result": result.model_dump()})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Supply chain (Phase 3) ───────────────────────────────────────────
@router.post("/supplychain/record")
async def supplychain_record(payload: ModelRecordRequest):
    try:
        row_id = await run_in_threadpool(
            supplychain.record_model, _get_store(), payload.device_id,
            payload.model, payload.pushed_by, payload.pushed_at,
            payload.repo_url, None,
        )
        _audit_http("POST", "/supplychain/record", "ok", payload.device_id)
        return JSONResponse(
            status_code=201, content={"id": row_id, "device_id": payload.device_id}
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/supplychain/check")
async def supplychain_check():
    try:
        res = await run_in_threadpool(supplychain.run_supplychain_pass, _get_store())
        _audit_http("POST", "/supplychain/check", "ok", f"findings={res['findings_detected']}")
        return JSONResponse(status_code=200, content=res)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/supplychain/history")
async def supplychain_history(device_id: str | None = None):
    try:
        history = await run_in_threadpool(_get_store().list_model_history, device_id)
        return JSONResponse(status_code=200, content={"history": history})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


# ── Threat intel (Phase 3) ───────────────────────────────────────────
@router.post("/threatintel/check")
async def threatintel_check():
    try:
        res = await run_in_threadpool(threatintel.run_threatintel_pass, _get_store())
        _audit_http("POST", "/threatintel/check", "ok", f"findings={res['findings_detected']}")
        return JSONResponse(status_code=200, content=res)
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/threatintel/feed")
async def threatintel_feed():
    try:
        advisories = await run_in_threadpool(threatintel.load_feed)
        return JSONResponse(
            status_code=200,
            content={"advisories": [a.model_dump() for a in advisories]},
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"error": str(e)})


# Router mora biti vključen PO definiciji vseh route (include_router zajame
# trenutno stanje router.routes).
app.include_router(router)
