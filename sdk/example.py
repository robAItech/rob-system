"""fleet_security_sdk — OEM embed dogfood demo.

Uporaba:
    python sdk/example.py http://127.0.0.1:8000 [--token X] [--device-id rob-demo-1]

Prijavi hostinfo + telemetry + omrežno opazko + model provenance proti jedru.
"""

from __future__ import annotations

import argparse
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])  # sdk/ na path → fleet_security_sdk

from fleet_security_sdk import FleetSecurityClient  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fleet-security-sdk-example")
    parser.add_argument("server_url", help="npr. http://127.0.0.1:8000")
    parser.add_argument("--token", default=None)
    parser.add_argument("--device-id", default=None)
    args = parser.parse_args(argv)

    client = FleetSecurityClient(args.server_url, token=args.token, device_id=args.device_id)

    print("== hostinfo ==")
    print(client.report_hostinfo())
    print("== telemetry ==")
    print(client.report_telemetry({"cpu_pct": 30.0, "mem_pct": 45.0}))
    print("== network ==")
    print(client.report_network(dst_host="10.0.0.9", dst_ip="10.0.0.9", dst_port=443, proto="tcp"))
    print("== model provenance ==")
    print(client.report_model("vision-model", "2.0", sha256="a" * 64, provider="oem", pushed_by="factory-ci"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
