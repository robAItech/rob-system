"""core/reality_check.py — 'reality check' po avto-team buildu.

Modul je zgrajen in njegovi testi so zeleni — ampak to NE pomeni, da je
PRAVILEN proti realnemu sistemu (teste piše isti LLM z isto predpostavko;
klasičen primer: health_metrics z logiko `state=='running'`, čeprav daemon
nikoli ni v `running`).

Reality check požene zgrajeni modul proti REALNIM `.rob_ai` podatkom
(ne tmp fixtures) in preveri POGODBO S SISTEMOM:
  1. deterministične funkcije z `base_dir` parametrom se pokličejo z realnim
     korenom in ne smejo pasti,
  2. če modul poroča o stanju daemona (`state` / `healthy`), mora biti izhod
     SKLADEN z realnim `daemon.json` — normalno stanje + svež heartbeat
     → `healthy` True.

Deterministično, brez LLM.
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Normalna obratovalna stanja daemona in prag svežine heartbeata — ENA
# avtoritativna definicija v actions/health_metrics (domenski modul); tukaj
# se importa, da ni podvojenih konstant (drift tveganje). Fallback, če
# health_metrics ni dosegljiv (deleted/rebuilt).
try:
    from actions.health_metrics.health_metrics import (  # noqa: E402
        _HEALTHY_STATES as _NORMAL_STATES,
        _HEARTBEAT_FRESH_SECONDS as _HEARTBEAT_FRESH_SECONDS,
    )
except Exception:
    _NORMAL_STATES = {
        "idle", "running", "running_task", "running_tick",
        "boot", "ensure_services",
    }
    _HEARTBEAT_FRESH_SECONDS = 300.0


def _read_daemon(root: Path) -> Dict[str, Any]:
    try:
        return json.loads((root / ".rob_ai" / "daemon.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _heartbeat_fresh(heartbeat_ts: Any) -> bool:
    if heartbeat_ts is None:
        return False
    try:
        return time.time() - float(heartbeat_ts) < _HEARTBEAT_FRESH_SECONDS
    except (TypeError, ValueError):
        return True  # ISO/neznano → ne moremo izračunati; ne obsojaj


def _check_system_contract(out: Dict[str, Any], root: Path,
                           fn_name: str, issues: List[str]) -> None:
    """Preveri, ali modul poroča o daemon stanju skladno z realnim sistemom."""
    real = _read_daemon(root)
    real_state = real.get("state")
    daemon = out.get("daemon") if isinstance(out.get("daemon"), dict) else out
    reported_state = daemon.get("state")
    # 1) Poročan state mora ustrezati realnemu (če modul poroča state).
    if real_state and reported_state and reported_state != real_state:
        issues.append(f"{fn_name}: poroča state={reported_state!r}, realni daemon je {real_state!r}")
    # 2) healthy mora biti True ob normalnem stanju + svežem heartbeat-u.
    if "healthy" in out:
        fresh = _heartbeat_fresh(real.get("heartbeat_ts"))
        expect = real_state in _NORMAL_STATES and fresh
        if out["healthy"] != expect:
            issues.append(
                f"{fn_name}: healthy={out['healthy']!r}, pričakovano {expect!r} "
                f"(realni state={real_state!r}, heartbeat svež={fresh})")


def run_reality_check(project: str, root: Optional[Path | str] = None) -> Dict[str, Any]:
    """Poženi zgrajeni modul proti realnim podatkom.

    Vrne ``{ok: bool, issues: [str]}``. `ok=False` = modul ni skladen z
    realnim sistemom (kljub zelenim lastnim testom).
    """
    root = Path(root) if root else PROJECT_ROOT
    module_dir = root / "actions" / project
    issues: List[str] = []

    # Varnost: project prihaja iz agende (dashboard/LLM) — omeji na varen slug
    # pred `import actions.<project>` (prepreči import injekcijo).
    if not re.match(r"^[A-Za-z0-9_-]+$", project):
        return {"ok": False, "issues": [f"neveljaven project name: {project!r}"]}
    if not module_dir.is_dir():
        return {"ok": False, "issues": [f"actions/{project} ne obstaja"]}
    if not (module_dir / "__init__.py").exists():
        return {"ok": False, "issues": [f"actions/{project}/__init__.py manjka"]}

    # Import modula — robustno: najprej kot podpaket `actions.<project>` (pravilni
    # relative importi v __init__.py), nato fallback z vstavitvijo imenika na path.
    mod = None
    try:
        mod = importlib.import_module(f"actions.{project}")
    except Exception:
        try:
            sys.path.insert(0, str(module_dir))
            mod = importlib.import_module(project)
        except Exception as e:  # pragma: no cover — import napake so raznolike
            return {"ok": False, "issues": [f"import fail: {e}"]}

    # Parametri, ki pomenijo "koren/sistemski imenik" → pokličemo z realnim korenom.
    _DIR_PARAMS = ("base_dir", "root", "cwd", "data_dir", "dir", "directory", "path")
    for name in dir(mod):
        if name.startswith("_"):
            continue
        obj = getattr(mod, name)
        if not callable(obj):
            continue
        try:
            sig = inspect.signature(obj)
        except (TypeError, ValueError):
            continue
        params = list(sig.parameters.values())
        dir_param = next((p for p in params if p.name in _DIR_PARAMS), None)
        if dir_param is None:
            continue  # ni deterministični bralec stanja s korenom → preskoči
        try:
            out = obj(**{dir_param.name: str(root)})
        except Exception as e:
            issues.append(f"{name}: real-run fail: {e}")
            continue
        if isinstance(out, dict):
            _check_system_contract(out, root, name, issues)

    return {"ok": not issues, "issues": issues}
