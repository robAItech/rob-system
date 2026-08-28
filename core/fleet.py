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

from core import agenda
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
        }

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
