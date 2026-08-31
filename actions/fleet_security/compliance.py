"""fleet_security — CRA (EU Cyber Resilience Act) skladnostni report.

Kurirana preslikava najpomembnejših varnostnih zahtev CRA Annex I na dokaze
iz inventarja + najdb + audit loga + remediacij. Deterministično, brez LLM.

Omejitve Faze 1 (CEO review):
- REQ-03 (firmware update) → **partial by design**: firmware je report-only,
  fix gre skozi OEM.
- REQ-07 (disclosure) → **partial**: PR-ji so human-in-the-loop, ENISA kanal ni.
- PII redakcija: ``redact=True`` (privzeto) maskira email/telefon/IBAN prek
  ``actions/pii_masking_sanitizer``.

Report je Markdown (vzorec: core/report.py) + strojno berljiva JSON različica.
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    ComplianceReportSection,
    Device,
    PostureFinding,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402


def _now() -> int:
    return int(time.time())


#: Kurirana CRA Annex I preslikava (razširljiva — dodaj zahteve sem).
CRA_REQUIREMENTS: list[dict[str, Any]] = [
    {
        "requirement_id": "REQ-01",
        "title": "Secure by default",
        "annex_ref": "CRA Annex I Part I §1(a); Art. 13",
        "related_categories": [
            "config_drift",
            # Phase 3 — red team pokaže prompt-injection ranljivosti action-decider-ja.
            "redteam_injection",
        ],
    },
    {
        "requirement_id": "REQ-02",
        "title": "Vulnerability handling (no known exploitable vulns in default config)",
        "annex_ref": "CRA Annex I Part I §2(a)",
        "related_categories": [
            "firmware_drift",
            "model_provenance",
            "os_version_drift",
            # Phase 2 — nepooblaščen/neznan omrežni egress = izpostavljenost.
            "unknown_egress",
            "egress_anomaly",
            # Phase 3 — znane ranljivosti (threat intel feed).
            "known_vulnerability",
        ],
    },
    {
        "requirement_id": "REQ-03",
        "title": "Secure update mechanisms",
        "annex_ref": "CRA Annex I Part I §3",
        "related_categories": ["firmware_drift", "firmware_unknown"],
    },
    {
        "requirement_id": "REQ-04",
        "title": "Integrity & tamper protection of critical components",
        "annex_ref": "CRA Annex I Part I §5(a)",
        "related_categories": [
            "model_provenance",
            # Phase 3 — supply chain: spremenjen/neverificiran model.
            "model_changed",
            "model_unverified",
        ],
    },
    {
        "requirement_id": "REQ-05",
        "title": "Logging, monitoring & access control for security-relevant events",
        "annex_ref": "CRA Annex I Part I §5(j)",
        "related_categories": [],
        "evidence_from": "audit",
    },
    {
        "requirement_id": "REQ-06",
        "title": "Minimal data exposure",
        "annex_ref": "CRA Annex I Part I §5(d)",
        "related_categories": [],
        "evidence_from": "redaction",
    },
    {
        "requirement_id": "REQ-07",
        "title": "Vulnerability reporting to authority / disclosure",
        "annex_ref": "CRA Annex I Part II §1; Art. 14(7)",
        "related_categories": [],
        "evidence_from": "remediations",
    },
]

_CRITICAL_SEVERITIES = {"critical", "high"}


# ------------------------------------------------------------------ #
#  Pomožne
# ------------------------------------------------------------------ #
def _has_fleet_audit() -> bool:
    """Ali obstaja vsaj en fleet-security audit event (REQ-05 dokaz)."""
    if not audit.AUDIT_FILE.exists():
        return False
    try:
        for line in audit.AUDIT_FILE.read_text(encoding="utf-8").strip().split("\n"):
            try:
                event = json.loads(line).get("event", "")
            except Exception:
                continue
            if event.startswith("fleet-security"):
                return True
    except OSError:
        return False
    return False


def _redact(text: str, masker: Any, redact: bool) -> str:
    if not redact:
        return text
    return masker.redact_text(text)


def _iso(now: int) -> str:
    return datetime.fromtimestamp(now, tz=timezone.utc).isoformat()


def _by_category(findings: list[PostureFinding]) -> dict[str, list[PostureFinding]]:
    out: dict[str, list[PostureFinding]] = defaultdict(list)
    for f in findings:
        out[f.category].append(f)
    return out


# ------------------------------------------------------------------ #
#  Statusi + dokazi
# ------------------------------------------------------------------ #
def _build_sections(
    store: FleetSecurityStore,
    devices: list[Device],
    findings_by_cat: dict[str, list[PostureFinding]],
    redacted: bool,
) -> list[ComplianceReportSection]:
    has_devices = bool(devices)
    has_audit = _has_fleet_audit()
    open_criticals = [
        f for f in findings_by_cat.get("config_drift", []) if f.severity == "critical"
    ] + [
        f for f in store.list_open_findings()
        if f.severity == "critical" and f.category != "config_drift"
    ]

    sections: list[ComplianceReportSection] = []
    for req in CRA_REQUIREMENTS:
        rid = req["requirement_id"]
        related = [
            f for cat in req.get("related_categories", [])
            for f in findings_by_cat.get(cat, [])
        ]
        related_high = [f for f in related if f.severity in _CRITICAL_SEVERITIES]

        # Status.
        if not has_devices and req.get("evidence_from") != "audit":
            status = "not_applicable"
        elif rid == "REQ-01":
            status = "non_compliant" if related else "compliant"
        elif rid == "REQ-02":
            status = "non_compliant" if related_high else "compliant"
        elif rid == "REQ-03":
            status = "partial" if related else "compliant"
        elif rid == "REQ-04":
            status = "partial" if related else "compliant"
        elif rid == "REQ-05":
            status = "compliant" if has_audit else "not_applicable"
        elif rid == "REQ-06":
            status = "compliant" if redacted else "partial"
        elif rid == "REQ-07":
            unhandled = [
                f for f in open_criticals
                if not store.list_remediations(f.device_id)
            ]
            status = "non_compliant" if unhandled else "partial"
        else:
            status = "not_applicable"

        # Dokazi.
        evidence: list[str] = []
        if not has_devices and req.get("evidence_from") != "audit":
            evidence = ["no devices registered in inventory"]
        elif rid == "REQ-01":
            evidence = [f.detail for f in related] if related else ["no open config_drift findings"]
        elif rid == "REQ-02":
            evidence = [f.detail for f in related_high] if related_high else ["no open high/critical findings in related categories"]
        elif rid == "REQ-03":
            evidence = (
                [f"{f.device_id}: {f.detail} (report-only, fix via OEM)" for f in related]
                if related
                else ["no open firmware findings"]
            )
        elif rid == "REQ-04":
            evidence = [f.detail for f in related] if related else ["no open model_provenance findings"]
        elif rid == "REQ-05":
            evidence = (
                ["fleet-security audit events present"]
                if has_audit
                else ["no fleet-security audit events recorded"]
            )
        elif rid == "REQ-06":
            evidence = (
                ["report emitted with PII redaction"]
                if redacted
                else ["PII redaction disabled"]
            )
        elif rid == "REQ-07":
            rems = store.list_remediations()
            if rems:
                evidence = [f"PR/remediation {r['status']} for {r['device_id']} ({r['kind']})" for r in rems[-5:]]
            else:
                evidence = ["no remediation PRs yet (human-in-the-loop)"]
            if unhandled:
                evidence.append(f"{len(unhandled)} open critical finding(s) without remediation")

        sections.append(
            ComplianceReportSection(
                requirement_id=rid,
                title=req["title"],
                annex_ref=req["annex_ref"],
                status=status,  # type: ignore[arg-type]
                evidence=evidence,
                related_findings=[f.detail for f in related[:20]],
            )
        )
    return sections


# ------------------------------------------------------------------ #
#  Report generator
# ------------------------------------------------------------------ #
def generate_report_json(
    store: FleetSecurityStore,
    now: int | None = None,
    redact: bool = True,
) -> dict[str, Any]:
    """Strojno berljiv report: {generated_at, fleet_summary, devices, findings, requirements}."""
    now = int(now) if now is not None else _now()
    devices = store.list_devices()
    findings = store.list_open_findings()
    findings_by_cat = _by_category(findings)

    per_device: list[dict[str, Any]] = []
    for device in devices:
        score = store.latest_score(device.device_id)
        entry: dict[str, Any] = {
            "device_id": device.device_id,
            "role": device.role,
            "hostname": device.hostname,
            "os": f"{device.os.name} {device.os.version}".strip(),
            "last_seen_ts": device.last_seen_ts,
        }
        if score:
            entry["score"] = score.score
            entry["grade"] = score.grade
        per_device.append(entry)

    return {
        "generated_at": _iso(now),
        "redacted": redact,
        "fleet_summary": {
            "device_count": len(devices),
            "open_findings": len(findings),
            "open_critical": sum(1 for f in findings if f.severity == "critical"),
            "open_high": sum(1 for f in findings if f.severity == "high"),
        },
        "devices": per_device,
        "findings": [
            {
                "device_id": f.device_id,
                "category": f.category,
                "severity": f.severity,
                "detail": _redact(f.detail, _masker(), redact),
            }
            for f in findings
        ],
        "requirements": [s.model_dump() for s in _build_sections(store, devices, findings_by_cat, redact)],
    }


def generate_report(
    store: FleetSecurityStore,
    now: int | None = None,
    redact: bool = True,
) -> str:
    """Markdown CRA report (vzorec: core/report.py). Determinističen prek now."""
    now = int(now) if now is not None else _now()
    data = generate_report_json(store, now=now, redact=redact)
    masker = _masker()

    lines: list[str] = []
    lines.append("# Robot Fleet Security — CRA Compliance Report")
    lines.append(f"_Generated {data['generated_at']}_")
    lines.append("")

    summary = data["fleet_summary"]
    lines.append("## Fleet summary")
    lines.append(f"- Devices: **{summary['device_count']}**")
    lines.append(f"- Open findings: {summary['open_findings']} "
                 f"(critical {summary['open_critical']}, high {summary['open_high']})")
    lines.append("")

    lines.append("## Devices")
    if data["devices"]:
        lines.append("| device_id | role | hostname | os | score | grade |")
        lines.append("|---|---|---|---|---|---|")
        for d in data["devices"]:
            lines.append(
                f"| {d['device_id']} | {d['role']} | {_redact(d['hostname'], masker, redact)} | "
                f"{d['os']} | {d.get('score', '-')} | {d.get('grade', '-')} |"
            )
    else:
        lines.append("_No devices registered._")
    lines.append("")

    lines.append("## Open findings")
    if data["findings"]:
        lines.append("| severity | category | device | detail |")
        lines.append("|---|---|---|---|")
        for f in sorted(data["findings"], key=lambda x: (x["severity"], x["category"])):
            lines.append(f"| {f['severity']} | {f['category']} | {f['device_id']} | {f['detail']} |")
    else:
        lines.append("_No open findings._")
    lines.append("")

    lines.append("## CRA requirements")
    for req in data["requirements"]:
        lines.append(f"### {req['requirement_id']} — {req['title']}")
        lines.append(f"_{req['annex_ref']}_")
        lines.append(f"Status: **{req['status']}**")
        lines.append("Evidence:")
        for e in req["evidence"]:
            lines.append(f"- {_redact(e, masker, redact)}")
        if req["related_findings"]:
            lines.append("Related findings:")
            for rf in req["related_findings"]:
                lines.append(f"  - {_redact(rf, masker, redact)}")
        lines.append("")

    lines.append("## Remediations")
    rems = store.list_remediations()
    if rems:
        lines.append("| device | kind | status | branch | pr_url |")
        lines.append("|---|---|---|---|---|")
        for r in rems[-10:]:
            lines.append(f"| {r['device_id']} | {r['kind']} | {r['status']} | {r['branch'] or '-'} | {r['pr_url'] or '-'} |")
    else:
        lines.append("_No remediations yet._")
    lines.append("")

    lines.append("---")
    lines.append("_Phase 1 passive core: inventory + posture + CRA mapping. "
                 "Firmware fixes go through OEM; PRs are human-in-the-loop._")
    return "\n".join(lines)


_MASKER: Any = None


def _masker() -> Any:
    """Lazy PIIMasker (import pii_masking_sanitizer samo kadar rabimo)."""
    global _MASKER
    if _MASKER is None:
        from actions.pii_masking_sanitizer.pii import PIIMasker

        _MASKER = PIIMasker()
    return _MASKER
