"""health_metrics — čista domenska logika za opazljivost sistema.

Bere `.rob_ai/daemon.json` (polji ``state`` in ``heartbeat_ts``) ter
`.rob_ai/agenda.json` (števci nalog po statusih ``pending`` / ``done`` /
``failed``) in vrne dict oz. kratek tekstovni povzetek.

Odporno na manjkajoče datoteke in poškodovan JSON: nikoli ne pade,
manjkajoče vrednosti nadomesti s privzetimi (``"unknown"`` / ``None``)
in ob težavi doda ključ ``error``.
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

_DEFAULT_STATE = "unknown"

_STATUS_KEYS = ("pending", "done", "failed")
_AGENDA_COLLECTION_KEYS = ("items", "tasks", "entries", "agenda")

# Daemon je ZDRAV v normalnih obratovalnih stanjih (idle, dela, se dviga) —
# NE samo v "running" (to stanje daemon nikoli ne ima). Nezdrav = shutdown/degraded.
_HEALTHY_STATES = {
    "idle", "running", "running_task", "running_tick",
    "boot", "ensure_services",
}
# Daemon piše heartbeat na ~30 s. Če je starejši od tega pragu, je zataknjen/padel.
_HEARTBEAT_FRESH_SECONDS = 300.0


def _heartbeat_age(heartbeat_ts: Any) -> Optional[float]:
    """Starost heartbeata v sekundah; None, če ni parsable (ISO/neznano)."""
    if heartbeat_ts is None:
        return None
    text = str(heartbeat_ts).strip()
    if not text:
        return None
    try:
        return time.time() - float(text)            # epoch (realni daemon)
    except ValueError:
        pass
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))  # ISO 8601
        return time.time() - dt.timestamp()
    except ValueError:
        return None


def _read_json(path: Path) -> Optional[dict]:
    """Preberi JSON objekt; vrni ``None`` ob manjkajoči datoteki ali napaki."""
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _read_agenda_json(path: Path) -> Optional[dict]:
    """Preberi agenda.json — dovoli tudi gol seznam nalog.

    Vrne dict (gol seznam normalizira v ``{"items": [...]}``) ali ``None``
    ob manjkajoči datoteki, neveljavnem JSON ali nepričakovani obliki.
    """
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, list):
        return {"items": data}
    if not isinstance(data, dict):
        return None
    return data


def _iter_agenda_items(agenda: dict) -> Iterable[Any]:
    """Iteriraj naloge iz agenda.json — podpira več dogovorjenih oblik.

    Podprte oblike: ``{"items": [...]}``, ``{"tasks": [...]}``,
    ``{"entries": [...]}``, ``{"agenda": [...]}``, gol seznam nalog ali
    dict preslikava ``id -> naloga``.
    """
    for key in _AGENDA_COLLECTION_KEYS:
        value = agenda.get(key)
        if isinstance(value, list):
            return iter(value)
    return (v for v in agenda.values() if isinstance(v, dict))


def _count_statuses(agenda: Optional[dict]) -> Dict[str, int]:
    """Preštej naloge po statusih; neznani statusi se ne štejejo."""
    counts: Dict[str, int] = {"pending": 0, "done": 0, "failed": 0}
    if agenda is None:
        return counts
    for item in _iter_agenda_items(agenda):
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        if status in counts:
            counts[status] += 1
    return counts


def _normalize_state(state: Any) -> str:
    if state is None:
        return _DEFAULT_STATE
    text = str(state).strip()
    return text if text else _DEFAULT_STATE


def _normalize_heartbeat(heartbeat_ts: Any) -> Optional[str]:
    if heartbeat_ts is None:
        return None
    text = str(heartbeat_ts).strip()
    return text if text else None


def _resolve_base_dir(base_dir: Optional[Union[str, Path]]) -> Path:
    if base_dir is None:
        return Path.cwd()
    return Path(base_dir)


def collect_metrics(
    base_dir: Optional[Union[str, Path]] = None,
) -> Dict[str, Any]:
    """Zberi metrike stanja daemona in agende.

    Vrne dict s ključi ``daemon`` (``state``, ``heartbeat_ts``),
    ``agenda`` (``pending``, ``done``, ``failed``), ``healthy`` in
    (če je heartbeat parsable) ``heartbeat_age_s``.

    ``healthy`` = daemon v normalnem obratovalnem stanju (npr. ``idle``,
    ``running_task``) IN heartbeat svež (ne starejši od ~5 min). Nezdrav =
    ``shutdown``/``degraded`` ali zastapljen heartbeat (zataknjen/padel daemon).
    Ob manjkajočih/poškodovanih virih ne pade — vrne privzete vrednosti
    in ključ ``error`` z opisom težave.

    Args:
        base_dir: Korenski imenik, v katerem se išče ``.rob_ai/``.
            Če ni podan, se uporabi trenutni delovni imenik.

    Returns:
        Dict z metrikami stanja sistema.
    """
    root = _resolve_base_dir(base_dir)
    rob_ai = root / ".rob_ai"

    daemon_raw = _read_json(rob_ai / "daemon.json")
    agenda_raw = _read_agenda_json(rob_ai / "agenda.json")

    errors: list[str] = []
    if daemon_raw is None:
        errors.append("daemon.json missing or invalid")
    if agenda_raw is None:
        errors.append("agenda.json missing or invalid")

    daemon = daemon_raw or {}
    agenda = agenda_raw or {}

    state = _normalize_state(daemon.get("state"))
    heartbeat_ts = _normalize_heartbeat(daemon.get("heartbeat_ts"))
    counts = _count_statuses(agenda)

    age = _heartbeat_age(heartbeat_ts)
    healthy = state in _HEALTHY_STATES and age is not None and age < _HEARTBEAT_FRESH_SECONDS

    result: Dict[str, Any] = {
        "daemon": {"state": state, "heartbeat_ts": heartbeat_ts},
        "agenda": counts,
        "healthy": healthy,
    }
    if age is not None:
        result["heartbeat_age_s"] = round(age, 1)
    if errors:
        result["error"] = "; ".join(errors)
    return result


def summary(base_dir: Optional[Union[str, Path]] = None) -> str:
    """Kratek, determinističen tekstovni povzetek stanja sistema.

    ``None`` se nikoli ne pojavi v izpisu — nadomesti ga ``"unknown"``.

    Args:
        base_dir: Korenski imenik, v katerem se išče ``.rob_ai/``.

    Returns:
        Enovrstični povzetek, npr.
        ``Daemon: running (heartbeat 2025-01-01T00:00:00Z) — agenda:
        3 pending, 12 done, 1 failed.``
    """
    metrics = collect_metrics(base_dir)
    daemon = metrics["daemon"]
    agenda = metrics["agenda"]
    state = daemon["state"]
    heartbeat = daemon["heartbeat_ts"] or _DEFAULT_STATE
    # Človeško berljiv heartbeat (HH:MM:SS), če je parsable epoch; sicer surov.
    hb_display = heartbeat
    if metrics.get("heartbeat_age_s") is not None:
        try:
            hb_display = time.strftime("%H:%M:%S", time.localtime(float(heartbeat)))
        except (TypeError, ValueError, OSError):
            pass
    health = "zdrav" if metrics.get("healthy") else "ni zdrav"
    return (
        f"Daemon: {state} ({health}, heartbeat {hb_display}) — agenda: "
        f"{agenda['pending']} pending, {agenda['done']} done, "
        f"{agenda['failed']} failed."
    )