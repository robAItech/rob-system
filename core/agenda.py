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
    """Atomičen zapis: piši v temp + `os.replace`, da dva procesa nikoli ne
    pustita agenda.json pokvarjenega. Mutatorji so dodatno pod `_locked`
    (cross-process lock), da se ne izgubi posodobitev (read-modify-write)."""
    AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    tmp = AGENDA_FILE.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, AGENDA_FILE)


# ── Cross-process lock (paralelni daemon: N subprocesov kliče mark/add) ── #
AGENDA_LOCK = AGENDA_FILE.with_suffix(".lock")
_LOCK_TIMEOUT = 10.0
_LOCK_STALE_AFTER = 30.0


def _lock_pid_alive(pid: int) -> bool:
    """Ali PID še obstaja (stale lock cleanup). Windows: OpenProcess probe."""
    if os.name == "nt":
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


def _lock_stale() -> bool:
    try:
        if time.time() - AGENDA_LOCK.stat().st_mtime > _LOCK_STALE_AFTER:
            return True
        pid = int(AGENDA_LOCK.read_text(encoding="utf-8").strip())
        return not _lock_pid_alive(pid)
    except Exception:
        return False


def _locked(fn):
    """Izvede `fn` pod cross-process lockom — agenda.json read-modify-write je
    atomičen MED PROCESI. Nujno za paralelni daemon: N subprocesov kliče
    `mark`/`add`/`rearm_repeat` hkrati; brez locka bi se posodobitve izgubile."""
    AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_TIMEOUT
    while True:
        try:
            fd = os.open(AGENDA_LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            os.close(fd)
            try:
                return fn()
            finally:
                try:
                    AGENDA_LOCK.unlink()
                except OSError:
                    pass
        except FileExistsError:
            if _lock_stale():
                try:
                    AGENDA_LOCK.unlink()
                except OSError:
                    pass
                continue
            if time.monotonic() >= deadline:
                return fn()   # zadnja možnost: best-effort, brez deadlocka
            time.sleep(0.02)


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
    def _do() -> dict:
        items = _load()
        item = {
            "id": uuid.uuid4().hex[:12],
            "goal": goal,
            "kind": kind,      # python | markdown | html | autonomous
            "target": target or _slug(goal),
            "status": "pending",
            "repeat": repeat,  # None ali cron-expression string
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        if source:
            item["source"] = source
        item.update(extra)     # extra zmaga ob teoretičnem kolapsu ključev
        items.append(item)
        _save(items)
        return item
    return _locked(_do)


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
    def _do() -> None:
        items = _load()
        for it in items:
            if it.get("id") == item_id:
                it["status"] = status
                it["updated_at"] = int(time.time())
        _save(items)
    _locked(_do)


def all_() -> list:
    return _load()


def claim_pending(exclude_targets: set | None = None, limit: int = 1) -> list:
    """Vrne do `limit` pending itemov z DISTINCT targeti, FIFO po vrstnem redu.

    `exclude_targets`: targeti, ki so že aktivni — daemon ne zažene dveh build-ov
    istega targeta hkrati. Ne spreminja statusa (running mark-ajo subprocesi).
    """
    exclude = set(exclude_targets or ())
    seen = set(exclude)
    claimed = []
    for it in pending():
        target = it.get("target") or it["id"]   # itemi brez targeta → unikatni po id
        if target in seen:
            continue
        seen.add(target)
        claimed.append(it)
        if len(claimed) >= limit:
            break
    return claimed


def rearm_repeat() -> int:
    """F3 — ponavljajoča naročila (polje `repeat`) po obdelavi znova postavi v
    pending, da ob naslednjem --process-agenda zopet izvedejo (enostaven
    schedule: ponavljaj se ob vsakem procesiranju). Vrne število ponovno
    aktiviranih."""
    def _do() -> int:
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
    return _locked(_do)


def _slug(goal: str) -> str:
    from re import sub as _sub
    return _sub(r"[^a-zA-Z0-9_-]", "_", goal.strip().split()[0].lower()) if goal.strip() else "naloga"
