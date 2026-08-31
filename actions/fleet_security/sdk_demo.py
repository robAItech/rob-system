"""fleet_security — sdk_demo: OEM embed SDK dogfood proti živo server.

Uporaba:
    python -m actions.fleet_security.sdk_demo http://127.0.0.1:8000 [--token X]
                                              [--device-id rob-demo-1]

Pošlje: hostinfo (fingerprint), 3 telemetry vzorce, 2 omrežni opazki — in
izpiše vsak odgovor. Zahteva delujoč server (uvicorn main:app ali runtime).
"""

from __future__ import annotations

import argparse
import sys

from actions.fleet_security import sdk


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fleet-security-sdk-demo",
        description="OEM embed SDK dogfood — pošlji hostinfo/telemetry/network.",
    )
    parser.add_argument("server_url", help="npr. http://127.0.0.1:8000")
    parser.add_argument("--token", default=None)
    parser.add_argument("--device-id", default=None)
    args = parser.parse_args(argv)

    device_id = args.device_id or "rob-demo-1"
    print("== hostinfo ==")
    print(sdk.report_hostinfo(args.server_url, token=args.token,
                              hostinfo=sdk.fingerprint(device_id=device_id)))
    print("== telemetry (3 vzorci) ==")
    for i, cpu in enumerate((30.0, 31.0, 97.0)):
        print(sdk.report_telemetry(args.server_url, device_id,
                                   {"cpu_pct": cpu, "mem_pct": 45.0 + i},
                                   token=args.token))
    print("== network (2 opazki) ==")
    print(sdk.report_network(args.server_url, device_id,
                             dst_host="10.0.0.9", dst_ip="10.0.0.9",
                             dst_port=443, proto="tcp", token=args.token))
    print(sdk.report_network(args.server_url, device_id,
                             dst_host="10.0.0.9", dst_ip="10.0.0.9",
                             dst_port=53, proto="udp", token=args.token))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
