"""fleet_security — Model Supply-Chain Verifikacija (Phase 3).

Provenance registry (``fs_model_history``) + change detekcija za AI modele na
napravah. Najdbe → isti fs_findings tok (posture + CRA + eskalacija).

Pravila:
- **first-seen** (device z modelom, brez zgodovine, sha256 prisoten) →
  zabeleži kot baseline, BREZ findinga (pasivna limitacija: tampered model
  ob prvem ingestu ni zaznaven).
- **model_changed** (sha256 ali version različen od zadnjega zapisa) → high;
  detail je STABILEN (brez timestampa) → dedup/resolve delujeta. Resolve je
  samo prek eksplicitne ``record_model`` (operater/CI zabeleži nov artifact).
- **model_unverified** (model brez sha256 / brez provenance) → medium.

``check_supply_chain`` NIKOLI ne auto-record-a spremenjenega modela — sicer bi
se finding sam resolve-al v istem pass-u.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402
from actions.fleet_security.schemas import ModelInfo, PostureFinding  # noqa: E402
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

SUPPLYCHAIN_CATEGORIES = frozenset({"model_changed", "model_unverified"})


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Provenance registry
# ------------------------------------------------------------------ #
def record_model(
    store: FleetSecurityStore,
    device_id: str,
    model: ModelInfo,
    pushed_by: str | None = None,
    pushed_at: int | None = None,
    repo_url: str | None = None,
    now: int | None = None,
) -> int:
    """Zabeleži model v history — SAMO če se sha256/version razlikuje od zadnjega.

    Vrne id novega zapisa ali 0 (ni spremembe).
    """
    now = int(now) if now is not None else _now()
    latest = store.latest_model_record(device_id)
    if latest is not None:
        if latest["sha256"] == model.sha256 and latest["model_version"] == model.version:
            return 0
    return store.append_model_record(
        device_id=device_id,
        model_name=model.name,
        model_version=model.version,
        sha256=model.sha256,
        provider=model.provider,
        pushed_by=pushed_by,
        pushed_at=int(pushed_at) if pushed_at is not None else None,
        repo_url=repo_url,
        ts=now,
    )


# ------------------------------------------------------------------ #
#  Preverjanje (pass)
# ------------------------------------------------------------------ #
def check_supply_chain(
    store: FleetSecurityStore, now: int | None = None
) -> list[PostureFinding]:
    """Primerjaj trenutni model naprav z zadnjim zapisom v history-ju."""
    now = int(now) if now is not None else _now()
    findings: list[PostureFinding] = []

    for device in store.list_devices():
        model = device.model
        if model is None:
            continue
        latest = store.latest_model_record(device.device_id)

        if latest is None:
            # First-seen: baseline, brez findinga (če je sha256 prisoten).
            if not model.sha256:
                findings.append(
                    PostureFinding(
                        device_id=device.device_id,
                        category="model_unverified",
                        severity="medium",
                        detail="model sha256 missing, provenance not verifiable",
                        detected_at=now,
                    )
                )
            else:
                record_model(store, device.device_id, model, now=now)
            continue

        if model.sha256 != latest["sha256"] or model.version != latest["model_version"]:
            # Sprememba — finding; NE auto-record (resolve samo prek record_model).
            findings.append(
                PostureFinding(
                    device_id=device.device_id,
                    category="model_changed",
                    severity="high",
                    detail=(
                        f"model changed: {model.name} {model.version} "
                        f"sha256={model.sha256} "
                        f"(latest {latest['model_name']} {latest['model_version']} "
                        f"sha256={latest['sha256']})"
                    ),
                    detected_at=now,
                )
            )
        elif not model.sha256:
            findings.append(
                PostureFinding(
                    device_id=device.device_id,
                    category="model_unverified",
                    severity="medium",
                    detail="model sha256 missing, provenance not verifiable",
                    detected_at=now,
                )
            )

    return findings


def run_supplychain_pass(
    store: FleetSecurityStore, now: int | None = None
) -> dict:
    """En supply-chain pass: check → upsert (scope: supplychain kategorije) → audit."""
    now = int(now) if now is not None else _now()
    findings = check_supply_chain(store, now=now)

    assessed: set[str] = {
        d.device_id for d in store.list_devices() if d.model is not None
    }
    for f in store.list_open_findings():
        if f.category in SUPPLYCHAIN_CATEGORIES:
            assessed.add(f.device_id)

    inserted = store.upsert_findings(
        findings, now=now, assessed=sorted(assessed),
        resolve_categories=SUPPLYCHAIN_CATEGORIES,
    )
    try:
        audit.record(
            event="fleet-security-supplychain",
            project="*",
            status="ok",
            detail=f"findings={len(findings)} inserted={inserted}",
        )
    except Exception:
        pass
    return {
        "findings_detected": len(findings),
        "findings_inserted": inserted,
        "assessed_devices": len(assessed),
    }


def supplychain_summary(
    store: FleetSecurityStore, device_id: str | None = None
) -> dict:
    """Povzetek: model history + odprte supply-chain najdbe."""
    history = store.list_model_history(device_id)
    open_findings = [
        f for f in store.list_open_findings(device_id)
        if f.category in SUPPLYCHAIN_CATEGORIES
    ]
    return {
        "history_records": len(history),
        "open_findings": len(open_findings),
        "by_category": {
            cat: sum(1 for f in open_findings if f.category == cat)
            for cat in SUPPLYCHAIN_CATEGORIES
        },
        "last_record_ts": history[-1]["ts"] if history else None,
    }
