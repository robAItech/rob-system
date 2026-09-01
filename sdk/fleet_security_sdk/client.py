"""fleet_security_sdk.client — kanonična OEM embed SDK logika.

Tiny, **dependency-free** client (samo stdlib), ki ga roboti/OEM firmware
vgradijo. Ni pydantic, ni ``core.*`` importov — paket se lahko ``pip install``-a
ali skopira kot samostojni modul.

Pošilja na jedro (FastAPI):
- hostinfo  → ``POST {server}/api/fleet-security/devices/ingest``
- telemetry → ``POST {server}/api/fleet-security/monitor/telemetry``
- omrežne opazke → ``POST {server}/api/fleet-security/monitor/network``
- model provenance → ``POST {server}/api/fleet-security/supplychain/record``

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
        # Runtime (FastAPI :8788) uporablja X-API-Key; dashboard sprejme tudi
        # Bearer. Oba pošljeva → SDK dela proti obema površinama.
        headers["X-API-Key"] = token
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
#  Module-level Report API (backward-compat; server_url prvi)
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


def report_model(
    server_url: str,
    device_id: str,
    model_name: str,
    model_version: str,
    sha256: str = "",
    provider: str = "",
    pushed_by: Optional[str] = None,
    repo_url: Optional[str] = None,
    token: Optional[str] = None,
    timeout: float = 5.0,
) -> dict:
    """Prijavi model provenance (Phase 3 supply-chain) na ``/supplychain/record``.

    Payload: ``{device_id, model:{name,version,provider,sha256}, pushed_by, repo_url}``.
    """
    payload = {
        "device_id": device_id,
        "model": {
            "name": model_name,
            "version": model_version,
            "provider": provider,
            "sha256": sha256,
        },
        "pushed_by": pushed_by,
        "repo_url": repo_url,
    }
    return _post(
        f"{_base(server_url)}/api/fleet-security/supplychain/record",
        payload,
        token=token,
        timeout=timeout,
    )


# ------------------------------------------------------------------ #
#  FleetSecurityClient — objektni vmesnik za OEM integracijo
# ------------------------------------------------------------------ #
class FleetSecurityClient:
    """Enostaven OEM client: server_url + token + timeout + device_id.

    ``device_id`` je opcijski — če ni podan, se izpelje iz ``fingerprint``.
    Vse metode so **ne-blocking-safe** (urllib) in nikoli ne dvignejo izjeme.
    """

    def __init__(
        self,
        server_url: str,
        token: Optional[str] = None,
        timeout: float = 5.0,
        device_id: Optional[str] = None,
    ):
        self.server_url = _base(server_url)
        self.token = token
        self.timeout = timeout
        self._device_id = device_id

    def _did(self) -> str:
        return self._device_id or fingerprint()["device_id"]

    def report_hostinfo(self, hostinfo: Optional[dict] = None, **fp_kwargs: Any) -> dict:
        """Prijavi hostinfo (privzeto fingerprint)."""
        payload = hostinfo if hostinfo is not None else fingerprint(**fp_kwargs)
        return _post(
            f"{self.server_url}/api/fleet-security/devices/ingest",
            payload,
            token=self.token,
            timeout=self.timeout,
        )

    def report_telemetry(
        self, metrics: dict, device_id: Optional[str] = None, ts: Optional[int] = None
    ) -> dict:
        """Prijavi telemetry vzorec naprave."""
        return report_telemetry(
            self.server_url,
            device_id or self._did(),
            metrics,
            ts=ts,
            token=self.token,
            timeout=self.timeout,
        )

    def report_network(
        self,
        dst_host: Optional[str] = None,
        dst_ip: Optional[str] = None,
        dst_port: Optional[int] = None,
        proto: Optional[str] = None,
        device_id: Optional[str] = None,
        ts: Optional[int] = None,
    ) -> dict:
        """Prijavi omrežno opazko (dst tuple) naprave."""
        return report_network(
            self.server_url,
            device_id or self._did(),
            dst_host=dst_host,
            dst_ip=dst_ip,
            dst_port=dst_port,
            proto=proto,
            ts=ts,
            token=self.token,
            timeout=self.timeout,
        )

    def report_model(
        self,
        model_name: str,
        model_version: str,
        sha256: str = "",
        provider: str = "",
        pushed_by: Optional[str] = None,
        repo_url: Optional[str] = None,
        device_id: Optional[str] = None,
    ) -> dict:
        """Prijavi model provenance (supply-chain) za napravo."""
        return report_model(
            self.server_url,
            device_id or self._did(),
            model_name,
            model_version,
            sha256=sha256,
            provider=provider,
            pushed_by=pushed_by,
            repo_url=repo_url,
            token=self.token,
            timeout=self.timeout,
        )


__all__ = [
    "FleetSecurityClient",
    "fingerprint",
    "report_hostinfo",
    "report_telemetry",
    "report_network",
    "report_model",
]
