"""core/daemon.py — P1: avtonomni daemon (24/7).

En master proces, ki poganja Rob AI Studio sam (skok na 10x):
  - idempotentno dvigne LiteLLM proxy (:4010) + Command-Center dashboard (:8787)
    z reuse `core/dev_cli.cmd_serve`,
  - prazni agendo (`core/agenda`) skozi RSI zanko — subprocess `run_swarm.py --item`,
    ena naloga naenkrat (single-flight) s trdim timeoutom,
  - periodično predlaga nove naloge iz šibkosti sistema (`core/goal_autonomy`) —
    polna avtonomija: tudi kodne naloge gredo v agendo brez človeške potrditve,
  - teče vzdrževalne jobe: konsolidacija spomina, strateška refleksija,
    samorazvoj, meta-eval in polni eval,
  - piše heartbeat v `.rob_ai/daemon.json` (opazljivost prek `GET /api/daemon`).

Sinhronska `while True` zanka — RSI je blokirajoč, naloge so single-flight,
tikovi tečejo le ko je daemon idle (vsi pišejo memory.db/actions, ne smejo se
prekrivati). Windows: brez systemd, avtozagon prek HKCU Run (autostart.bat).

UPORABA:
  python core/daemon.py            # teči v nedogled (avtozagon)
  python core/daemon.py --once     # ena enota dela, nato izhod (smoke test)
  python core/daemon.py --status   # izpiši stanje daemona, izhod
  python core/daemon.py --stop     # graceful shutdown tekočega daemona
  python core/daemon.py --serve    # dvigni proxy+dashboard in izhod
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

# Vsili UTF-8 izhod tudi, ko je stdout preusmerjen na pipe (ne terminal).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass  # reconfigure ni vedno na voljo (nekateri okolji)

# Koren projekta vedno na PYTHONPATH (daemon se lahko požene od kjerkoli).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import agenda, audit, config, dev_cli, fleet, memory_sync

ROB_AI = PROJECT_ROOT / ".rob_ai"
DAEMON_FILE = ROB_AI / "daemon.json"
LOCK_FILE = ROB_AI / "daemon.lock"
STOP_FILE = ROB_AI / "daemon.stop"
DB_PATH = ROB_AI / "memory.db"

_stop_requested = False

# P9 fleet — odpornost: ko master ni dosegljiv, worker NE "išče" povezave
# (backoff). Po preteku se poskusi enkrat; uspeh ga ponastavi.
_fleet_offline_until = 0.0


def _fleet_offline() -> bool:
    return time.time() < _fleet_offline_until


def _fleet_mark_offline(settings) -> None:
    global _fleet_offline_until
    _fleet_offline_until = time.time() + getattr(settings, "fleet_backoff_seconds", 300)


def _fleet_mark_online() -> None:
    global _fleet_offline_until
    _fleet_offline_until = 0.0


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Single-instance lock
# ------------------------------------------------------------------ #
def _lock_pid_alive(pid: int) -> bool:
    """Ali PID še obstaja. Unix: `os.kill(pid, 0)`. Windows: `OpenProcess`
    probe — `os.kill(pid, 0)` tam vrže WinError 87 (param error) za vsak PID,
    zato ga ne moremo uporabiti kot probe."""
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
            return True  # ne moremo preveriti → ne briši stale locka (varno)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True  # nismo prepričani → smatramo živega (varno: ne briši)


def _acquire_lock() -> None:
    """Zagotovi, da teče SAMO en daemon. Stale lock (mrtav PID) se pobere."""
    ROB_AI.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("utf-8"))
            os.close(fd)
            return
        except FileExistsError:
            try:
                pid = int(LOCK_FILE.read_text(encoding="utf-8").strip())
            except Exception:
                pid = None
            if pid is not None and _lock_pid_alive(pid):
                raise RuntimeError(f"daemon že teče (PID {pid})")
            # Stale lock — lastnik je mrtev; odstrani in poskusi znova.
            try:
                LOCK_FILE.unlink()
            except OSError:
                pass
            time.sleep(0.5)


def _release_lock() -> None:
    try:
        LOCK_FILE.unlink()
    except OSError:
        pass


# ------------------------------------------------------------------ #
#  Heartbeat (.rob_ai/daemon.json)
# ------------------------------------------------------------------ #
def _load_heartbeat() -> dict:
    if not DAEMON_FILE.exists():
        return {}
    try:
        data = json.loads(DAEMON_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_heartbeat(state: str, **extra) -> None:
    """Prepiše daemon.json z novim stanjem. Nikoli ne pade (disk poln → skip)."""
    hb = _load_heartbeat()
    hb["state"] = state
    hb["pid"] = os.getpid()
    hb["started_at"] = hb.get("started_at", _now())
    hb["heartbeat_ts"] = _now()
    for k, v in extra.items():
        if v is None:
            hb.pop(k, None)  # None = počisti polje (npr. stale current_task ob restartu)
        else:
            hb[k] = v
    try:
        tmp = DAEMON_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(hb, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, DAEMON_FILE)
    except OSError:
        pass


def _append_error(msg: str) -> None:
    """Ring buffer zadnjih 5 napak v daemon.json."""
    hb = _load_heartbeat()
    errs = hb.get("last_errors") or []
    errs.append({"ts": _now(), "error": str(msg)[:300]})
    hb["last_errors"] = errs[-5:]
    try:
        tmp = DAEMON_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(hb, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, DAEMON_FILE)
    except OSError:
        pass


# ------------------------------------------------------------------ #
#  Scheduler (periodični jobi)
# ------------------------------------------------------------------ #
class Scheduler:
    """Tabela jobov z intervali. `next_due`/`last_run` preživita restart
    (perzistirana v daemon.json pod "jobs")."""

    def __init__(self) -> None:
        self._jobs: list[dict] = []

    def add(self, name: str, run_fn, interval_seconds: int) -> None:
        self._jobs.append({
            "name": name,
            "run_fn": run_fn,
            "interval_seconds": int(interval_seconds),
            "last_run": 0,
            "next_due": 0,
        })

    def load_persisted(self, persisted: dict | None) -> None:
        for j in self._jobs:
            p = (persisted or {}).get(j["name"])
            if isinstance(p, dict):
                j["last_run"] = int(p.get("last_run") or 0)
                j["next_due"] = int(p.get("next_due") or 0)

    def warm_up(self, now: int) -> None:
        """Prvi zagon brez perzistiranega stanja: prvi termin vsakega joba je
        SORAZMEREN njegovemu intervalu (interval//24 → dnevni v ~1h, tedenski
        v ~7h, goal 6h v ~15 min) + majhen index offset (da se jobi z istim
        intervalom ne zaženejo vsi naenkrat). Tedenski jobi se ob svežem
        boot-u torej NE poženejo v prvih minutah (prej = drag self-check)."""
        for i, j in enumerate(self._jobs):
            if j["next_due"] <= 0:
                interval = max(int(j["interval_seconds"]), 1)
                j["next_due"] = now + max(interval // 24, 60) + 60 * i

    def due(self, now: int) -> dict | None:
        """Prvi job, ki je na vrsti (po vrstnem redu dodajanja)."""
        for j in self._jobs:
            if j["next_due"] <= now:
                return j
        return None

    def complete(self, name: str, now: int) -> None:
        """Po izvedbi joba zamakni naslednji termin za en interval (tudi ob
        napaki — da napaka ne hot-loopa)."""
        for j in self._jobs:
            if j["name"] == name:
                j["last_run"] = now
                j["next_due"] = now + j["interval_seconds"]
                return

    def to_dict(self) -> dict:
        return {
            j["name"]: {
                "last_run": j["last_run"],
                "next_due": j["next_due"],
                "interval_seconds": j["interval_seconds"],
            }
            for j in self._jobs
        }


# ------------------------------------------------------------------ #
#  Periodični jobi (run_fn signature: (settings, cfg) -> dict)
# ------------------------------------------------------------------ #
def _tick_consolidate(settings, cfg) -> dict:
    """Zanka 1 — spominska konsolidacija: surove epizode → semantične lekcije."""
    from core.memory_consolidation import MemoryConsolidator
    return MemoryConsolidator(DB_PATH).consolidate()


def _tick_reflect(settings, cfg) -> dict:
    """P3 — strateška samorefleksija: operativna načela iz lekcij (z varovanjem)."""
    from core.strategy_reflect import StrategyReflector
    return StrategyReflector(DB_PATH).run_cycle(dry_run=False)


def _tick_improve(settings, cfg) -> dict:
    """Zanka 3 — samorazvoj RSI sistemskega prompta (predlog→guard→test→promocija)."""
    from core.loopx_bridge import RSI_PROMPT_SYSTEM
    from core.self_improve import SelfImprover
    imp = SelfImprover(DB_PATH)
    current = imp.registry.get_active("rsi_heal_system", RSI_PROMPT_SYSTEM)
    return imp.run_cycle(current, imp.gather_context(), dry_run=False)


def _tick_meta_check(settings, cfg) -> dict:
    """Zanka 4 — meta-eval: primerjaj s snapshot-om po zadnji nalogi; ob
    regresiji avtomatsko rollback samorazvojnih sprememb."""
    from core.meta_eval import MetaEvaluator
    last_id = _load_heartbeat().get("last_snapshot_id")
    if not last_id:
        return {"skipped": "še ni snapshot-a (daemon še ni obdelal naloge)"}
    return MetaEvaluator(DB_PATH).check(int(last_id), auto_rollback=True)


def _tick_full_eval(settings, cfg) -> dict:
    """P0 eval — polni SWE-bench stil eval avtonomnosti. Le ko je agenda prazna
    in je dovolj prostora na disku (težek: LLM + Docker)."""
    if agenda.pending():
        return {"skipped": "agenda ni prazna"}
    try:
        free = shutil.disk_usage(PROJECT_ROOT).free
        if free < settings.daemon_min_free_gb * (2 ** 30):
            return {"skipped": f"premalo prostora na disku ({free / 2**30:.1f} GiB)"}
    except OSError:
        pass
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    r = subprocess.run(
        [sys.executable, "evaluate_autonomy.py"],
        env=env, cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    return {"ok": r.returncode == 0, "returncode": r.returncode}


def _tick_goal(settings, cfg) -> dict:
    """P4 + P1 — goal autonomy: predlagaj naslednje naloge iz šibkosti sistema
    in jih POLNO AVTONOMNO vvrzi v agendo (tudi kodne). tune/consolidate/improve
    predlogi so že pokriti s periodicnimi jobi (ne grejo skozi RSI build)."""
    if len(agenda.pending()) >= settings.daemon_goal_pending_cap:
        return {"enqueued": 0, "reason": "cap"}
    from core.goal_autonomy import GoalProposer
    proposals = GoalProposer(DB_PATH).propose(limit=settings.daemon_goal_max_enqueue)
    existing = {str(g.get("goal", ""))[:120] for g in agenda.all_() if g.get("goal")}
    enqueued = 0
    for p in proposals:
        if p.get("action") != "build":
            continue
        goal_text = str(p.get("goal", "")).strip()
        if not goal_text or goal_text[:120] in existing:
            continue
        agenda.add(goal_text, kind="autonomous", target=p.get("project"),
                   source="goal_autonomy")
        existing.add(goal_text[:120])
        enqueued += 1
    return {"enqueued": enqueued, "proposed": len(proposals)}


def _tick_fleet_memory(settings, cfg) -> dict:
    """Worker: periodična sinhronizacija z masterjem (1×/uro, le ko je dosegljiv):
    pull (fresh lekcije) + push (svoje nove) + heartbeat (last_seen na masterju)."""
    pulled = _fleet_pull_memory(settings)
    pushed = _fleet_push_memory(settings)
    _fleet_heartbeat(settings)
    return {"pulled": pulled, "pushed": pushed}


def _tick_fleet_backup(settings, cfg) -> dict:
    """Master: avtomatski backup spomina+agende v git (odpornost — master ni
    slepa ulica). Idempotentno: brez sprememb ne naredi novega commita."""
    try:
        rc = fleet._cmd_backup()
        return {"backup": "ok" if rc == 0 else f"rc={rc}"}
    except Exception as e:
        _append_error(f"fleet backup: {e}")
        return {"backup": f"napaka: {e}"}


def _tick_fleet_git_sync(settings, cfg) -> dict:
    """Master + worker: avtomatski `git pull --rebase --autostash` — izmenjava
    kode brez ročnega posega. Ob napaki/konfliktu se zabeleži in nadaljuje
    (daemon nikoli ne pade zaradi sync-a; naslednji interval poskusi znova).

    Nov pull-ana koda se uporabi ob naslednjem task-u (run_swarm požene svež
    proces) in ob naslednjem zagonu daemon-a; tekoči daemon proces teče naprej
    na stari kodi.
    """
    try:
        branch = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            capture_output=True, text=True, cwd=PROJECT_ROOT, check=False,
        ).stdout.strip() or "master"
        r = subprocess.run(
            ["git", "pull", "--rebase", "--autostash", "origin", branch],
            capture_output=True, text=True, cwd=PROJECT_ROOT, timeout=180,
        )
        out = (r.stdout or "").strip()
        if (r.stderr or "").strip():
            out += "\n" + r.stderr.strip()
        out = out[-500:]
        if r.returncode == 0:
            return {"git_sync": "ok", "branch": branch, "detail": out}
        _append_error(f"git sync (rc={r.returncode}): {out[-300:]}")
        return {"git_sync": f"napaka rc={r.returncode}", "branch": branch,
                "detail": out[-300:]}
    except Exception as e:
        _append_error(f"git sync: {e}")
        return {"git_sync": f"napaka: {e}"}


def _tick_weekly_report(settings, cfg) -> dict:
    """Avtonomija: tedenski readout (vsi izvedeni taski + kvaliteta + eval +
    fleet) → zapis `.rob_ai/weekly_report.md`. Napaka se zabeleži, ne ustavi."""
    try:
        from core.report import generate_weekly_report
        md = generate_weekly_report()
        out = ROB_AI / "weekly_report.md"
        out.write_text(md, encoding="utf-8")
        summary = next((ln for ln in md.split("\n")
                        if ln.startswith("**Povzetek:**")), "")
        return {"report": "ok", "file": str(out), "summary": summary}
    except Exception as e:
        _append_error(f"weekly report: {e}")
        return {"report": f"napaka: {e}"}


def _tick_quality_gate(settings, cfg) -> dict:
    """Avtonomija: kvalitetni prag — targete pod pragom označi disabled +
    zapiše eskalacijo uporabniku (dashboard feed + escalations.json)."""
    try:
        from core import quality
        min_runs = getattr(settings, "quality_min_runs", 3)
        min_rate = getattr(settings, "quality_min_success_rate", 0.5)
        grace = getattr(settings, "quality_reenable_grace_days", 7)
        res = quality.run_gate(min_runs=min_runs, min_success_rate=min_rate,
                               grace_days=grace)
        return {"gate": "ok", **res}
    except Exception as e:
        _append_error(f"quality gate: {e}")
        return {"gate": f"napaka: {e}"}


def _tick_fleet_monitor(settings, cfg) -> dict:
    """Phase 2 — pasivni operator monitor: telemetry/egress anomalije → isti
    findings tok; nato reassess, da se najdbe odrazijo v score/eskalaciji.

    Omogoči z FS_MONITOR_HOURS (> 0). 0 = izključeno (ni v schedulerju).
    """
    try:
        from actions.fleet_security import posture
        from actions.fleet_security.monitor import run_monitor_pass
        from actions.fleet_security.store import FleetSecurityStore
        store = FleetSecurityStore(settings.fs_db_path)
        res = run_monitor_pass(store)
        posture.run_assessment(store)
        return {"fleet_monitor": "ok", **res}
    except Exception as e:
        _append_error(f"fleet monitor: {e}")
        return {"fleet_monitor": f"napaka: {e}"}


def _tick_fleet_supplychain(settings, cfg) -> dict:
    """Phase 3 — model supply-chain preverba → isti findings tok + reassess."""
    try:
        from actions.fleet_security import posture
        from actions.fleet_security.supplychain import run_supplychain_pass
        from actions.fleet_security.store import FleetSecurityStore
        store = FleetSecurityStore(settings.fs_db_path)
        res = run_supplychain_pass(store)
        posture.run_assessment(store)
        return {"fleet_supplychain": "ok", **res}
    except Exception as e:
        _append_error(f"fleet supply chain: {e}")
        return {"fleet_supplychain": f"napaka: {e}"}


def _tick_fleet_threatintel(settings, cfg) -> dict:
    """Phase 3 — threat intel feed preverba → isti findings tok + reassess."""
    try:
        from actions.fleet_security import posture
        from actions.fleet_security.threatintel import run_threatintel_pass
        from actions.fleet_security.store import FleetSecurityStore
        store = FleetSecurityStore(settings.fs_db_path)
        res = run_threatintel_pass(store)
        posture.run_assessment(store)
        return {"fleet_threatintel": "ok", **res}
    except Exception as e:
        _append_error(f"fleet threat intel: {e}")
        return {"fleet_threatintel": f"napaka: {e}"}


def build_scheduler(settings) -> Scheduler:
    """Tabela periodicnih jobov, krmiljena z DAEMON_* nastavitvami."""
    sched = Scheduler()
    sched.add("consolidate", _tick_consolidate, settings.daemon_consolidate_hours * 3600)
    sched.add("reflect", _tick_reflect, settings.daemon_reflect_hours * 3600)
    sched.add("improve", _tick_improve, settings.daemon_improve_hours * 3600)
    sched.add("meta_check", _tick_meta_check, settings.daemon_meta_check_hours * 3600)
    if settings.daemon_full_eval_hours > 0:
        sched.add("full_eval", _tick_full_eval, settings.daemon_full_eval_hours * 3600)
    # Worker ne generira lastnih nalog (goal tick) — le izvaja naloge od masterja.
    if getattr(settings, "fleet_role", "standalone") != "worker":
        sched.add("goal", _tick_goal, settings.daemon_goal_hours * 3600)
    # P9 — "takojšnji" sync: worker periodično izmenja spomin z masterjem,
    # master avtomatsko dela git backup. 0 = izključeno.
    if (getattr(settings, "fleet_role", "standalone") == "worker"
            and getattr(settings, "fleet_sync_memory", True)
            and settings.fleet_memory_sync_seconds > 0):
        sched.add("fleet_memory", _tick_fleet_memory, settings.fleet_memory_sync_seconds)
    if (getattr(settings, "fleet_role", "standalone") == "master"
            and settings.fleet_backup_seconds > 0):
        sched.add("fleet_backup", _tick_fleet_backup, settings.fleet_backup_seconds)
    # P9 — avtomatski git sync na masterju IN workerju (pull --rebase --autostash),
    # da se koda izmenja brez ročnega posega. 0 = izključeno.
    if (getattr(settings, "fleet_role", "standalone") in ("master", "worker")
            and getattr(settings, "fleet_git_sync_seconds", 0) > 0):
        sched.add("fleet_git_sync", _tick_fleet_git_sync,
                  getattr(settings, "fleet_git_sync_seconds", 0))
    # Avtonomija — tedenski readout + kvalitetni prag (master/standalone; worker
    # agregira samo prek masterja). 0 = izključeno.
    if (getattr(settings, "fleet_role", "standalone") != "worker"
            and getattr(settings, "report_hours", 0) > 0):
        sched.add("weekly_report", _tick_weekly_report,
                  getattr(settings, "report_hours", 0) * 3600)
    if (getattr(settings, "fleet_role", "standalone") != "worker"
            and getattr(settings, "quality_gate_hours", 0) > 0):
        sched.add("quality_gate", _tick_quality_gate,
                  getattr(settings, "quality_gate_hours", 0) * 3600)
    # Phase 2 — pasivni fleet security monitor (telemetry/egress). 0 = off.
    if getattr(settings, "fs_monitor_hours", 0) > 0:
        sched.add("fleet_monitor", _tick_fleet_monitor,
                  settings.fs_monitor_hours * 3600)
    # Phase 3 — supply chain + threat intel (0 = off). Red team je on-demand.
    if getattr(settings, "fs_supplychain_hours", 0) > 0:
        sched.add("fleet_supplychain", _tick_fleet_supplychain,
                  settings.fs_supplychain_hours * 3600)
    if getattr(settings, "fs_threatintel_hours", 0) > 0:
        sched.add("fleet_threatintel", _tick_fleet_threatintel,
                  settings.fs_threatintel_hours * 3600)
    return sched


# ------------------------------------------------------------------ #
#  Čista odločitvena funkcija
# ------------------------------------------------------------------ #
def decide(agenda_pending: list, scheduler: Scheduler) -> tuple:
    """Vrne ("task", item) | ("tick", job) | ("idle", None).

    Prioritetni red (single-flight): naloga iz agende > periodični tick > idle.
    """
    if agenda_pending:
        return ("task", agenda_pending[0])
    job = scheduler.due(_now())
    if job is not None:
        return ("tick", job)
    return ("idle", None)


# ------------------------------------------------------------------ #
#  Storitve (proxy + dashboard)
# ------------------------------------------------------------------ #
def _proxy_base(cfg) -> str:
    return f"http://127.0.0.1:{dev_cli.PORT}"


def _proxy_ok(cfg) -> bool:
    return dev_cli.proxy_health(_proxy_base(cfg), cfg.master_key)


def _ensure_services(cfg) -> bool:
    """Idempotentno dvigne proxy+dashboard (reuse dev_cli.cmd_serve).
    Vrne True, če je proxy dosegljiv."""
    try:
        rc = dev_cli.cmd_serve(cfg)
        if rc != 0:
            print(f"[daemon] cmd_serve ni uspel (rc={rc}) — proxy ni dvignjen.")
            _append_error(f"cmd_serve rc={rc}: proxy se ni zagnal")
    except Exception as e:
        print(f"[daemon] cmd_serve napaka: {e}")
        _append_error(f"cmd_serve: {e}")
    return _proxy_ok(cfg)


def _fleet_server_ok(settings) -> bool:
    """Ali fleet strežnik (uvicorn :ROB_FLEET_PORT) že posluša."""
    return dev_cli.port_listener(getattr(settings, "fleet_port", 8789)) is not None


def _ensure_fleet_server(settings) -> bool:
    """Master: idempotentno dvigne fleet strežnik (`core/fleet.py serve`) v
    ozadju. Fail-closed: brez ROB_FLEET_TOKEN se `core/fleet.py serve` sam
    ustavi — tukaj brez tokena sploh ne zaženemo (in javimo razlog)."""
    if not getattr(settings, "fleet_token", ""):
        print("[daemon] ROB_FLEET_TOKEN ni nastavljen — fleet strežnik NI dvignjen "
              "(fail-closed; nastavi v .env na masterju).")
        return False
    if _fleet_server_ok(settings):
        return True   # že teče (npr. ročno `rob fleet serve`)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["PYTHONUTF8"] = "1"
    try:
        kwargs: dict = {}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        # Log v datoteko (ne DEVNULL), da je worker promet viden od zunaj
        # (/fleet/claim|result|memory|actions) — za debug in preverbo sync-a.
        logf = open(ROB_AI / "fleet_server.log", "a", encoding="utf-8")
        subprocess.Popen(
            [sys.executable, "core/fleet.py", "serve"],
            env=env, cwd=PROJECT_ROOT,
            stdout=logf, stderr=logf, **kwargs)
    except OSError as e:
        print(f"[daemon] fleet serve zagon ni uspel: {e}")
        _append_error(f"fleet serve: {e}")
        return False
    # Počakaj do 5 s, da uvicorn vzpostavi port.
    for _ in range(10):
        if _fleet_server_ok(settings):
            print(f"[daemon] fleet strežnik dvignjen na :{settings.fleet_port}.")
            return True
        time.sleep(0.5)
    print("[daemon] fleet strežnik se ni vzpostavil v 5 s.")
    _append_error("fleet serve: ni vzpostavljen v 5 s")
    return False


# ------------------------------------------------------------------ #
#  Izvajanje dela
# ------------------------------------------------------------------ #
def _heartbeat_tasks(active: list) -> list:
    """Seznam aktivnih nalog za heartbeat (current_tasks)."""
    return [
        {"id": e["item"]["id"],
         "goal": str(e["item"].get("goal", ""))[:400],
         "target": e["item"].get("target", ""),
         "kind": e["item"].get("kind", "python"),
         "started_at": e["started_at"]}
        for e in active
    ]


def _fleet_claim_remote(settings) -> list:
    """Worker: claim eno nalogo od masterja in jo zapiši v LOKALNO senčno
    agendo (fleet_claimed, status running), da `run_swarm.py --item` deluje.
    Master ni dosegljiv (ali backoff aktiven) → prazno, BREZ iskanja povezave."""
    if _fleet_offline():
        return []
    try:
        client = fleet.FleetClient(settings.fleet_master_url, settings.fleet_token)
        item = client.claim(worker=fleet.host_id())
        _fleet_mark_online()
    except Exception as e:
        print(f"[daemon] fleet claim napaka: {e}")
        _append_error(f"fleet claim: {e}")
        _fleet_mark_offline(settings)
        return []
    if not item:
        return []
    item["fleet_claimed"] = True
    item["status"] = "running"   # senčna agenda: lokalni claim_pending je ne vzame
    item["updated_at"] = int(time.time())
    agenda.upsert_fleet(item)
    return [item]


def _fleet_report_result(settings, item: dict, ok: bool, detail: str, duration_s: float) -> None:
    """Worker: po zaključku naloge pošlje izid masterju. Napaka se zabeleži,
    naloga pa ostane lokalno (master jo bo re-claim-a po lease TTL)."""
    if _fleet_offline():
        return
    try:
        fleet.FleetClient(settings.fleet_master_url, settings.fleet_token).result(
            item_id=item["id"], ok=ok, target=item.get("target", item["id"]),
            detail=detail, duration_s=duration_s, worker=fleet.host_id())
        _fleet_mark_online()
    except Exception as e:
        _append_error(f"fleet result: {e}")
        _fleet_mark_offline(settings)


def _fleet_pull_memory(settings) -> dict:
    """Worker: potegni masterjev spomin (učne tabele) in ga združi lokalno.
    Backoff (master nedosegljiv) → prazno, brez iskanja povezave."""
    if not getattr(settings, "fleet_sync_memory", True) or _fleet_offline():
        return {}
    try:
        client = fleet.FleetClient(settings.fleet_master_url, settings.fleet_token)
        payload = client.memory_pull()
        _fleet_mark_online()
        stats = memory_sync.merge_memory(payload)
        if any((stats or {}).values()):
            print(f"[daemon] fleet: povlekel spomin od masterja → {stats}")
        return stats or {}
    except Exception as e:
        _append_error(f"fleet memory pull: {e}")
        _fleet_mark_offline(settings)
        return {}


def _fleet_push_memory(settings) -> dict:
    """Worker: pošlji svoj spomin (nove lekcije) nazaj masterju — agregacija."""
    if not getattr(settings, "fleet_sync_memory", True) or _fleet_offline():
        return {}
    try:
        client = fleet.FleetClient(settings.fleet_master_url, settings.fleet_token)
        payload = memory_sync.export_memory()
        added = client.memory_push(payload)
        _fleet_mark_online()
        if added and any((added or {}).values()):
            print(f"[daemon] fleet: poslal spomin masterju → {added}")
        return added or {}
    except Exception as e:
        _append_error(f"fleet memory push: {e}")
        _fleet_mark_offline(settings)
        return {}


def _fleet_heartbeat(settings) -> None:
    """Worker: sporoči masterju, da je živ (ob urnem sync ticku)."""
    if _fleet_offline():
        return
    try:
        fleet.FleetClient(settings.fleet_master_url, settings.fleet_token).heartbeat(
            worker=fleet.host_id(), tasks=[])
        _fleet_mark_online()
    except Exception as e:
        _fleet_mark_offline(settings)


def _fleet_push_actions(settings, module: str) -> None:
    """Worker: po uspešnem build-u pošlje zgrajeni modul masterju prek HTTP
    (`POST /fleet/actions`) — master zapiše v actions/<module>/. Brez gita na
    workerju; isti kanal kot claim/result/spomin."""
    if not module or _fleet_offline():
        return
    try:
        files = fleet.export_module_files(module)
        if not files:
            print(f"[daemon] fleet: modul {module} nima datotek — preskočim push.")
            return
        fleet.FleetClient(settings.fleet_master_url, settings.fleet_token).push_actions(
            module, files)
        _fleet_mark_online()
        print(f"[daemon] fleet: poslal modul {module} masterju ({len(files)} datotek).")
    except Exception as e:
        _append_error(f"fleet push actions: {e}")
        _fleet_mark_offline(settings)


def _spawn_task(item: dict, settings, cfg) -> dict:
    """Zažene run_swarm.py --item v subprocesu (NE-blokirajoče). Vrne entry dict."""
    item_id = item["id"]
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env["PYTHONUTF8"] = "1"
    popen = subprocess.Popen(
        [sys.executable, "run_swarm.py", "--item", item_id],
        env=env, cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    audit.record(event="daemon-task", project=item.get("target", item_id),
                 status="started", detail=str(item.get("goal", ""))[:400])
    started = _now()
    timeout = settings.daemon_task_timeout_seconds or None
    return {
        "item": item,
        "popen": popen,
        "started_at": started,
        "deadline": (started + timeout) if timeout else None,
        "killed": False,
    }


def _reap_task(entry: dict, settings, cfg, active: list) -> dict:
    """Logika PO zaključku subprocesa (rearm_repeat, snapshot, audit, heartbeat)."""
    item = entry["item"]
    item_id = item["id"]
    popen = entry["popen"]
    rc = getattr(popen, "returncode", None)
    ok = rc == 0

    if entry.get("killed"):
        ok = False
        agenda.mark(item_id, "failed")
        audit.record(event="daemon-task", project=item.get("target", item_id),
                     status="failed", detail="timeout (trdi daemon timeout)")
    # Subprocess je padel tako trdo, da itema ni označil (še running) → failed.
    if not ok:
        after = agenda.get(item_id)
        if after and after.get("status") == "running":
            agenda.mark(item_id, "failed")

    try:
        agenda.rearm_repeat()
    except Exception as e:
        _append_error(f"rearm_repeat: {e}")
    snapshot_id = None
    try:
        from core.meta_eval import MetaEvaluator
        snapshot_id = MetaEvaluator(DB_PATH).snapshot(label=f"after-{item_id}")
    except Exception as e:
        _append_error(f"meta snapshot: {e}")

    duration = round(time.time() - entry["started_at"], 1)

    # Worker: izid posreduj masterju (naloga pripada floti, ne lokalni agendi)
    # + pošlji nazaj svoj spomin (nove lekcije iz tega teka).
    if getattr(settings, "fleet_role", "standalone") == "worker" and item.get("fleet_claimed"):
        _fleet_report_result(settings, item, ok, detail=f"rc={rc}", duration_s=duration)
        _fleet_push_memory(settings)
        # Uspešen build → zgrajeni modul pošlji masterju prek HTTP (ne git).
        if ok:
            _fleet_push_actions(settings, item.get("target", ""))

    audit.record(event="daemon-task", project=item.get("target", item_id),
                 status="ok" if ok else "failed",
                 detail=f"duration_s={duration}"
                        + (f" snapshot={snapshot_id}" if snapshot_id else ""))
    # Heartbeat: če tečejo še druge naloge → running_task, sicer idle.
    still = [e for e in active if e is not entry]
    _write_heartbeat("running_task" if still else "idle",
                     current_tasks=_heartbeat_tasks(still) if still else None,
                     current_tick=None,
                     last_run_summary={"kind": "task", "id": item_id, "ok": ok,
                                       "duration_s": duration},
                     last_snapshot_id=snapshot_id)
    return {"ok": ok, "duration_s": duration, "snapshot_id": snapshot_id}


def _reap_finished(active: list, settings, cfg) -> int:
    """Pollira vse aktivne subprocese; zaključene reapa (post-task logika).
    Timeout presežen → kill (item gre v failed ob naslednjem pollu).
    Vrne število reapanih."""
    now = _now()
    n = 0
    remaining = []
    for entry in active:
        popen = entry["popen"]
        deadline = entry.get("deadline")
        if (not entry.get("killed") and deadline and now >= deadline
                and popen.poll() is None):
            print(f"[daemon] timeout ({entry['item']['id']}) — ubijam nalogo.")
            try:
                popen.kill()
            except OSError:
                pass
            entry["killed"] = True
            remaining.append(entry)   # reapa se ob naslednjem pollu
            continue
        rc = popen.poll()
        if rc is not None:
            entry["returncode"] = rc
            _reap_task(entry, settings, cfg, active)   # active še vsebuje entry
            n += 1
        else:
            remaining.append(entry)
    active[:] = remaining
    return n


def run_tick(job: dict, settings, cfg, scheduler: Scheduler) -> dict:
    """Izvede en periodični job. Napaka ne hot-loopa — naslednji termin je
    čez en interval."""
    name = job["name"]
    _write_heartbeat("running_tick", current_tick=name, current_tasks=None)
    started = time.time()
    ok = True
    error = None
    try:
        result = job["run_fn"](settings, cfg)
    except Exception as e:
        ok = False
        error = str(e)[:400]
        print(f"[daemon] tick {name} napaka: {error}")
        _append_error(f"tick {name}: {error}")
        result = None
    scheduler.complete(name, _now())
    audit.record(event="daemon-tick", project=name, status="ok" if ok else "failed",
                 detail=error or "ok")
    duration = round(time.time() - started, 1)
    _write_heartbeat("idle", current_tick=None, current_tasks=None,
                     last_run_summary={"kind": "tick", "name": name, "ok": ok,
                                       "duration_s": duration})
    return {"ok": ok, "duration_s": duration, "result": result}


def recover_agenda() -> int:
    """Ob boot: itemi v 'running' → 'pending' (daemon/subprocess je padel sredi
    naloge — running sme obstajati samo med aktivno izvedbo)."""
    n = 0
    for it in agenda.all_():
        if it.get("status") == "running":
            agenda.mark(it["id"], "pending")
            n += 1
    return n


# ------------------------------------------------------------------ #
#  Signal handling + glavna zanka
# ------------------------------------------------------------------ #
def _handle_signal(signum, frame) -> None:
    global _stop_requested
    _stop_requested = True


def run_loop(settings, cfg, once: bool = False) -> int:
    """Glavna zanka daemona. once=True → ena enota dela in izhod (smoke test)."""
    global _stop_requested  # pisana v sentinel veji → mora biti global, ne lokalna
    _stop_requested = False  # reset ob vsakem bootu (ne podeduj prejšnjega stop-a)
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    scheduler = build_scheduler(settings)
    scheduler.load_persisted(_load_heartbeat().get("jobs"))
    scheduler.warm_up(_now())

    workers = 1 if once else max(1, int(getattr(settings, "daemon_workers", 1) or 1))
    active: list = []   # [{item, popen, started_at, deadline, killed}]
    # P9 fleet: worker ne dviga storitev (proxy/dashboard) in ne generira lastnih
    # nalog — le potegne in izvede naloge od masterja (single-flight claim).
    is_worker = getattr(settings, "fleet_role", "standalone") == "worker"

    # BOOT
    _write_heartbeat("boot", current_tasks=None, current_tick=None)
    # Odstrani morebiten star stop sentinel (iz prejšnje seje).
    try:
        STOP_FILE.unlink()
    except OSError:
        pass
    recovered = recover_agenda()
    if recovered:
        print(f"[daemon] obnovljenih nalog (running→pending): {recovered}")

    if is_worker:
        # Nedokončane fleet senčne naloge (reboot workerja) izginejo — master
        # jih re-claim-a po lease TTL. Ni lokalnega podvajanja ob reboot.
        stale = [it for it in agenda.all_()
                 if it.get("fleet_claimed") and it.get("status") != "done"]
        for it in stale:
            agenda.delete_item(it["id"])
        if stale:
            print(f"[daemon] worker: počiščenih {len(stale)} nedokončanih fleet senčnih nalog.")
        # Faza 4 — deljen spomin: ob boot-u potegni masterjev spomin, da ima
        # worker od začetka sveže lekcije (in jih nato vrača po vsaki nalogi).
        _fleet_pull_memory(settings)
        _write_heartbeat("boot_worker", current_tasks=None, current_tick=None)
    else:
        _write_heartbeat("ensure_services", current_tasks=None)
        if not _ensure_services(cfg):
            print("[daemon] proxy ni dosegljiv po zagonu — stanje degraded, retry v zanki.")
            _write_heartbeat("degraded", current_tasks=None)
        # P9 — master: avto-zagon fleet strežnika (:8789) v ozadju.
        if getattr(settings, "fleet_role", "standalone") == "master":
            _ensure_fleet_server(settings)
    print(f"[daemon] zagnan (PID {os.getpid()}, once={once}, workers={workers}, "
          f"role={getattr(settings, 'fleet_role', 'standalone')})")

    last_hb = _now()
    try:
        while not _stop_requested or active:
            # Stop sentinel (`rob daemon --stop`) → graceful DRAIN (dokončaj aktivne).
            if STOP_FILE.exists() and not _stop_requested:
                print("[daemon] prejeta stop zahteva — dokončam aktivne naloge.")
                _stop_requested = True
            now = _now()

            # DRAIN MODE (stop, še aktivne) — reapa, ne spawi novih.
            if _stop_requested:
                _reap_finished(active, settings, cfg)
                if active:
                    _write_heartbeat("shutdown", current_tasks=_heartbeat_tasks(active),
                                     current_tick=None)
                    time.sleep(settings.daemon_idle_seconds)
                    continue
                break

            # Fleet strežnik (master): če pade, ga občasno spet dvignemo.
            if (not is_worker and getattr(settings, "fleet_role", "standalone") == "master"
                    and not _fleet_server_ok(settings)
                    and now - last_hb >= settings.daemon_proxy_retry_seconds):
                print("[daemon] fleet strežnik dol — ponovni dvig.")
                _ensure_fleet_server(settings)

            # HEALTH GATE — brez proxyja ni novih nalog/tickov (worker ga preskoči).
            if not is_worker and not _proxy_ok(cfg):
                if now - last_hb >= settings.daemon_proxy_retry_seconds:
                    print("[daemon] proxy dol — ponovni poskus dviga storitev.")
                    _ensure_services(cfg)
                    last_hb = now
                _write_heartbeat("degraded", current_tasks=_heartbeat_tasks(active),
                                 agenda_pending=len(agenda.pending()))
                if once and not active:
                    return 0
                time.sleep(settings.daemon_idle_seconds)
                continue

            # 1) REAP zaključene subprocese.
            reaped = _reap_finished(active, settings, cfg)
            if once and reaped >= 1 and not active:
                return 0   # ena enota dela končana

            # 2) SPAWN do workers (distinct targets).
            spawned = 0
            if len(active) < workers:
                exclude = {a["item"].get("target") or a["item"]["id"] for a in active}
                limit = workers - len(active)
                if once:
                    limit = min(limit, 1) if not active else 0
                if limit > 0:
                    if is_worker:
                        items = _fleet_claim_remote(settings)
                    elif getattr(settings, "fleet_role", "standalone") == "master":
                        # Master = koordinator: naloge SLUŽI workerjem prek
                        # /fleet/claim, sam jih NE izvaja — sicer tekmuje z
                        # workerji in jim (hitreje) pobere vse (claim_pending
                        # ne postavi claimed_by → worker nikoli nič ne dobi).
                        items = []
                    else:
                        items = agenda.claim_pending(exclude_targets=exclude, limit=limit)
                    for item in items:
                        active.append(_spawn_task(item, settings, cfg))
                        spawned += 1

            # 3) TICK SAMO ko je idle (single-flight za vzdrževanje).
            if not active:
                job = scheduler.due(_now())
                if job is not None:
                    run_tick(job, settings, cfg, scheduler)
                    if once:
                        return 0
                    _write_heartbeat("idle", current_tasks=None, current_tick=None,
                                     jobs=scheduler.to_dict(),
                                     agenda_pending=len(agenda.pending()))
                    last_hb = now
                    time.sleep(settings.daemon_idle_seconds)
                    continue
                if once:
                    return 0
                if now - last_hb >= settings.daemon_heartbeat_seconds:
                    _write_heartbeat("idle", current_tasks=None, current_tick=None,
                                     jobs=scheduler.to_dict(),
                                     agenda_pending=len(agenda.pending()))
                    last_hb = now
                time.sleep(settings.daemon_idle_seconds)
                continue

            # 4) Aktivne naloge tečejo — periodični heartbeat.
            if spawned or now - last_hb >= settings.daemon_heartbeat_seconds:
                _write_heartbeat("running_task", current_tasks=_heartbeat_tasks(active),
                                 current_tick=None, jobs=scheduler.to_dict(),
                                 agenda_pending=len(agenda.pending()))
                last_hb = now
            time.sleep(settings.daemon_idle_seconds)
    except KeyboardInterrupt:
        print("\n[daemon] Ctrl+C — graceful shutdown.")
        _stop_requested = True
        while active:   # drain: dokončaj aktivne
            _reap_finished(active, settings, cfg)
            if active:
                time.sleep(settings.daemon_idle_seconds)
    finally:
        for e in active:   # defenzivno: ubij morebitne sirote
            try:
                e["popen"].kill()
            except OSError:
                pass
        _write_heartbeat("shutdown", current_tasks=None, current_tick=None,
                         jobs=scheduler.to_dict())
        _release_lock()
    return 0


# ------------------------------------------------------------------ #
#  CLI
# ------------------------------------------------------------------ #
def _cmd_status() -> int:
    hb = _load_heartbeat()
    if not hb:
        print("[daemon] ni heartbeat datoteke — daemon še ni tekel.")
    else:
        print(f"State       : {hb.get('state')}")
        print(f"PID         : {hb.get('pid')}")
        print(f"started_at  : {hb.get('started_at')}")
        print(f"heartbeat   : {hb.get('heartbeat_ts')}")
        if hb.get("current_tasks"):
            print(f"Aktivne naloge ({len(hb['current_tasks'])}):")
            for t in hb["current_tasks"]:
                print(f"  - {t['id']} · {t.get('goal','')[:60]} · {t.get('target','')}")
        elif hb.get("current_task"):   # legacy (stara heartbeat)
            print(f"Trenutna naloga: {hb.get('current_task')}")
        if hb.get("current_tick"):
            print(f"Trenutni tick  : {hb.get('current_tick')}")
        if hb.get("last_run_summary"):
            print(f"Zadnji zagon: {hb.get('last_run_summary')}")
        jobs = hb.get("jobs") or {}
        print("Jobi (next_due / last_run):")
        for name, j in sorted(jobs.items()):
            print(f"  {name:<12} next_due={j.get('next_due')} last_run={j.get('last_run')}")
        errs = hb.get("last_errors") or []
        if errs:
            print("Zadnje napake:")
            for e in errs[-3:]:
                print(f"  {e.get('ts')}  {e.get('error')}")
    print(f"Agenda pending: {len(agenda.pending())}")
    return 0


def _cmd_stop() -> int:
    hb = _load_heartbeat()
    pid = hb.get("pid")
    if not pid:
        print("[daemon] ni tekočega daemona (ni PID v daemon.json).")
        return 1
    # Na Windows `os.kill(pid, SIGTERM)` = TerminateProcess → TRD uboj, brez
    # graceful handlerja (signal handler ne steče). Zato `--stop` napiše stop
    # sentinel, ki ga daemon prebere ob naslednji iteraciji → graceful shutdown
    # (shutdown heartbeat + release lock). Če daemon sredi dolge naloge, počaka.
    try:
        STOP_FILE.write_text(json.dumps({"pid": int(pid), "ts": _now()}),
                             encoding="utf-8")
        print(f"[daemon] stop zahteva poslana (PID {pid}) — graceful shutdown.")
    except OSError as e:
        print(f"[daemon] ni mogoče zapisati stop zahteve: {e}")
        return 1
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="rob daemon",
        description="P1 — avtonomni daemon: agendo prazni, sam predlaga naloge, "
                    "teče periodične jobe in piše heartbeat (24/7).",
    )
    parser.add_argument("--once", action="store_true",
                        help="ena enota dela, nato izhod (smoke test)")
    parser.add_argument("--status", action="store_true",
                        help="izpiši stanje daemona in izhod")
    parser.add_argument("--stop", action="store_true",
                        help="graceful shutdown tekočega daemona")
    parser.add_argument("--serve", action="store_true",
                        help="dvigni proxy+dashboard in izhod (wrapper na dev_cli)")
    args = parser.parse_args(argv)

    if args.serve:
        return dev_cli.cmd_serve(dev_cli.Config.from_root(PROJECT_ROOT))
    if args.status:
        return _cmd_status()
    if args.stop:
        return _cmd_stop()

    settings = config.settings
    cfg = dev_cli.Config.from_root(PROJECT_ROOT)
    try:
        _acquire_lock()
    except RuntimeError as e:
        print(f"[daemon] {e}")
        return 2
    return run_loop(settings, cfg, once=args.once)


if __name__ == "__main__":
    sys.exit(main())
