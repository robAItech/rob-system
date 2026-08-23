"""core/agenda.py — Faza 3: med-run agenda (čakalna vrsta naročil).

Podjetje ne dela le na zahtevo; ima čakalno vrsto naročil (agenda), ki jih
RSI zanka obdela po vrsti. Naročila so shranjena v `.rob_ai/agenda.json`
(lokalno, izven gita). To omogoča:
  - nalaganje več nalog (iz dashboarda ali CLI),
  - obdelavo po vrsti (`run_swarm.py --process-agenda`),
  - sledenje statusu (pending / running / done / failed),
  - ponavljajoče naloge (schedule) — `repeat` polje.
"""

import json
import os
import time
import uuid
from pathlib import Path

AGENDA_FILE = Path(__file__).resolve().parent.parent / ".rob_ai" / "agenda.json"


def _load() -> list:
    AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not AGENDA_FILE.exists():
        return []
    try:
        return json.loads(AGENDA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: list) -> None:
    """Atomičen zapis: piši v temp + `os.replace`, da dva procesa (server.ts
    Gmail poll, daemon subprocess) nikoli ne pustita agenda.json pokvarjenega.

    Opomba: to prepreči korupcijo datoteke, ne izgubljene posodobitve (klasičen
    read-modify-write race med dvema procesoma ostaja — za P1 sprejemljivo, ker
    klici prihajajo redko in `mark`/`add` imata en kratek vmesni čas).
    """
    AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    tmp = AGENDA_FILE.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, AGENDA_FILE)


def add(goal: str, kind: str = "python", target: str | None = None,
        repeat: str | None = None, source: str | None = None,
        **extra) -> dict:
    """Doda naročilo v čakalno vrsto. Vrne novo naročilo.

    `source` (opcijsko): od koder naloga (dashboard | cli | gmail | voice) — za
    sledenje izvora na dashboardu. Ne vpliva na obdelavo.

    `extra` (opcijsko): poljubna dodatna polja na itemu — npr. fix naloga
    (source="fix_loop") nosi `test=<ime padlega testa>` strukturno, da
    `run_surgical` ve, kateri test ciljno verifikirati.
    """
    items = _load()
    item = {
        "id": uuid.uuid4().hex[:12],
        "goal": goal,
        "kind": kind,          # python | markdown | html | autonomous
        "target": target or _slug(goal),
        "status": "pending",
        "repeat": repeat,      # None ali cron-expression string (npr. "0 8 * * *")
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    if source:
        item["source"] = source
    item.update(extra)         # extra zmaga ob teoretičnem kolapsu ključev
    items.append(item)
    _save(items)
    return item


def pending() -> list:
    """Vsa še ne obdelana naročila (in ponavljajoča)."""
    return [i for i in _load() if i.get("status") == "pending"]


def get(item_id: str) -> dict | None:
    """Vrne naročilo po id (ali None). Uporablja daemon (--item)."""
    for it in _load():
        if it.get("id") == item_id:
            return it
    return None


def mark(item_id: str, status: str) -> None:
    items = _load()
    for it in items:
        if it.get("id") == item_id:
            it["status"] = status
            it["updated_at"] = int(time.time())
    _save(items)


def all_() -> list:
    return _load()


def rearm_repeat() -> int:
    """F3 — ponavljajoča naročila (polje `repeat`) po obdelavi znova postavi v
    pending, da ob naslednjem --process-agenda zopet izvedejo (enostaven
    schedule: ponavljaj se ob vsakem procesiranju). Vrne število ponovno
    aktiviranih."""
    items = _load()
    n = 0
    for it in items:
        if it.get("repeat") and it.get("status") in ("done", "failed"):
            it["status"] = "pending"
            it["updated_at"] = int(time.time())
            n += 1
    if n:
        _save(items)
    return n


def _slug(goal: str) -> str:
    from re import sub as _sub
    return _sub(r"[^a-zA-Z0-9_-]", "_", goal.strip().split()[0].lower()) if goal.strip() else "naloga"
