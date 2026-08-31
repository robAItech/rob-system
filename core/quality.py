"""core/quality.py — kvalitetni prag + eskalacija (avtonomija z omejeno avtoriteto).

Merljivo in deterministično (brez LLM):
- uspešnost targeta = green/runs iz tabele `run_reviews` (pošten vir, ki ga
  uporablja tudi MetaEvaluator.metrics(); `task_history` je namerno preskočen),
- zaporedni neuspehi iz `audit.jsonl` (eventa `daemon-task` + `fleet-result`,
  status `failed`, po targetu iz polja `project`).

Ko target doseže `quality_min_runs` tekov in ima uspešnost pod
`quality_min_success_rate`, se označi kot DISABLED (goal-autonomy ga neha
predlagati — "ugasni agenta") in se zapiše ESKALACIJA uporabniku
(`.rob_ai/escalations.json` + audit event `escalation` → rdeč dashboard feed).

Registra:
  .rob_ai/quality_registry.json  — {project: {disabled_at, reason, runs, success_rate}}
  .rob_ai/escalations.json       — [{ts, project, reason, detail, status, ...}]

Uporaba:
  python core/quality.py --gate            # zaženi kvalitetni prag
  python core/quality.py --list            # disabled targeti + odprte eskalacije
  python core/quality.py --resolve <proj>  # označi eskalacijo kot rešeno
  python core/quality.py --reenable <proj> # odstrani target iz disabled registra
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402

DEFAULT_DB = PROJECT_ROOT / ".rob_ai" / "memory.db"
QUALITY_REGISTRY = PROJECT_ROOT / ".rob_ai" / "quality_registry.json"
ESCALATIONS_FILE = PROJECT_ROOT / ".rob_ai" / "escalations.json"

# Eventa, ki predstavljata izvedbo naloge (lokalno / fleet worker).
TASK_EVENTS = ("daemon-task", "fleet-result")


# ------------------------------------------------------------------ #
#  Pomožne (atomatično branje/pisanje JSON registrov)
# ------------------------------------------------------------------ #
def _load_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


# ------------------------------------------------------------------ #
#  Meritve (deterministično)
# ------------------------------------------------------------------ #
def project_quality(db_path: Optional[Path | str] = None) -> Dict[str, Dict[str, Any]]:
    """Uspešnost po projektu iz `run_reviews` (outcome green/failed).

    Vrne {project: {runs, green, failed, success_rate}} za projekte z vsaj
    enim tekom. Istoveten vir kot MetaEvaluator.metrics() (pošten; task_history
    se ne uporablja — onesnažen s test_proj vrsticami).
    """
    db = Path(db_path) if db_path else DEFAULT_DB
    try:
        conn = sqlite3.connect(db, timeout=5)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT project, COUNT(*) AS t, "
                "SUM(CASE WHEN outcome='green' THEN 1 ELSE 0 END) AS g "
                "FROM run_reviews GROUP BY project"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        total, green = int(r["t"]), int(r["g"] or 0)
        failed = total - green
        out[r["project"]] = {
            "runs": total, "green": green, "failed": failed,
            "success_rate": round(green / total, 4),
        }
    return out


def consecutive_fails(project: str) -> int:
    """Število ZAPOREDNIH neuspehov na koncu zgodovine tega targeta.

    Audit je append-only → kronološko. Šteje od zadaj (najnovejši) nazaj,
    dokler ne naleti na neuspeh.
    """
    evs = [e for e in audit.query(project=project) if e.get("event") in TASK_EVENTS]
    n = 0
    for e in reversed(evs):
        if e.get("status") == "failed":
            n += 1
        else:
            break
    return n


# ------------------------------------------------------------------ #
#  Disabled register (quality_registry.json)
# ------------------------------------------------------------------ #
def is_disabled(project: str) -> bool:
    return project in _load_json(QUALITY_REGISTRY, {})


def list_disabled() -> List[Dict[str, Any]]:
    reg = _load_json(QUALITY_REGISTRY, {})
    return [{"project": p, **m} for p, m in sorted(reg.items())]


def _flag_disabled(project: str, m: Dict[str, Any], min_success_rate: float) -> None:
    reg = _load_json(QUALITY_REGISTRY, {})
    reg[project] = {
        "disabled_at": int(time.time()),
        "reason": f"uspešnost {m['success_rate']:.0%} < {min_success_rate:.0%}",
        "runs": m["runs"],
        "success_rate": m["success_rate"],
    }
    _save_json(QUALITY_REGISTRY, reg)


def reenable(project: str) -> bool:
    """Uporabnik ponovno omogoči target (odstrani iz disabled registra)."""
    reg = _load_json(QUALITY_REGISTRY, {})
    if project in reg:
        reg.pop(project)
        _save_json(QUALITY_REGISTRY, reg)
        return True
    return False


# ------------------------------------------------------------------ #
#  Eskalacije (escalations.json + audit event → rdeč feed)
# ------------------------------------------------------------------ #
def record_escalation(project: str, reason: str, detail: str = "") -> bool:
    """Zapiše odprto eskalacijo (če za ta projekt še ni odprte)."""
    esc = _load_json(ESCALATIONS_FILE, [])
    if any(e.get("project") == project and e.get("status") == "open" for e in esc):
        return False
    esc.append({
        "ts": int(time.time()), "project": project, "reason": reason,
        "detail": str(detail)[:400], "status": "open",
    })
    _save_json(ESCALATIONS_FILE, esc)
    try:
        audit.record(event="escalation", project=project, status="critical",
                     detail=f"{reason}: {detail}"[:500])
    except Exception:
        pass
    return True


def open_escalations() -> List[Dict[str, Any]]:
    return [e for e in _load_json(ESCALATIONS_FILE, []) if e.get("status") == "open"]


def resolve_escalation(project: str, resolved_by: str = "user") -> bool:
    esc = _load_json(ESCALATIONS_FILE, [])
    changed = False
    for e in esc:
        if e.get("project") == project and e.get("status") == "open":
            e["status"] = "resolved"
            e["resolved_at"] = int(time.time())
            e["resolved_by"] = resolved_by
            changed = True
    if changed:
        _save_json(ESCALATIONS_FILE, esc)
    return changed


# ------------------------------------------------------------------ #
#  Kvalitetni prag (gate)
# ------------------------------------------------------------------ #
def run_gate(min_runs: int = 3, min_success_rate: float = 0.5,
             db_path: Optional[Path | str] = None) -> Dict[str, Any]:
    """Preveri vse targete; pod pragom → disabled + eskalacija. Deterministično.

    Vrne povzetek: {checked, flagged, escalated}. Idempotentno: za target, ki je
    že disabled / ima odprto eskalacijo, ne ponovi.
    """
    q = project_quality(db_path)
    checked = flagged = escalated = 0
    for project, m in q.items():
        if m["runs"] < min_runs:
            continue
        checked += 1
        if m["success_rate"] >= min_success_rate:
            continue
        if not is_disabled(project):
            _flag_disabled(project, m, min_success_rate)
            flagged += 1
        if record_escalation(
                project, "nizka uspešnost",
                f"{m['green']}/{m['runs']} zelenih ({m['success_rate']:.0%})"):
            escalated += 1
    return {"checked": checked, "flagged": flagged, "escalated": escalated}


# ------------------------------------------------------------------ #
#  CLI
# ------------------------------------------------------------------ #
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="rob quality",
                                description="Kvalitetni prag + eskalacije.")
    p.add_argument("--gate", action="store_true", help="poženi kvalitetni prag")
    p.add_argument("--list", action="store_true", help="disabled targeti + odprte eskalacije")
    p.add_argument("--resolve", metavar="PROJECT", help="označi eskalacijo kot rešeno")
    p.add_argument("--reenable", metavar="PROJECT", help="odstrani target iz disabled")
    args = p.parse_args(argv)

    if args.gate:
        print(json.dumps(run_gate(), ensure_ascii=False))
        return 0
    if args.resolve:
        ok = resolve_escalation(args.resolve)
        print(f"eskalacija {args.resolve}: {'rešena' if ok else 'ni odprte'}")
        return 0
    if args.reenable:
        ok = reenable(args.reenable)
        print(f"target {args.reenable}: {'omogočen' if ok else 'ni bil disabled'}")
        return 0
    if args.list:
        print("DISABLED TARGETI:")
        for d in list_disabled():
            print(f"  {d['project']}  (uspešnost {d['success_rate']:.0%}, {d['reason']})")
        print("ODPRTE ESKALACIJE:")
        for e in open_escalations():
            print(f"  [{e['ts']}] {e['project']}: {e['reason']} — {e['detail']}")
        return 0
    p.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
