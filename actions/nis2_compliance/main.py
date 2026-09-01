"""nis2_compliance — FastAPI router + app (prvi runtime-viden kos, child #3).

Vzorec: ``report_builder/main.py`` (Pydantic strict, JSONResponse 4xx/5xx) +
``fleet_security/main.py`` (``_audit_http`` — vsak handler piše audit event
``nis2-compliance-http``, zero silent failures). ``run_in_threadpool`` za
sqlite; LLM opis tveganja teče async prek ``DeepSeekLLMClient`` (fallback na
generičen opis, če LLM ni na voljo — ni blokada).
"""

from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi import APIRouter, FastAPI  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from starlette.concurrency import run_in_threadpool  # noqa: E402

from core import audit  # noqa: E402
from core.config import settings  # noqa: E402
from core.llm_client import DeepSeekLLMClient  # noqa: E402

from actions.nis2_compliance.intake import (  # noqa: E402
    intake_to_draft_evidence,
    load_question_map,
)
from actions.nis2_compliance.policies import render_all_policies  # noqa: E402
from actions.nis2_compliance.risk import build_risk_register  # noqa: E402
from actions.nis2_compliance.rules_engine import load_rules  # noqa: E402
from actions.nis2_compliance.scope import determine_scope  # noqa: E402
from actions.nis2_compliance.schemas import (  # noqa: E402
    CreateFirmRequest,
    FirmProfile,
    InvalidScopeInputError,
    ScopeInput,
    ScopeNotDeterminedError,
    UnknownFirmError,
)
from actions.nis2_compliance.store import Nis2Store  # noqa: E402

router = APIRouter(prefix="/api/nis2-compliance", tags=["nis2_compliance"])
app = FastAPI(title="NIS2 Compliance (done-for-you)", version="1.0.0")


def _now() -> int:
    return int(time.time())


def _get_store(firm_id: str) -> Nis2Store:
    return Nis2Store(Path(settings.nis2_db_root), firm_id)


def _firm_db_exists(firm_id: str) -> bool:
    """Ali per-firm DB datoteka obstaja (guard za read poti — ne ustvari prazne)."""
    return (Path(settings.nis2_db_root) / f"{firm_id}.db").is_file()


def _policies_dir() -> Path:
    return Path(__file__).resolve().parent / "rules" / "policies"


def _audit_http(method: str, path: str, status: str, detail: str = "") -> None:
    try:
        audit.record(
            event="nis2-compliance-http", project=path, status=status,
            detail=f"{method} {detail}"[:500],
        )
    except Exception:  # noqa: BLE001 — audit napaka ne sme podreti requesta
        pass


def _rules_bundle():
    return load_rules()


async def _llm_desc_fn(prompt: str) -> str:
    """LLM-draft opisa tveganja (DeepSeekLLMClient, fallback na prazen string)."""
    client = DeepSeekLLMClient()
    try:
        return await client.generate_completion(
            prompt,
            system_prompt=(
                "Ti si varnostni strokovnjak za ZInfV-1/NIS2. Opiši tveganje "
                "v eni do dveh povedih (slovenščina), brez osebnih podatkov."
            ),
            use_coder_model=False,
        )
    except Exception:  # noqa: BLE001
        return ""


# ── Firm ──────────────────────────────────────────────────────────────
@router.post("/firms")
async def create_firm(payload: CreateFirmRequest) -> JSONResponse:
    """Kreira firmo → profile + scope + intake + draft evidence v enem koraku."""
    try:
        firm_id = str(uuid.uuid4())
        now = _now()
        scope_input = ScopeInput(
            zaposleni=payload.zaposleni,
            promet_mio=payload.promet_mio,
            sektor=payload.sektor,
        )
        scope_result = await run_in_threadpool(
            determine_scope,
            scope_input,
            settings.nis2_scope_thresholds,
            settings.nis2_priloga_sectors,
        )
        profile = FirmProfile(
            firm_id=firm_id,
            naziv=payload.naziv,
            sektor=payload.sektor,
            zaposleni=payload.zaposleni,
            promet_mio=payload.promet_mio,
            kontakt=payload.kontakt,
            created_at=now,
        )
        store = _get_store(firm_id)
        await run_in_threadpool(store.create_firm, profile)
        await run_in_threadpool(store.save_scope_result, firm_id, scope_result)
        if payload.answers:
            await run_in_threadpool(store.save_intake_answers, firm_id, payload.answers)
        bundle = _rules_bundle()
        question_map = load_question_map()
        drafts = await run_in_threadpool(
            intake_to_draft_evidence,
            payload.answers,
            bundle,
            scope_result,
            question_map,
        )
        await run_in_threadpool(store.save_evidence_draft, firm_id, drafts, now)
        _audit_http("POST", "/firms", "ok", firm_id)
        return JSONResponse(
            status_code=200,
            content={
                "firm_id": firm_id,
                "profile": profile.model_dump(),
                "scope": scope_result.model_dump(),
                "evidence_count": len(drafts),
            },
        )
    except InvalidScopeInputError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", "/firms", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/firms/{firm_id}")
async def get_firm(firm_id: str) -> JSONResponse:
    """Paket: profile + scope + politike + risk register."""
    try:
        if not _firm_db_exists(firm_id):
            raise UnknownFirmError(f"Firma ne obstaja: {firm_id}")
        store = _get_store(firm_id)
        profile = await run_in_threadpool(store.get_firm, firm_id)
        if profile is None:
            raise UnknownFirmError(f"Firma ne obstaja: {firm_id}")
        scope = await run_in_threadpool(store.get_scope_result, firm_id)
        if scope is None:
            raise ScopeNotDeterminedError(f"Obseg ni določen za firmo: {firm_id}")
        evidence = await run_in_threadpool(store.get_evidence_draft, firm_id)
        bundle = _rules_bundle()
        policies = await run_in_threadpool(
            render_all_policies, _policies_dir(), profile, scope
        )
        register = await build_risk_register(
            profile, scope, evidence, bundle,
            llm_desc=False, llm_desc_fn=None, now=_now(),
        )
        _audit_http("GET", f"/firms/{firm_id}", "ok", firm_id)
        return JSONResponse(
            status_code=200,
            content={
                "firm_id": firm_id,
                "profile": profile.model_dump(),
                "scope": scope.model_dump(),
                "policies": [p.model_dump() for p in policies],
                "risk": register.model_dump(),
            },
        )
    except UnknownFirmError as e:
        _audit_http("GET", f"/firms/{firm_id}", "failed", str(e))
        return JSONResponse(status_code=404, content={"error": str(e)})
    except ScopeNotDeterminedError as e:
        _audit_http("GET", f"/firms/{firm_id}", "failed", str(e))
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001
        _audit_http("GET", f"/firms/{firm_id}", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/firms/{firm_id}/policies")
async def generate_policies(firm_id: str) -> JSONResponse:
    """Renderira politike (iz predlog) za firmo."""
    try:
        if not _firm_db_exists(firm_id):
            raise UnknownFirmError(f"Firma ne obstaja: {firm_id}")
        store = _get_store(firm_id)
        profile = await run_in_threadpool(store.get_firm, firm_id)
        if profile is None:
            raise UnknownFirmError(f"Firma ne obstaja: {firm_id}")
        scope = await run_in_threadpool(store.get_scope_result, firm_id)
        if scope is None:
            raise ScopeNotDeterminedError(f"Obseg ni določen za firmo: {firm_id}")
        policies = await run_in_threadpool(
            render_all_policies, _policies_dir(), profile, scope
        )
        _audit_http(
            "POST", f"/firms/{firm_id}/policies", "ok", f"policies={len(policies)}"
        )
        return JSONResponse(
            status_code=200, content={"policies": [p.model_dump() for p in policies]}
        )
    except UnknownFirmError as e:
        _audit_http("POST", f"/firms/{firm_id}/policies", "failed", str(e))
        return JSONResponse(status_code=404, content={"error": str(e)})
    except ScopeNotDeterminedError as e:
        _audit_http("POST", f"/firms/{firm_id}/policies", "failed", str(e))
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", f"/firms/{firm_id}/policies", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/firms/{firm_id}/risk")
async def assess_risk(firm_id: str) -> JSONResponse:
    """Oceni tveganja (register + LLM opis, če je na voljo)."""
    try:
        if not _firm_db_exists(firm_id):
            raise UnknownFirmError(f"Firma ne obstaja: {firm_id}")
        store = _get_store(firm_id)
        profile = await run_in_threadpool(store.get_firm, firm_id)
        if profile is None:
            raise UnknownFirmError(f"Firma ne obstaja: {firm_id}")
        scope = await run_in_threadpool(store.get_scope_result, firm_id)
        if scope is None:
            raise ScopeNotDeterminedError(f"Obseg ni določen za firmo: {firm_id}")
        evidence = await run_in_threadpool(store.get_evidence_draft, firm_id)
        bundle = _rules_bundle()
        use_llm = settings.nis2_risk_llm_desc and settings.is_real_key_available()
        register = await build_risk_register(
            profile,
            scope,
            evidence,
            bundle,
            llm_desc=settings.nis2_risk_llm_desc,
            llm_desc_fn=_llm_desc_fn if use_llm else None,
            now=_now(),
        )
        _audit_http(
            "POST", f"/firms/{firm_id}/risk", "ok", f"items={len(register.items)}"
        )
        return JSONResponse(status_code=200, content=register.model_dump())
    except UnknownFirmError as e:
        _audit_http("POST", f"/firms/{firm_id}/risk", "failed", str(e))
        return JSONResponse(status_code=404, content={"error": str(e)})
    except ScopeNotDeterminedError as e:
        _audit_http("POST", f"/firms/{firm_id}/risk", "failed", str(e))
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:  # noqa: BLE001
        _audit_http("POST", f"/firms/{firm_id}/risk", "failed", str(e))
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/health")
async def health() -> JSONResponse:
    """Health — preveri tudi, da se pravila naložijo."""
    try:
        _rules_bundle()
        return JSONResponse(status_code=200, content={"status": "ok"})
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=500, content={"status": "error", "error": str(e)})


app.include_router(router)
