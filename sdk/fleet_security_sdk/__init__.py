"""fleet_security_sdk — OEM embed SDK (dependency-free, stdlib only).

Kanonični vir je ta paket (``sdk/fleet_security_sdk``). ``actions/
fleet_security/sdk.py`` je tanek re-export za demo/teste.

OEM integracija:
    from fleet_security_sdk import FleetSecurityClient

    client = FleetSecurityClient("http://robot-cloud:8000", token="...")
    client.report_hostinfo()                       # fingerprint tega robota
    client.report_telemetry({"cpu_pct": 42.0})     # telemetry
    client.report_network(dst_ip="10.0.0.9", dst_port=443, proto="tcp")
    client.report_model("vision-model", "2.0", sha256="...", pushed_by="factory-ci")
"""

from .client import (
    FleetSecurityClient,
    fingerprint,
    report_hostinfo,
    report_network,
    report_model,
    report_telemetry,
)

__version__ = "0.1.0"

__all__ = [
    "FleetSecurityClient",
    "fingerprint",
    "report_hostinfo",
    "report_telemetry",
    "report_network",
    "report_model",
]
