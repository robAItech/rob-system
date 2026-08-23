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
import threading
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


_REPLACE_RETRIES = 20   # Windows: os.replace je lahko začasno blokiran (WinError 5/32)


def _save(items: list) -> None:
    """Atomičen zapis: piši v temp + `os.replace`, da dva procesa nikoli ne
    pustita agenda.json pokvarjenega. Mutatorji so dodatno pod `_locked`
    (cross-process lock), da se ne izgubi posodobitev (read-modify-write).

    Windows: temp ime je UNIKATNO po piscu (pid + naključno) — deljen `*.tmp`
    bi pri konkurenčnih `_save` (deadline fallback v `_locked`, brez locka)
    trčil: dve niti pišeta isti tmp → WinError 32 (file in use). `os.replace`
    se ob začasnem WinError 5/32 (Defender/handle) ponovi z backoff — če bi
    padel takoj, bi se nit umrla sredi `_do`, lock.unlink() bi na Windows
    obvisel (zaporedni create/delete locka) → osiroten lock → 10 s čakanja."""
    AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(items, ensure_ascii=False, indent=2)
    tmp = AGENDA_FILE.with_name(f"{AGENDA_FILE.name}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(tmp, AGENDA_FILE)
            return
        except OSError:
            if attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(0.02 * (attempt + 1))


# ── Cross-process lock (paralelni daemon: N subprocesov kliče mark/add) ── #
_LOCK_TIMEOUT = 10.0
_LOCK_STALE_AFTER = 30.0


def _agenda_lock() -> Path:
    """Pot do lock datoteke — IZPELJANA iz trenutnega AGENDA_FILE (testi ga
    patch-ajo; konstanta ob importu bi ostala na stari poti → FileNotFoundError)."""
    return AGENDA_FILE.with_suffix(".lock")


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
        lock = _agenda_lock()
        if time.time() - lock.stat().st_mtime > _LOCK_STALE_AFTER:
            return True
        pid = int(lock.read_text(encoding="utf-8").strip())
        return not _lock_pid_alive(pid)
    except Exception:
        return False


# Thread-varnost (Windows): niti ZNOTRAJ procesa serializiramo s threading.Lock
# PRED file-lockom. Rapidni create/delete lock datoteke s 5 nitmi na Windows
# trči (os.replace WinError 5 / osiroten lock → 10 s čakanja → best-effort
# brez locka → izgubljen update). threading.Lock reši to brez file-operacij;
# file lock ostane za cross-process (paralelni daemon).
_thread_guard = threading.Lock()


def _locked(fn):
    """Izvede `fn` pod lockom — agenda.json read-modify-write je atomičen.

    Dvonivojski lock: (1) `threading.Lock` serializira niti v tem procesu
    (brez dragih file-operacij), (2) file-lock `O_CREAT|O_EXCL` ščiti med
    procesi (paralelni daemon: N subprocesov kliče mark/add/rearm_repeat).
    """
    with _thread_guard:
        AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
        lock = _agenda_lock()
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while True:
            try:
                fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode("utf-8"))
                os.close(fd)
                try:
                    return fn()
                finally:
                    try:
                        lock.unlink()
                    except OSError:
                        pass
            except FileExistsError:
                if _lock_stale():
                    try:
                        lock.unlink()
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


def purge_history(keep: tuple = ("pending", "running")) -> int:
    """Odstrani zaključene naloge (done/failed) iz agende; obdrži aktivne.

    Dashboard čiščenje: zaključene naloge niso več potrebne v vrsti (moduli
    ostanejo v actions/). Vrne število odstranjenih. Pod lockom (varno ob
    daemonovih add/mark)."""
    def _do() -> int:
        items = _load()
        kept = [i for i in items if i.get("status") in keep]
        removed = len(items) - len(kept)
        if removed:
            _save(kept)
        return removed
    return _locked(_do)


def delete_item(item_id: str) -> bool:
    """Odstrani ENO nalogo iz agende po id. Vrne True, če je bila odstranjena."""
    def _do() -> bool:
        items = _load()
        kept = [i for i in items if i.get("id") != item_id]
        if len(kept) == len(items):
            return False
        _save(kept)
        return True
    return _locked(_do)


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
