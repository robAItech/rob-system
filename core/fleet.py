"""core/fleet.py — P9: master–worker fleet (deljena agenda čez več strojev).

Master (`ROB_FLEET_ROLE=master`) požene majhno FastAPI (`rob fleet serve`,
privzeti port :8789), ki eksponira LOKALNO agendo prek /fleet/* — workerji
atomsko claim-ajo naloge, pošljejo rezultate in heartbeat. Master ostane edina
avtoriteta nad agendo; worker nikoli ne piše vanjo neposredno.

Worker (`ROB_FLEET_ROLE=worker`): daemon namesto lokalne `claim_pending` kliče
masterjev /fleet/claim; prejeto nalogo zapiše v LOKALNO senčno agendo
(`fleet_claimed=True`, status running) in jo izvede skozi isto pot kot lokalne
naloge (`run_swarm.py --item`), nato rezultat pošlje nazaj masterju.

Lease / odpornost:
- master ob claim-u postavi `claimed_at`; `agenda.release_expired_claims()` po
  TTL (`ROB_FLEET_CLAIM_TTL_SECONDS`) sprosti naloge workerjev, ki so umrli
  sredi dela.
- worker ob boot-u izbriše nedokončane fleet senčne iteme (master jih
  re-claim-a), tako da ni podvajanja ob reboot-u workerja.

Varnost: vsi /fleet/* endpointi zahtevajo `ROB_FLEET_TOKEN` (Bearer) in padejo
zaprti (fail-closed) brez tokena. NIKOLI ne izpostavljaj javno — Tailscale ali
zasebno omrežje.
"""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

import requests

# Koren projekta na PYTHONPATH (fleet.py se lahko požene kot `python core/fleet.py`).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import agenda, memory_sync
from core.config import settings

FLEET_PORT = 8789
FLEET_WORKERS_FILE = agenda.AGENDA_FILE.parent / "fleet_workers.json"


def host_id() -> str:
    """Identiteta stroja/workerja (za claimed_by + heartbeat)."""
    return socket.gethostname() or "unknown"


# ── Request sheme ─────────────────────────────────────────────────────────
class ClaimRequest(BaseModel):
    worker: str = "unknown"


class ResultRequest(BaseModel):
    item_id: str
    ok: bool
    target: str = ""
    detail: str = ""
    duration_s: float = 0.0
    worker: str = ""


class HeartbeatRequest(BaseModel):
    worker: str
    tasks: list = []


# ── Heartbeat workerjev (master): .rob_ai/fleet_workers.json ──────────────
def _load_workers() -> dict:
    try:
        return json.loads(FLEET_WORKERS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _record_heartbeat(req: HeartbeatRequest) -> None:
    FLEET_WORKERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    workers = _load_workers()
    workers[req.worker] = {"last_seen": int(time.time()), "tasks": req.tasks}
    FLEET_WORKERS_FILE.write_text(json.dumps(workers, indent=2), encoding="utf-8")


# ── Server ────────────────────────────────────────────────────────────────
def _authorized(token: str, authorization: Optional[str]) -> bool:
    """Bearer preverba. Brez konfiguriranega tokena → zavrnemo (fail-closed)."""
    if not token or not authorization:
        return False
    scheme, _, value = authorization.partition(" ")
    return scheme.lower() == "bearer" and value == token


def create_app(token: Optional[str] = None) -> FastAPI:
    """Masterjev fleet strežnik. `token` = ROB_FLEET_TOKEN (privzeto iz config)."""
    token = token or settings.fleet_token
    app = FastAPI(title="Rob System Fleet", version="1.0.0")

    def auth(authorization: Optional[str] = Header(default=None)) -> None:
        if not _authorized(token, authorization):
            raise HTTPException(status_code=401, detail="manjkajoč ali neveljaven fleet token")

    @app.post("/fleet/claim", dependencies=[Depends(auth)])
    def claim(req: ClaimRequest) -> dict:
        """Worker zahteva naslednjo nalogo. Master najprej sprosti pretekle
        (lease), nato atomično rezervira en pending item za tega workerja."""
        released = agenda.release_expired_claims(settings.fleet_claim_ttl_seconds)
        items = agenda.claim_fleet(limit=1, worker=req.worker)
        return {"items": items, "released": released}

    @app.post("/fleet/result", dependencies=[Depends(auth)])
    def result(req: ResultRequest) -> dict:
        """Worker javlja izid naloge (done/failed) — master označi svoj item."""
        status = "done" if req.ok else "failed"
        agenda.record_fleet_result(req.item_id, status, worker=req.worker or None,
                                   detail=req.detail, duration_s=req.duration_s)
        return {"ok": True, "item_id": req.item_id, "status": status}

    @app.post("/fleet/heartbeat", dependencies=[Depends(auth)])
    def heartbeat(req: HeartbeatRequest) -> dict:
        _record_heartbeat(req)
        return {"ok": True}

    @app.get("/fleet/status", dependencies=[Depends(auth)])
    def status() -> dict:
        items = agenda.all_()
        return {
            "agenda": {
                "pending": len(agenda.pending()),
                "running": sum(1 for i in items if i.get("status") == "running"),
                "total": len(items),
            },
            "workers": _load_workers(),
            "memory": memory_sync.count_memory(),
        }

    @app.get("/fleet/memory", dependencies=[Depends(auth)])
    def memory_export() -> dict:
        """Worker potegne masterjev spomin (izvoz učnih tabel)."""
        return memory_sync.export_memory()

    @app.post("/fleet/memory", dependencies=[Depends(auth)])
    def memory_merge(payload: dict) -> dict:
        """Worker pošlje svoj spomin nazaj — master združi (dedup, idempotentno)."""
        return memory_sync.merge_memory(payload)

    return app


# ── Klient (worker → master) ──────────────────────────────────────────────
class FleetClient:
    """HTTP klient za worker→master. Uporablja `requests` (že dependency)."""

    def __init__(self, base_url: str, token: str, timeout: float = 10.0):
        self.base = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def claim(self, worker: Optional[str] = None) -> Optional[dict]:
        """Claim eno nalogo od masterja; None, če vrsta prazna."""
        if not self.base:
            raise RuntimeError("ROB_FLEET_MASTER_URL ni nastavljen")
        r = requests.post(f"{self.base}/fleet/claim",
                          json={"worker": worker or host_id()},
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        items = r.json().get("items") or []
        return items[0] if items else None

    def result(self, item_id: str, ok: bool, target: str = "", detail: str = "",
               duration_s: float = 0.0, worker: Optional[str] = None) -> bool:
        r = requests.post(f"{self.base}/fleet/result",
                          json={"item_id": item_id, "ok": ok, "target": target,
                                "detail": detail, "duration_s": duration_s,
                                "worker": worker or host_id()},
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return True

    def heartbeat(self, worker: Optional[str] = None, tasks: Optional[list] = None) -> bool:
        r = requests.post(f"{self.base}/fleet/heartbeat",
                          json={"worker": worker or host_id(), "tasks": tasks or []},
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return True

    def status(self) -> dict:
        r = requests.get(f"{self.base}/fleet/status",
                         headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def memory_pull(self) -> dict:
        """Potegni masterjev izvoz spomina (učne tabele)."""
        r = requests.get(f"{self.base}/fleet/memory",
                         headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def memory_push(self, payload: dict) -> dict:
        """Pošlji svoj izvoz spomina masterju (master združi z dedupom)."""
        r = requests.post(f"{self.base}/fleet/memory", json=payload,
                          headers=self._headers(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()


# ── Git backup / restore (odpornost — master ni slepa ulica) ──────────────
BACKUP_FILE = PROJECT_ROOT / "fleet" / "backup.json"


def _cmd_backup() -> int:
    """Izvoz spomina + agende v fleet/backup.json, commit+push v git."""
    BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "memory": memory_sync.export_memory(),
        "agenda": agenda.all_(),
        "backed_up_at": int(time.time()),
    }
    BACKUP_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    # Vključi tudi actions/ (zgrajeni moduli — workerjevi build-i pridejo sem
    # prek git-a; tudi masterjevi neposredni `rob build`).
    if subprocess.call(["git", "add", "fleet/backup.json", "actions/"], cwd=PROJECT_ROOT) != 0:
        print("[fleet] git add ni uspel")
        return 1
    # Ni sprememb → backup je že aktualen, nič za commit.
    if subprocess.call(["git", "diff", "--cached", "--quiet"], cwd=PROJECT_ROOT) == 0:
        print("[fleet] backup že aktualen (ni sprememb).")
        return 0
    ts = time.strftime("%Y-%m-%d %H:%M")
    if subprocess.call(["git", "commit", "-m", f"fleet backup {ts} — spomin+agenda"],
                       cwd=PROJECT_ROOT) != 0:
        print("[fleet] git commit ni uspel")
        return 1
    if subprocess.call(["git", "push"], cwd=PROJECT_ROOT) != 0:
        print("[fleet] git push ni uspel (preveri remote/povezavo)")
        return 1
    print(f"[fleet] backup commit + push OK → fleet/backup.json ({ts})")
    return 0


def commit_worker_actions(module: str) -> bool:
    """Worker: po uspešnem build-u commit-a svoj `actions/<module>` v git in
    push-a — tako kodo dobi tudi master (prek naslednjega backup pull-a).
    Ne dotika se `fleet/backup.json` (to je masterjev izvoz). Idempotentno:
    brez sprememb ni commit-a. Push poskusi dvakrat (pre-push hook lahko ob
    prvem naredi pull --rebase in prekine)."""
    if not module:
        return False
    if subprocess.call(["git", "add", f"actions/{module}"], cwd=PROJECT_ROOT) != 0:
        return False
    if subprocess.call(["git", "diff", "--cached", "--quiet"], cwd=PROJECT_ROOT) == 0:
        return False   # ni sprememb → nič za commit
    if subprocess.call(["git", "commit", "-m", f"fleet: worker build {module}"],
                       cwd=PROJECT_ROOT) != 0:
        return False
    if subprocess.call(["git", "push"], cwd=PROJECT_ROOT) != 0:
        # pre-push hook je morda naredil rebase in prekinil → poskusi še enkrat
        subprocess.call(["git", "push"], cwd=PROJECT_ROOT)
    return True


def _cmd_restore() -> int:
    """git pull + združi fleet/backup.json v lokalni spomin in agendo."""
    subprocess.call(["git", "pull", "--rebase"], cwd=PROJECT_ROOT)
    if not BACKUP_FILE.exists():
        print("[fleet] ni fleet/backup.json (še ni bilo backupa na masterju).")
        return 1
    payload = json.loads(BACKUP_FILE.read_text(encoding="utf-8"))
    mem_stats = memory_sync.merge_memory(payload.get("memory") or {})
    agenda_n = agenda.restore_pending(payload.get("agenda") or [])
    print(f"[fleet] restore OK — spomin dodano: {mem_stats}; agenda uvoženih: {agenda_n}")
    return 0


# ── CLI (rob fleet ...) ───────────────────────────────────────────────────
def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rob fleet",
        description="P9 — master–worker fleet: deljena agenda čez več strojev.",
    )
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="master: zaženi fleet strežnik (FastAPI/uvicorn)")
    sub.add_parser("status", help="prikaži stanje flote (od masterja)")
    sub.add_parser("claim", help="(worker, debug) claim eno nalogo od masterja")
    sub.add_parser("memory", help="prikaži lokalni spomin (števila po učnih tabelah)")
    sub.add_parser("backup", help="master: izvoz spomina+agende v fleet/backup.json, commit+push v git")
    sub.add_parser("restore", help="katerikoli stroj: git pull + združi fleet/backup.json v lokalni spomin/agendo")
    args = parser.parse_args(argv)

    if args.cmd == "serve":
        if not settings.fleet_token:
            print("[fleet] ROB_FLEET_TOKEN ni nastavljen — fail-closed, ne zaženem.")
            return 1
        import uvicorn
        print(f"[fleet] master strežnik na :{settings.fleet_port} "
              f"(role=master, token zaščiten). Za workerje: ROB_FLEET_ROLE=worker.")
        uvicorn.run(create_app(), host="0.0.0.0", port=settings.fleet_port)
        return 0

    if args.cmd == "memory":
        for table, n in memory_sync.count_memory().items():
            print(f"  {table:<22} {n}")
        return 0

    if args.cmd == "backup":
        return _cmd_backup()
    if args.cmd == "restore":
        return _cmd_restore()

    client = FleetClient(settings.fleet_master_url, settings.fleet_token)
    if args.cmd == "status":
        try:
            st = client.status()
        except Exception as e:
            print(f"[fleet] napaka pri statusu: {e}")
            return 1
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return 0
    if args.cmd == "claim":
        try:
            item = client.claim()
        except Exception as e:
            print(f"[fleet] napaka pri claim-u: {e}")
            return 1
        print(json.dumps(item, indent=2, ensure_ascii=False) if item else "— (ni nalog)")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
