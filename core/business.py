"""core/business.py — Faza 6: poslovni avtomat + glavna knjiga (ledger podjetja).

Podjetje ne evidentira le tekov, ampak poslovne vnose: ideje, predloge,
stranke in prilive. Ta modul vodi **glavno knjigo podjetja** v lokalnem
`.rob_ai/business_ledger.json` (izven gita) in povezuje Sales-delovnik
(izdelava predloga prek RSI) s knjigo.

Delovnik:
  1. idea → ustvari poslovni predlog (RSI markdown) v actions/<target>/.
  2. menedžer presodi (deterministično: predlog velja, če ima naslov + telo).
  3. vnese v glavno knjigo (status: proposal / sent / won / lost).
  4. log_sale() evidentira revenue (priliv).
"""

import json
import time
import uuid
from pathlib import Path

LEDGER_FILE = Path(__file__).resolve().parent.parent / ".rob_ai" / "business_ledger.json"


def _load() -> list:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not LEDGER_FILE.exists():
        return []
    try:
        return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: list) -> None:
    LEDGER_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def create_proposal(idea: str, customer: str = "", target: str | None = None) -> dict:
    """Zabeleži idejo v knjigo z namenom izdelave predloga (Sales delovnik)."""
    target = target or _slug(idea)
    entry = {
        "id": uuid.uuid4().hex[:12],
        "idea": idea,
        "customer": customer,
        "target": target,
        "status": "proposal",        # proposal → sent → won/lost
        "revenue": 0,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    items = _load(); items.append(entry); _save(items)
    return entry


def list_ledger() -> list:
    return _load()


def update(entry_id: str, status: str | None = None, revenue: float | None = None) -> None:
    items = _load()
    for it in items:
        if it.get("id") == entry_id:
            if status is not None:
                it["status"] = status
            if revenue is not None:
                it["revenue"] = revenue
            it["updated_at"] = int(time.time())
    _save(items)


def log_sale(entry_id: str, amount: float) -> None:
    """Evidentira priliv (won) — SIE podjetja v glavno knjigo."""
    update(entry_id, status="won", revenue=amount)


def total_revenue() -> float:
    return round(sum(i.get("revenue", 0) for i in _load()), 4)


def _slug(idea: str) -> str:
    from re import sub as _sub
    words = idea.strip().split()
    base = _sub(r"[^a-zA-Z0-9_-]", "_", words[0].lower()) if words else "predlog"
    return base
