"""Jedrna logika modula fleet_status.

Modul bere operativno stanje flote Rob AI Studio z diska:
  - `.rob_ai/daemon.json`        -> state + heartbeat_ts daemona
  - `.rob_ai/fleet_workers.json` -> {ime_workerja: {"last_seen": ts}}

`collect_status()` vrne strojno berljiv dict, `summary()` pa kratek
človeško berljiv povzetek. Manjkajoče datoteke dvignejo
`FileNotFoundError`, poškodovane/neveljavne pa `ValueError`
(ValidationError pydantic shem), ki jih FastAPI plast pretvori v
ustrezen JSON odziv.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .schemas import DaemonStatus, FleetStatus

DEFAULT_DATA_DIR = Path(".rob_ai")

PathLike = Union[str, Path]


def _resolve_dir(data_dir: Optional[PathLike]) -> Path:
    return Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing fleet status file: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Corrupted JSON in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"Expected a JSON object in {path}, got {type(raw).__name__}")
    return raw


def collect_status(base_dir: Optional[PathLike] = None) -> Dict[str, Any]:
    """Prebere stanje daemona in workerjev ter vrne enoten dict.

    `base_dir` = KOREN repozitorija (sistem konvencija, kot health_metrics);
    bere `base_dir/.rob_ai/daemon.json` in `base_dir/.rob_ai/fleet_workers.json`.

    Oblika izhoda::

        {
            "daemon": {"state": "running", "heartbeat_ts": 1234.5},
            "workers": {"worker-1": 1234.0},
        }
    """
    root = Path(base_dir) if base_dir else Path(".")
    rob_ai = root / ".rob_ai"
    daemon_raw = _read_json(rob_ai / "daemon.json")
    workers_raw = _read_json(rob_ai / "fleet_workers.json")

    daemon = DaemonStatus.model_validate(daemon_raw)
    status = FleetStatus.model_validate({"daemon": daemon, "workers": workers_raw})
    return status.model_dump()


def summary(base_dir: Optional[PathLike] = None) -> str:
    """Vrne kratek človeško berljiv povzetek stanja flote."""
    status = collect_status(base_dir)
    daemon = status["daemon"]
    heartbeat = daemon["heartbeat_ts"]
    lines = [
        "Daemon: {state}{hb}".format(
            state=daemon["state"],
            hb=f" (heartbeat: {heartbeat})" if heartbeat is not None else "",
        )
    ]
    workers = status["workers"]
    if not workers:
        lines.append("Workers: none")
    else:
        for name in sorted(workers):
            last_seen = workers[name]
            if last_seen is None:
                lines.append(f"Worker {name}: never seen")
            else:
                lines.append(f"Worker {name}: last seen {last_seen}")
    return "\n".join(lines)