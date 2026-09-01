"""fleet_security — OEM embed SDK (re-export).

**Kanonični vir je paket ``sdk/fleet_security_sdk``** (installable, stdlib only).
Ta modul je tanek re-export za demo (`sdk_demo.py`) in obstoječe teste
(`test_sdk.py`) — ena resnica, ni podvojenega koda.

OEM integracija:
    from fleet_security_sdk import FleetSecurityClient
"""

from fleet_security_sdk import (  # noqa: F401
    FleetSecurityClient,
    fingerprint,
    report_hostinfo,
    report_network,
    report_model,
    report_telemetry,
)
from fleet_security_sdk.client import _post  # noqa: F401 — zasebno, za test backward-compat

__all__ = [
    "FleetSecurityClient",
    "fingerprint",
    "report_hostinfo",
    "report_telemetry",
    "report_network",
    "report_model",
]
