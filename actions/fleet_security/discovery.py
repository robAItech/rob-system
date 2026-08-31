"""fleet_security — pasivno zbiranje, ingest in heartbeat preverjanje.

**Pasivno-prvi (CEO trdo pravilo):** nobenega aktivnega skeniranja, probe-ov,
port/ping sweepov. Naprava SAMA sporoči svoj state (HostInfo) prek HTTP ingest
ali status datotek. Local collector uporablja samo stdlib branje (platform,
socket, uuid, lokalne datoteke) — nikoli omrežnih klicev v smeri naprav.

Vzorec odpornosti na manjkajoče/poškodovane vire: actions/health_metrics.
"""

from __future__ import annotations

import json
import os
import platform
import socket
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit  # noqa: E402
from core.config import settings  # noqa: E402
from actions.fleet_security.schemas import (  # noqa: E402
    FirmwareInfo,
    HostInfo,
    OSInfo,
    PostureFinding,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402


def _now() -> int:
    return int(time.time())


# ------------------------------------------------------------------ #
#  Local fingerprint helper-ji (module-level → testi monkeypatch-ajo)
# ------------------------------------------------------------------ #
def _node_uuid_hex() -> str:
    """Stabilen 12-hex identifikator iz MAC (uuid.getnode)."""
    return format(uuid.getnode() & 0xFFFFFFFFFFFF, "012x")


def _system_name() -> str:
    return platform.system().lower()


def _system_version() -> str:
    return platform.version()[:120]


def _kernel() -> str:
    return platform.release()[:120]


def _hostname() -> str:
    return socket.gethostname()


def _read_os_release(root: Path) -> dict:
    """Parse /etc/os-release (Linux); {} na Windows/manjkajoči datoteki."""
    path = Path(root) / "etc" / "os-release"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            out[key.strip()] = val.strip().strip('"')
    except OSError:
        return {}
    return out


def _read_firmware_manifest(root: Path) -> list[dict]:
    """Device-reported firmware (.rob_ai/fleet_security_firmware.json)."""
    path = Path(root) / ".rob_ai" / "fleet_security_firmware.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


def _read_device_config(root: Path) -> dict:
    """Device-reported host config (.rob_ai/fleet_security_hostconfig.json)."""
    path = Path(root) / ".rob_ai" / "fleet_security_hostconfig.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


# ------------------------------------------------------------------ #
#  Local collector
# ------------------------------------------------------------------ #
def collect_local_hostinfo(
    device_id: str | None = None,
    now: int | None = None,
    root: Path | None = None,
) -> HostInfo:
    """Pasiven fingerprint TEGA hosta (samo stdlib). Dogfood: ta repo/mašina.

    - device_id privzeto ``rob-<12-hex>`` (iz MAC),
    - role iz ``settings.fleet_role`` (master|worker|standalone),
    - os iz ``platform`` (Linux: /etc/os-release PRETTY_NAME bogati version),
    - config: python_version, cpu_count, arch, node_uuid,
    - firmware iz ``.rob_ai/fleet_security_firmware.json`` (če obstaja).
    """
    now = int(now) if now is not None else _now()
    root = Path(root) if root is not None else PROJECT_ROOT

    os_rel = _read_os_release(root)
    node = _node_uuid_hex()
    config: dict[str, Any] = _read_device_config(root)
    config.setdefault("python_version", platform.python_version())
    config.setdefault("cpu_count", os.cpu_count() or 0)
    config.setdefault("arch", platform.machine())
    config.setdefault("node_uuid", node)
    if os_rel.get("PRETTY_NAME"):
        config.setdefault("os_release_pretty", os_rel["PRETTY_NAME"])

    return HostInfo(
        device_id=device_id or f"rob-{node}",
        hostname=_hostname(),
        role=settings.fleet_role,
        os=OSInfo(
            name=_system_name(),
            version=os_rel.get("PRETTY_NAME") or _system_version(),
            kernel=_kernel(),
        ),
        firmware=[FirmwareInfo(**f) for f in _read_firmware_manifest(root)],
        config=config,
        source="local-collector",
        collected_at=now,
    )


# ------------------------------------------------------------------ #
#  Ingest + heartbeat
# ------------------------------------------------------------------ #
def ingest_hostinfo(
    store: FleetSecurityStore, payload: HostInfo, now: int | None = None
) -> HostInfo:
    """Persistira napravo + zapiše audit event (zero silent failures)."""
    now = int(now) if now is not None else _now()
    device = store.upsert_device(payload, now=now)
    try:
        audit.record(
            event="fleet-security-ingest",
            project=device.device_id,
            status="ok",
            detail=f"hostinfo via {payload.source}",
        )
    except Exception:
        pass  # audit nikoli ne sme podreti ingest-a
    return device


def check_heartbeats(
    store: FleetSecurityStore,
    now: int | None = None,
    max_age: int | None = None,
) -> list[PostureFinding]:
    """Pasiven heartbeat preverjanje (template: health_metrics freshness).

    - naprava, ki ni sporočila svežega heartbeat-a (last_seen starejši od
      limita) → ``stale_heartbeat`` (high),
    - role z baseline-om, a brez naprave → ``missing_device`` (critical).

    Limit: ekspliciten ``max_age`` (testi) prevlada; sicer per-role iz
    baseline-a, fallback ``settings.fs_heartbeat_max_age_seconds``.
    """
    now = int(now) if now is not None else _now()
    findings: list[PostureFinding] = []
    default_max_age = (
        settings.fs_heartbeat_max_age_seconds if max_age is None else int(max_age)
    )
    baselines = {b.role: b for b in store.list_baselines()}
    devices = store.list_devices()

    for device in devices:
        age = now - device.last_seen_ts
        limit = default_max_age
        bl = baselines.get(device.role)
        if max_age is None and bl is not None:
            limit = bl.heartbeat_max_age_seconds
        if age > limit:
            findings.append(
                PostureFinding(
                    device_id=device.device_id,
                    category="stale_heartbeat",
                    severity="high",
                    detail=f"last_seen {age}s ago (max {limit}s)",
                    detected_at=now,
                )
            )

    reported_roles = {d.role for d in devices}
    for role in baselines:
        if role not in reported_roles:
            findings.append(
                PostureFinding(
                    device_id=f"{role}:missing",
                    category="missing_device",
                    severity="critical",
                    detail=f"no device reporting role '{role}' (baseline present)",
                    detected_at=now,
                )
            )
    return findings
