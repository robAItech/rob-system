"""fleet_security — posture scoring, eskalacija, regression snapshots.

Deterministično, brez LLM. Formula: ``score = max(0, 100 − Σ severity_weights
nad OPEN najdbami)``; grade A≥90 / B≥80 / C≥70 / D≥60 / F<60.

Eskalacija pod pragom → ``core.quality.record_escalation`` (globalni
`.rob_ai/escalations.json` + audit ``escalation``), idempotentno. Regression
med pass-oma → meta_eval stil (agregatni snapshot v fs_scores, device_id='*').

Vzorec eskalacije: core/quality.py. Vzorec snapshot/compare: core/meta_eval.py.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import quality  # noqa: E402
from core.config import settings  # noqa: E402
from actions.fleet_security import discovery  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    ANY_VALUE,
    Baseline,
    Device,
    PostureFinding,
    PostureScore,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

#: Privzete uteži severity (preglasijo se z settings.fs_severity_weights).
SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 25,
    "high": 15,
    "medium": 8,
    "low": 3,
}

GRADE_THRESHOLDS: tuple[tuple[int, str], ...] = ((90, "A"), (80, "B"), (70, "C"), (60, "D"))

#: Kategorija → privzeta severity (config_drift se lahko dvigne na critical).
#: Phase 2 monitor kategorije so dokumentacijsko "monitor" — severity nastavi
#: monitor.py eksplicitno (odvisno od |z| oz. tipa egress najdbe).
POSTURE_CATEGORY_SEVERITY: dict[str, str] = {
    "os_version_drift": "high",
    "firmware_drift": "high",
    "firmware_unknown": "medium",
    "model_provenance": "medium",
    "config_drift": "high",
    "stale_heartbeat": "high",
    "missing_device": "critical",
    "telemetry_anomaly": "monitor",
    "unknown_egress": "monitor",
    "egress_anomaly": "monitor",
    # Phase 3 — premium moduli. Dokumentacijski sentinel: realno severity
    # postavi vsak modul eksplicitno (Pydantic regex ne dovoli "informational").
    "redteam_injection": "informational",
    "model_changed": "informational",
    "model_unverified": "informational",
    "known_vulnerability": "informational",
}

#: Kategorije, ki jih piše/resolve-a posture pass (scope za resolve_categories).
#: Monitor kategorije so izključene — posture NE clobber-a monitor najdb.
POSTURE_OWNED_CATEGORIES = frozenset({
    "os_version_drift",
    "firmware_drift",
    "firmware_unknown",
    "model_provenance",
    "config_drift",
    "stale_heartbeat",
    "missing_device",
})


def _now() -> int:
    import time

    return int(time.time())


def _parse_severity_weights(raw: str) -> dict[str, int]:
    """Parse "critical:25,high:15,..." → {severity: weight}. Tolerantno."""
    out = dict(SEVERITY_WEIGHTS)
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        key, _, val = chunk.partition(":")
        key = key.strip()
        try:
            out[key] = int(val)
        except ValueError:
            continue
    return out


def severity_weights() -> dict[str, int]:
    return _parse_severity_weights(settings.fs_severity_weights)


def compute_score(counts: dict[str, int]) -> tuple[int, str]:
    """score iz števcev severity; grade A–F."""
    weights = severity_weights()
    total = sum(weights.get(sev, 0) * int(counts.get(sev, 0)) for sev in weights)
    score = max(0, 100 - total)
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return score, grade
    return score, "F"


def _count_severities(findings: list[PostureFinding]) -> dict[str, int]:
    counts: dict[str, int] = {sev: 0 for sev in ("critical", "high", "medium", "low")}
    for f in findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return counts


def _grade_for_score(score: int) -> str:
    for threshold, grade in GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"


# ------------------------------------------------------------------ #
#  assess_device (čisto, brez I/O)
# ------------------------------------------------------------------ #
def assess_device(
    device: Device, baseline: Baseline | None, now: int | None = None
) -> list[PostureFinding]:
    """Primerja napravo z baseline-om → najdbe (brez heartbeat najdb)."""
    now = int(now) if now is not None else _now()
    findings: list[PostureFinding] = []

    def _finding(category: str, severity: str, detail: str) -> PostureFinding:
        return PostureFinding(
            device_id=device.device_id,
            category=category,
            severity=severity,
            detail=detail,
            detected_at=now,
        )

    # OS drift.
    if baseline is not None:
        diffs: list[str] = []
        if baseline.os_name and device.os.name != baseline.os_name:
            diffs.append(f"os={device.os.name} (expected {baseline.os_name})")
        if baseline.os_version and device.os.version != baseline.os_version:
            diffs.append(f"version={device.os.version} (expected {baseline.os_version})")
        if baseline.os_kernel and device.os.kernel != baseline.os_kernel:
            diffs.append(f"kernel={device.os.kernel} (expected {baseline.os_kernel})")
        if diffs:
            findings.append(
                _finding("os_version_drift", "high", "os drift: " + "; ".join(diffs))
            )

    # Firmware drift / unknown.
    if baseline is not None:
        drift_parts: list[str] = []
        for comp, expected in baseline.firmware.items():
            actual = next(
                (f.version for f in device.firmware if f.component == comp), None
            )
            if actual is not None and actual != expected:
                drift_parts.append(f"{comp}={actual} (expected {expected})")
        if drift_parts:
            findings.append(
                _finding("firmware_drift", "high", "firmware drift: " + "; ".join(drift_parts))
            )
        known = set(baseline.firmware.keys())
        unknown = [f.component for f in device.firmware if f.component not in known]
        if unknown:
            findings.append(
                _finding(
                    "firmware_unknown",
                    "medium",
                    "firmware components not in baseline: " + ", ".join(sorted(unknown)),
                )
            )
    elif device.firmware:
        findings.append(
            _finding(
                "firmware_unknown",
                "medium",
                "firmware present, no baseline: "
                + ", ".join(sorted(c.component for c in device.firmware)),
            )
        )

    # Model provenance.
    if device.model is not None and (
        not device.model.sha256 or not device.model.provider
    ):
        findings.append(
            _finding(
                "model_provenance",
                "medium",
                "model artifact hash/provenance unknown",
            )
        )
    elif (
        baseline is not None
        and baseline.model_sha256
        and (device.model is None or device.model.sha256 not in baseline.model_sha256)
    ):
        findings.append(
            _finding(
                "model_provenance",
                "medium",
                f"model sha256 not in known-good set: {device.model.sha256 if device.model else 'none'}",
            )
        )

    # Config drift (required keys + insecure defaults).
    if baseline is not None:
        missing = [
            key for key in baseline.required_config_keys if key not in device.config
        ]
        mismatch: list[str] = []
        for key, expected in baseline.required_config_keys.items():
            if key in device.config and expected is not ANY_VALUE and device.config[key] != expected:
                mismatch.append(f"{key}={device.config[key]} (expected {expected!r})")
        if missing:
            findings.append(
                _finding("config_drift", "high", "missing required keys: " + ", ".join(sorted(missing)))
            )
        if mismatch:
            findings.append(
                _finding("config_drift", "high", "config mismatch: " + "; ".join(mismatch))
            )
        insecure = [
            f"{key}={device.config[key]!r}"
            for key, bad in baseline.secure_default_checks.items()
            if key in device.config and device.config[key] == bad
        ]
        if insecure:
            findings.append(
                _finding("config_drift", "critical", "insecure defaults: " + "; ".join(insecure))
            )

    return findings


# ------------------------------------------------------------------ #
#  Baselines (store → YAML seed → inline default)
# ------------------------------------------------------------------ #
def _default_local_baseline(role: str) -> Baseline:
    """Inline default za local role — dogfooding deluje out-of-the-box.

    Dovolj strogo, da da prave najdbe na tipičnem dev hostu (npr.
    firmware_unknown, model_provenance), a ne zahteva manualnega baseline-a.
    """
    return Baseline(
        role=role,
        required_config_keys={"node_uuid": ANY_VALUE},
        secure_default_checks={"allow_anonymous": True, "password": ""},
        heartbeat_max_age_seconds=settings.fs_heartbeat_max_age_seconds,
    )


def load_baselines(store: FleetSecurityStore) -> dict[str, Baseline]:
    """Baseline-i: YAML v fs_baselines_dir → store → inline default.

    **YAML je source of truth** za role, ki so v njem definirani: ob vsakem
    load-u se upsert-a v fs_baselines tabelo, da jih vidita tudi remediacija
    in compliance (store.get_baseline). Role, definirani samo v tabeli,
    ostanejo. Inline default se NE persistira (mehak fallback).
    """
    baselines: dict[str, Baseline] = {}

    # YAML seed (.rob_ai/fleet_security_baselines/*.yaml) → persistiraj.
    import yaml

    yaml_dir = Path(settings.fs_baselines_dir)
    if not yaml_dir.is_absolute():
        yaml_dir = PROJECT_ROOT / yaml_dir
    if yaml_dir.is_dir():
        for path in sorted(yaml_dir.glob("*.yaml")):
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                continue
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict) or not item.get("role"):
                    continue
                try:
                    bl = Baseline.from_jsonable(item)
                except Exception:
                    continue
                baselines[bl.role] = bl
                store.upsert_baseline(bl)

    # Store: YAML role-i so že notri (po upsertu), store-only role-i se dodajo.
    for baseline in store.list_baselines():
        baselines[baseline.role] = baseline

    # Inline default za local role (če ga ni drugje).
    baselines.setdefault(settings.fleet_role, _default_local_baseline(settings.fleet_role))
    return baselines


# ------------------------------------------------------------------ #
#  Eskalacija + regression
# ------------------------------------------------------------------ #
def _escalate(device_id: str, score: int, grade: str) -> bool:
    """Idempotentna eskalacija pod pragom (quality.record_escalation)."""
    try:
        return quality.record_escalation(
            project=f"fleet-security:{device_id}",
            reason="posture score below threshold",
            detail=f"score={score} grade={grade}",
        )
    except Exception:
        return False


def compare_snapshots(prev: dict, cur: dict, drop_points: int) -> dict:
    """meta_eval stil: regression med dvema agregatnima snapshot-oma.

    ``regressed`` = mean padec > drop_points ALI porast open critical.
    Vhoda imata ključa ``mean_score`` (int|None) in ``open_critical`` (int).
    """
    p_mean = prev.get("mean_score")
    c_mean = cur.get("mean_score")
    p_crit = int(prev.get("open_critical", 0) or 0)
    c_crit = int(cur.get("open_critical", 0) or 0)
    mean_delta = None
    if p_mean is not None and c_mean is not None:
        mean_delta = round(float(c_mean) - float(p_mean), 1)
    regressed = (c_crit > p_crit) or (
        mean_delta is not None and mean_delta < -drop_points
    )
    return {
        "regressed": regressed,
        "mean_delta": mean_delta,
        "critical_delta": c_crit - p_crit,
        "before": prev,
        "after": cur,
    }


def _aggregate_snapshot(store: FleetSecurityStore, now: int) -> dict:
    devices = store.list_devices()
    scores = [
        store.latest_score(d.device_id) for d in devices
    ]
    valid = [s.score for s in scores if s]
    mean = round(sum(valid) / len(valid), 1) if valid else None
    open_findings = store.list_open_findings()
    n_crit = sum(1 for f in open_findings if f.severity == "critical")
    n_high = sum(1 for f in open_findings if f.severity == "high")
    return {
        "device_count": len(devices),
        "mean_score": mean,
        "open_critical": n_crit,
        "open_high": n_high,
    }


# ------------------------------------------------------------------ #
#  Orchestracija
# ------------------------------------------------------------------ #
def run_assessment(
    store: FleetSecurityStore,
    now: int | None = None,
    escalate_below: int | None = None,
) -> dict:
    """En poln PASSIVEN prehod: assess vseh naprav + eskalacija + regression.

    1. baselines (load_baselines)
    2. heartbeat najdbe (discovery.check_heartbeats)
    3. per-naprava: assess_device → upsert_findings + save_score
    4. score < prag → eskalacija (idempotentno)
    5. agregatni snapshot ('*') + regression compare (meta_eval stil)
    """
    now = int(now) if now is not None else _now()
    baselines = load_baselines(store)
    heartbeat = discovery.check_heartbeats(store, now=now)
    hb_by_device = {f.device_id: f for f in heartbeat}

    threshold = (
        escalate_below
        if escalate_below is not None
        else settings.fs_score_escalate_below
    )

    escalated: list[str] = []
    device_scores: dict[str, int] = {}
    all_findings: list[PostureFinding] = []

    devices = store.list_devices()
    assessed_ids = [d.device_id for d in devices]
    for device in devices:
        device_findings = assess_device(device, baselines.get(device.role), now=now)
        hb = hb_by_device.get(device.device_id)
        if hb is not None:
            device_findings.append(hb)
        all_findings.extend(device_findings)

    # En sam upsert za vse najdbe (vključno s sintetičnimi missing_device).
    # resolve_categories=POSTURE_OWNED_CATEGORIES: posture resolve-a SAMO svoje
    # kategorije — monitor najdb se ne dotika (Phase 2, cross-category clobber fix).
    inserted_total = store.upsert_findings(
        all_findings,
        now=now,
        assessed=assessed_ids,
        resolve_categories=POSTURE_OWNED_CATEGORIES,
    )
    inserted_total += store.resolve_missing_for_roles(
        [d.role for d in devices], now=now
    )

    # Score iz OPEN najdb (po upsertu) — monitor najdbe znižajo posture score
    # (dokumentirana semantika: score = 100 − Σ weights nad OPEN najdbami).
    for device in devices:
        counts = _count_severities(store.list_open_findings(device.device_id))
        score, grade = compute_score(counts)
        store.save_score(device.device_id, score, grade, counts, now)
        device_scores[device.device_id] = score
        if score < threshold:
            if _escalate(device.device_id, score, grade):
                escalated.append(device.device_id)

    # Regression: primerjaj z PREDHODNIM '*'-snapshot-om pred shranitvijo novega.
    prev_row = store.latest_score("*")
    if prev_row:
        prev = {
            "mean_score": prev_row.score,
            "open_critical": int(prev_row.counts.get("open_critical", 0)),
        }
    else:
        prev = {"mean_score": None, "open_critical": 0}

    agg = _aggregate_snapshot(store, now)
    agg_score = int(agg["mean_score"]) if agg["mean_score"] is not None else 0
    store.save_score(
        "*",
        agg_score,
        _grade_for_score(agg_score),
        {
            "open_critical": agg["open_critical"],
            "open_high": agg["open_high"],
            "device_count": agg["device_count"],
        },
        now,
    )

    reg = compare_snapshots(
        prev, {"mean_score": agg["mean_score"], "open_critical": agg["open_critical"]},
        settings.fs_regression_drop_points,
    )
    if reg["regressed"]:
        try:
            from core import audit

            audit.record(
                event="fleet-security-regression",
                project="*",
                status="critical",
                detail=f"mean_delta={reg['mean_delta']} critical_delta={reg['critical_delta']}",
            )
        except Exception:
            pass

    return {
        "devices": len(device_scores),
        "scores": device_scores,
        "escalated": escalated,
        "mean_score": agg["mean_score"],
        "open_critical": agg["open_critical"],
        "open_high": agg["open_high"],
        "regressed": reg["regressed"],
        "findings_inserted": inserted_total,
    }


def posture_summary(store: FleetSecurityStore) -> dict:
    """Povzetek: per-naprava latest score + agregat (mean, grade histogram)."""
    devices = store.list_devices()
    per_device: list[dict[str, Any]] = []
    grades: dict[str, int] = {}
    for device in devices:
        score = store.latest_score(device.device_id)
        entry: dict[str, Any] = {
            "device_id": device.device_id,
            "role": device.role,
            "hostname": device.hostname,
        }
        if score:
            entry["score"] = score.score
            entry["grade"] = score.grade
            entry["counts"] = score.counts
            grades[score.grade] = grades.get(score.grade, 0) + 1
        per_device.append(entry)

    agg = _aggregate_snapshot(store, _now())
    open_findings = store.list_open_findings()
    by_severity: dict[str, int] = {}
    for f in open_findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1

    return {
        "devices": per_device,
        "device_count": agg["device_count"],
        "mean_score": agg["mean_score"],
        "grades": grades,
        "findings_by_severity": by_severity,
    }
