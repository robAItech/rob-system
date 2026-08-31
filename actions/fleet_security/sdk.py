"""fleet_security — OEM embed SDK (Phase 2, Skin B).

Tiny, **dependency-free** client (samo stdlib), ki ga roboti/OEM firmware
vgradijo. Ni pydantic, ni ``core.*`` importov — datoteko lahko OEM skopira
ven kot samostojni modul.

Pošilja na jedro (FastAPI):
- hostinfo  → ``POST {server}/api/fleet-security/devices/ingest``
- telemetry → ``POST {server}/api/fleet-security/monitor/telemetry``
- omrežne opazke → ``POST {server}/api/fleet-security/monitor/network``

Transport: ``urllib.request`` (stdlib). **Nikoli ne pade** — ob napaki vrne
``{"ok": False, "error": "..."}`` (za embedded odpornost).
"""

from __future__ import annotations

import json
import platform
import socket
import ssl
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Optional


def _now() -> int:
    return int(time.time())


def _base(url: str) -> str:
    return (url or "").rstrip("/")


# ------------------------------------------------------------------ #
#  Fingerprint — točno strict HostInfo obliko (extra="forbid")
# ------------------------------------------------------------------ #
def fingerprint(
    device_id: Optional[str] = None,
    role: str = "standalone",
    hostname: Optional[str] = None,
    os_name: Optional[str] = None,
    os_version: Optional[str] = None,
    os_kernel: Optional[str] = None,
    firmware: Optional[dict] = None,
    model: Optional[dict] = None,
    config: Optional[dict] = None,
    source: str = "sdk",
    collected_at: Optional[int] = None,
) -> dict:
    """Zgradi HostInfo-shaped dict (strict schema: nobenih extra ključev).

    Defaults: device_id ``rob-<12hex>`` iz MAC, hostname, os iz ``platform``,
    firmware iz dict {component: version}, model None, config {}.
    """
    node = uuid.getnode() & 0xFFFFFFFFFFFF
    host = hostname if hostname is not None else socket.gethostname()
    sys_name = os_name if os_name is not None else (platform.system() or "unknown")
    fw = [
        {"component": str(c), "version": str(v)}
        for c, v in (firmware or {}).items()
    ]
    return {
        "device_id": device_id or f"rob-{format(node, '012x')}",
        "hostname": host,
        "role": role,
        "os": {
            "name": sys_name.lower(),
            "version": os_version if os_version is not None else platform.release(),
            "kernel": os_kernel if os_kernel is not None else platform.version(),
        },
        "firmware": fw,
        "model": model,
        "config": config or {},
        "source": source,
        "collected_at": collected_at,
    }


# ------------------------------------------------------------------ #
#  Transport (stdlib; nikoli ne pade)
# ------------------------------------------------------------------ #
def _post(url: str, payload: dict, token: Optional[str] = None,
          timeout: float = 5.0) -> dict:
    """POST JSON na ``url``. Vrne ``{"ok": True, status, data}`` ali
    ``{"ok": False, "error": "..."}``. Ne dviguje izjem."""
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url, data=data, headers=headers, method="POST"
    )
    try:
        if url.startswith("https://"):
            # Self-signed-tolerant TLS kontekst (embedded/edge naprave).
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read()
                status = resp.status
        else:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
                status = resp.status
        try:
            data_out = json.loads(body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            data_out = body.decode("utf-8", errors="replace")
        return {"ok": True, "status": status, "data": data_out}
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:  # noqa: BLE001 — embedded: ne smemo pasti
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


# ------------------------------------------------------------------ #
#  Report API
# ------------------------------------------------------------------ #
def report_hostinfo(
    server_url: str,
    token: Optional[str] = None,
    hostinfo: Optional[dict] = None,
    timeout: float = 5.0,
    **fp_kwargs: Any,
) -> dict:
    """Pošlji hostinfo (privzeto ``fingerprint(**fp_kwargs)``) na ingest."""
    payload = hostinfo if hostinfo is not None else fingerprint(**fp_kwargs)
    return _post(
        f"{_base(server_url)}/api/fleet-security/devices/ingest",
        payload,
        token=token,
        timeout=timeout,
    )


def report_telemetry(
    server_url: str,
    device_id: str,
    metrics: dict,
    ts: Optional[int] = None,
    source: str = "sdk",
    token: Optional[str] = None,
    timeout: float = 5.0,
) -> dict:
    """Pošlji telemetry vzorec naprave."""
    payload = {
        "device_id": device_id,
        "ts": int(ts) if ts is not None else _now(),
        "source": source,
        "metrics": metrics,
    }
    return _post(
        f"{_base(server_url)}/api/fleet-security/monitor/telemetry",
        payload,
        token=token,
        timeout=timeout,
    )


def report_network(
    server_url: str,
    device_id: str,
    dst_host: Optional[str] = None,
    dst_ip: Optional[str] = None,
    dst_port: Optional[int] = None,
    proto: Optional[str] = None,
    ts: Optional[int] = None,
    token: Optional[str] = None,
    timeout: float = 5.0,
) -> dict:
    """Pošlji omrežno opazko (dst tuple) naprave."""
    payload = {
        "device_id": device_id,
        "ts": int(ts) if ts is not None else _now(),
        "dst_host": dst_host,
        "dst_ip": dst_ip,
        "dst_port": dst_port,
        "proto": proto,
    }
    return _post(
        f"{_base(server_url)}/api/fleet-security/monitor/network",
        payload,
        token=token,
        timeout=timeout,
    )
