"""fleet_security — konsolidiran dashboard snapshot (dashboard integracija).

``snapshot()`` vrne en JSON objekt z vsem, kar TS dashboard panel rabi:
posture, najdbe, CRA, monitor, red team, supply chain, threat intel.
Read-only — NE sproža pass-ov (pass-i tečejo prek daemon tick-ov / ročno).

Kliče ga Bun dashboard prek ``Bun.spawn(['python', '-m',
'actions.fleet_security.dashboard'])`` — zato ima ta modul CLI, ki printa
en JSON objekt (``ensure_ascii=False``).
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings  # noqa: E402
from actions.fleet_security import (  # noqa: E402
    compliance,
    monitor,
    posture,
    redteam,
    supplychain,
    threatintel,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

#: Vrstni red severity za sortiranje najdb (najhujša prva).
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_MAX_FINDINGS = 20


def _now_iso() -> str:
    return datetime.fromtimestamp(int(time.time()), tz=timezone.utc).isoformat()


def snapshot(db_path: str | None = None) -> dict[str, Any]:
    """Konsolidiran varnostni snapshot (read-only) za dashboard."""
    store = FleetSecurityStore(db_path or settings.fs_db_path)

    posture_data = posture.posture_summary(store)

    # Najdbe: sort po severity, cap na _MAX_FINDINGS.
    findings = store.list_open_findings()
    findings.sort(key=lambda f: (_SEVERITY_RANK.get(f.severity, 9), f.id or 0))
    findings_out = [
        {
            "severity": f.severity,
            "category": f.category,
            "device_id": f.device_id,
            "detail": f.detail,
        }
        for f in findings[:_MAX_FINDINGS]
    ]

    # CRA statusi (iz strojno berljivega reporta).
    cra_data = compliance.generate_report_json(store)
    cra_out = [
        {
            "requirement_id": r["requirement_id"],
            "title": r["title"],
            "status": r["status"],
        }
        for r in cra_data["requirements"]
    ]

    monitor_data = monitor.monitor_summary(store)
    redteam_data = redteam.redteam_summary(store)
    supplychain_data = supplychain.supplychain_summary(store)
    threatintel_data = threatintel.threatintel_summary(store)

    return {
        "generated_at": _now_iso(),
        "fleet": {
            "device_count": posture_data.get("device_count", 0),
            "mean_score": posture_data.get("mean_score"),
            "grades": posture_data.get("grades", {}),
        },
        "devices": posture_data.get("devices", []),
        "findings": findings_out,
        "findings_by_severity": posture_data.get("findings_by_severity", {}),
        "cra": cra_out,
        "monitor": {
            "open_anomaly_findings": monitor_data.get("open_anomaly_findings", 0),
            "by_category": monitor_data.get("by_category", {}),
        },
        "redteam": {
            "runs": redteam_data.get("runs", 0),
            "vulnerable": redteam_data.get("vulnerable", 0),
            "open_injection_findings": redteam_data.get("open_injection_findings", 0),
        },
        "supplychain": {
            "history_records": supplychain_data.get("history_records", 0),
            "open_findings": supplychain_data.get("open_findings", 0),
        },
        "threatintel": {
            "advisories": threatintel_data.get("advisories", 0),
            "open_vulnerabilities": threatintel_data.get("open_vulnerabilities", 0),
        },
    }


def main(argv: list[str] | None = None) -> int:
    """CLI: printaj en JSON snapshot (kliče ga Bun dashboard)."""
    print(json.dumps(snapshot(), ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
