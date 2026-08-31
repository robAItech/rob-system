"""fleet_security — Threat Intel Feed (Phase 3).

Kuriran CVE-style feed (seed JSON, module-relative) → version→vuln mapiranje
za OS / firmware komponente / modele na napravah. Najdbe → isti fs_findings
tok (posture + CRA + eskalacija).

``compare_versions`` je determinističen (numerični dot-segmenti); semver
pre-release ordering NI implementiran (dokumentirano). Missing/poškodovan feed
→ [] (brez napak). Detail najdb je stabilen (brez timestampa) → dedup/resolve.
"""

from __future__ import annotations

import json
import sys
import time
from itertools import zip_longest
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402
from core.config import settings  # noqa: E402
from actions.fleet_security.schemas import PostureFinding, VulnerabilityAdvisory  # noqa: E402
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

THREATINTEL_CATEGORIES = frozenset({"known_vulnerability"})

#: Privzeti seed feed (module-relative; sup_kanu Path(__file__) pattern).
DEFAULT_FEED_PATH = Path(__file__).resolve().parent / "data" / "threat_feed.json"


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Feed
# ------------------------------------------------------------------ #
def load_feed(path: str | Path | None = None) -> list[VulnerabilityAdvisory]:
    """Naloži threat feed. Tolerantno: missing/poškodovan → []; malformed → skip."""
    if path is not None:
        feed_path = Path(path)
    elif settings.fs_threat_feed_path:
        feed_path = Path(settings.fs_threat_feed_path)
    else:
        feed_path = DEFAULT_FEED_PATH
    if not feed_path.is_file():
        return []
    try:
        data = json.loads(feed_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("advisories", []) if isinstance(data, dict) else []
    out: list[VulnerabilityAdvisory] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            out.append(VulnerabilityAdvisory(**entry))
        except Exception:
            continue
    return out


# ------------------------------------------------------------------ #
#  Version comparison (determinističen)
# ------------------------------------------------------------------ #
def _segment(part: str) -> tuple[int, Any]:
    part = part.strip()
    if part.isdigit():
        return (0, int(part))
    return (1, part.lower())


def compare_versions(a: str, b: str) -> int:
    """Numerični dot-segmenti: 1.2.3 < 1.2.4, 1.10 > 1.9, v1.2 == 1.2.

    Non-numeric segmenti se primerjajo case-insensitive in sortirajo ZA
    numeričnimi (semver pre-release ordering namerno ni implementiran).
    """
    a_parts = (a or "").strip().lstrip("vV").split(".")
    b_parts = (b or "").strip().lstrip("vV").split(".")
    for sa, sb in zip_longest(a_parts, b_parts, fillvalue="0"):
        ka, kb = _segment(sa), _segment(sb)
        if ka < kb:
            return -1
        if ka > kb:
            return 1
    return 0


def _is_affected(version: str, adv: VulnerabilityAdvisory) -> bool:
    if adv.fixed_in and compare_versions(version, adv.fixed_in) >= 0:
        return False
    if adv.affected_versions:
        return any(compare_versions(version, v) == 0 for v in adv.affected_versions)
    if adv.fixed_in:
        return compare_versions(version, adv.fixed_in) < 0
    return False


def _severity_from_cvss(score: float) -> str:
    if score >= 9.0:
        return "critical"
    if score >= 7.0:
        return "high"
    if score >= 4.0:
        return "medium"
    return "low"


# ------------------------------------------------------------------ #
#  Check / pass
# ------------------------------------------------------------------ #
def check_threat_feed(
    store: FleetSecurityStore,
    feed: list[VulnerabilityAdvisory] | None = None,
    now: int | None = None,
) -> list[PostureFinding]:
    """Mapiraj naprave na feed → known_vulnerability najdbe (detail stabilen)."""
    now = int(now) if now is not None else _now()
    feed = feed if feed is not None else load_feed()
    findings: list[PostureFinding] = []

    for device in store.list_devices():
        candidates: list[tuple[str, str]] = [
            (device.os.name, device.os.version)
        ]
        candidates += [(f.component, f.version) for f in device.firmware]
        if device.model is not None:
            candidates.append((device.model.name, device.model.version))

        for component, version in candidates:
            if not version:
                continue
            for adv in feed:
                if adv.component.lower() != component.lower():
                    continue
                if not _is_affected(version, adv):
                    continue
                findings.append(
                    PostureFinding(
                        device_id=device.device_id,
                        category="known_vulnerability",
                        severity=_severity_from_cvss(adv.cvss_score),
                        detail=(
                            f"{adv.cve_id} {component} {version} affected "
                            f"(fixed in {adv.fixed_in})"
                        ),
                        detected_at=now,
                    )
                )
    return findings


def run_threatintel_pass(
    store: FleetSecurityStore,
    feed: list[VulnerabilityAdvisory] | None = None,
    now: int | None = None,
) -> dict:
    """En threat-intel pass: check → upsert (scope) → audit."""
    now = int(now) if now is not None else _now()
    findings = check_threat_feed(store, feed, now=now)

    assessed: set[str] = {d.device_id for d in store.list_devices()}
    for f in store.list_open_findings():
        if f.category in THREATINTEL_CATEGORIES:
            assessed.add(f.device_id)

    inserted = store.upsert_findings(
        findings, now=now, assessed=sorted(assessed),
        resolve_categories=THREATINTEL_CATEGORIES,
    )
    try:
        audit.record(
            event="fleet-security-threatintel",
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


def threatintel_summary(
    store: FleetSecurityStore, feed: list[VulnerabilityAdvisory] | None = None
) -> dict:
    """Povzetek: feed velikost + odprte known_vulnerability najdbe."""
    feed = feed if feed is not None else load_feed()
    open_findings = [
        f for f in store.list_open_findings()
        if f.category in THREATINTEL_CATEGORIES
    ]
    return {
        "advisories": len(feed),
        "open_vulnerabilities": len(open_findings),
        "by_severity": {
            sev: sum(1 for f in open_findings if f.severity == sev)
            for sev in ("critical", "high", "medium", "low")
        },
    }
