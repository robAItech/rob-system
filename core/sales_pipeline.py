"""core/sales_pipeline.py — prodajni cevovod (lead → … → won/lost).

Ista glavna knjiga kot F6 (`core/business.py`, `.rob_ai/business_ledger.json`):
faze razširimo na cel cevovod. Knjiga je ENA — dashboard (/api/business) in
sales delovnik bereta isto.

Faze: lead → contacted → proposal → sent → won | lost.
Vsak vnos nosi: company (customer), offer_note (kaj ponujamo), source,
next_action (naslednji korak — tisto, kar sistem/CoS preganja).

Robustno: nikoli ne dvigne na manjkajoči datoteki; CLI za ročno uporabo.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from core.business import LEDGER_FILE, _load, _save  # deljena glavna knjiga

STAGES = ["lead", "contacted", "proposal", "sent", "won", "lost"]
# Faze, ki še "živijo" (niso končane).
OPEN_STAGES = STAGES[:-2]


def _entry(entry_id: str) -> Optional[dict]:
    return next((e for e in _load() if e.get("id") == entry_id), None)


def new_lead(company: str, offer_note: str = "", source: str = "manual",
             next_action: str = "") -> Optional[dict]:
    """Nov lead v knjigo na fazi 'lead'. Vrne vnos ali None ob napaki."""
    company = (company or "").strip()
    if not company:
        return None
    entry = {
        "id": uuid.uuid4().hex[:12],
        "company": company,
        "customer": company,          # nazaj-kompatibilno s F6/business pogledi
        "idea": offer_note,           # kaj ponujamo (offer_note)
        "offer_note": offer_note,
        "source": source,
        "next_action": next_action,
        "stage": "lead",
        "status": "lead",             # business.py status polje = ista faza
        "revenue": 0,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    items = _load(); items.append(entry); _save(items)
    return entry


def advance(entry_id: str, stage: str, note: str = "") -> bool:
    """Premakne vnos na fazo (veljavna ali zaključna). Vrne True ob uspehu."""
    stage = (stage or "").strip().lower()
    if stage not in STAGES:
        return False
    items = _load()
    for it in items:
        if it.get("id") == entry_id:
            it["stage"] = stage
            it["status"] = stage
            it["updated_at"] = int(time.time())
            if note:
                notes = it.setdefault("notes", [])
                notes.append({"ts": int(time.time()), "text": note})
            if stage in ("won", "lost"):
                it["next_action"] = ""       # končano — ni naslednjega koraka
            _save(items)
            return True
    return False


def set_next(entry_id: str, text: str) -> bool:
    """Nastavi naslednji korak (tisto, kar sistem preganja naprej)."""
    text = (text or "").strip()
    items = _load()
    for it in items:
        if it.get("id") == entry_id:
            it["next_action"] = text
            it["updated_at"] = int(time.time())
            _save(items)
            return True
    return False


def open_leads() -> List[dict]:
    """Odprti vnosi (ne won/lost), najstarejši najprej."""
    out = [e for e in _load() if e.get("stage") in OPEN_STAGES or not e.get("stage")]
    out.sort(key=lambda e: e.get("created_at", 0))
    return out


def report() -> Dict[str, object]:
    """Povzetek cevovoda: števci po fazah + seznam odprtih."""
    entries = _load()
    counts = {s: 0 for s in STAGES}
    for e in entries:
        st = str(e.get("stage") or e.get("status") or "lead")
        counts[st] = counts.get(st, 0) + 1
    revenue_won = sum(float(e.get("revenue") or 0) for e in entries
                      if e.get("stage") == "won")
    return {
        "total": len(entries),
        "counts": counts,
        "open": len(open_leads()),
        "won": counts.get("won", 0),
        "revenue_won": revenue_won,
        "leads": open_leads()[:20],
    }


# --------------------------------------------------------------------------- #
#  CLI  (python -m core.sales_pipeline …)
# --------------------------------------------------------------------------- #
def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m core.sales_pipeline",
                                 description="Prodajni cevovod (lead → won/lost).")
    ap.add_argument("--add", nargs="+", metavar="BESEDILO", default=None,
                    help="Nov lead: --add \"Podjetje\" \"kaj ponujamo\" (source/next opcijsko).")
    ap.add_argument("--source", default="manual")
    ap.add_argument("--next", default="", help="Naslednji korak za nov lead.")
    ap.add_argument("--advance", nargs=2, metavar=("ID", "FAZA"),
                    help="Premakni lead na fazo (npr. proposal).")
    ap.add_argument("--report", action="store_true", help="Prikaži cevovod.")
    args = ap.parse_args(argv)

    if args.add:
        company = args.add[0]
        offer = " ".join(args.add[1:])
        e = new_lead(company, offer_note=offer, source=args.source,
                     next_action=args.next)
        print(f"lead dodan: {e['id']} · {e['company']} ({e['stage']})" if e else "(napaka)")
    if args.advance:
        ok = advance(args.advance[0], args.advance[1])
        print(f"advance {args.advance[0]} → {args.advance[1]}: {'ok' if ok else 'ni uspelo'}")
    if args.report:
        r = report()
        print("Prodajni cevovod:")
        for s in STAGES:
            n = r["counts"].get(s, 0)
            print(f"  {s:<10} {n}")
        print(f"  {'odprto':<10} {r['open']}  |  won: {r['won']}  |  revenue: {r['revenue_won']}")
        for e in r["leads"]:
            na = e.get("next_action") or ""
            print(f"  - {e.get('company')} ({e.get('stage')})"
                  + (f" · naprej: {na[:70]}" if na else ""))
    if not (args.add or args.advance or args.report):
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
