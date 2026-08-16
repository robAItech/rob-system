"""core/audit.py — Faza 5: revizijski dnevnik (v živi RSI poti).

Vsaka odločitev v podjetju se zapiše v revizijski log (JSONL, append-only,
ne spreminja preteklih vrstic). To omogoča sledljivost po vseh fazah:
  - kdaj, kaj (directive-hash), kdo (agent), kakšen rezultat,
  - koliko LLM klicev (cost), stanje.

Log: `.rob_ai/audit.jsonl` — lokalno, izven gita.
"""

import json
import time
from pathlib import Path

AUDIT_FILE = Path(__file__).resolve().parent.parent / ".rob_ai" / "audit.jsonl"


def record(event: str, project: str, status: str, detail: str = "",
          llm_calls: int = 0, agent: str = "GSTACK-Architect") -> None:
    """Appenda en revizijski vnos. Nikoli ne prebere/ne spreminja preteklih."""
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": int(time.time()),
        "event": event,           # e.g. "build", "agenda-item", "heal"
        "project": project,
        "agent": agent,
        "status": status,         # "ok" | "failed"
        "llm_calls": llm_calls,
        "detail": detail[:500],
    }
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def tail(n: int = 20) -> list:
    """Zadnjih n revizijskih vnosov (za prikaz)."""
    if not AUDIT_FILE.exists():
        return []
    lines = AUDIT_FILE.read_text(encoding="utf-8").strip().split("\n")
    out = []
    for ln in lines[-n:]:
        try:
            out.append(json.loads(ln))
        except Exception:
            continue
    return out
