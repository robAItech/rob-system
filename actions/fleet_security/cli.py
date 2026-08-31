"""fleet_security — CLI vmesnik (pasivno jedro).

Uporaba:
    python -m actions.fleet_security.cli ingest [--device-id ID]
    python -m actions.fleet_security.cli assess
    python -m actions.fleet_security.cli report [--format markdown|json]
                                                 [--no-redact] [--out PATH]
    python -m actions.fleet_security.cli remediate ID [--kind config|network_policy]
    python -m actions.fleet_security.cli pr ID [--kind config|network_policy]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings  # noqa: E402
from actions.fleet_security import (  # noqa: E402
    compliance,
    discovery,
    monitor,
    posture,
    remediation,
)
from actions.fleet_security.schemas import NetworkObservation, TelemetrySample  # noqa: E402
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402


def _store() -> FleetSecurityStore:
    return FleetSecurityStore(settings.fs_db_path)


def _emit(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _cmd_ingest(args) -> int:
    hostinfo = discovery.collect_local_hostinfo(device_id=args.device_id)
    device = discovery.ingest_hostinfo(_store(), hostinfo)
    _emit(device.model_dump())
    return 0


def _cmd_assess(args) -> int:
    _emit(posture.run_assessment(_store()))
    return 0


def _cmd_report(args) -> int:
    store = _store()
    if args.format == "json":
        data = compliance.generate_report_json(store, redact=not args.no_redact)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    else:
        text = compliance.generate_report(store, redact=not args.no_redact)
    if args.out:
        out = Path(args.out)
        out.write_text(text, encoding="utf-8")
        print(f"report -> {out}")
    else:
        print(text)
    return 0


def _cmd_remediate(args) -> int:
    result = remediation.open_remediation_pr(
        _store(), args.device_id, kind=args.kind, dry_run=not args.pr
    )
    _emit(result.model_dump())
    return 0


def _cmd_monitor(args) -> int:
    """Dispatch monitor leaf-ukazov (telemetry|network|run|summary)."""
    if args.monitor_cmd == "telemetry":
        metrics: dict[str, float] = {}
        for kv in args.metrics:
            if "=" not in kv:
                print(f"napaka: pričakoval key=value, dobil {kv!r}", file=sys.stderr)
                return 2
            key, _, val = kv.partition("=")
            try:
                metrics[key] = float(val)
            except ValueError:
                print(f"napaka: {val!r} ni številka za {key}", file=sys.stderr)
                return 2
        sample = TelemetrySample(device_id=args.device_id, source="cli", metrics=metrics)
        _emit(monitor.ingest_telemetry(_store(), sample))
        return 0
    if args.monitor_cmd == "network":
        obs = NetworkObservation(
            device_id=args.device_id,
            dst_host=args.dst_host,
            dst_ip=args.dst_ip,
            dst_port=args.dst_port,
            proto=args.proto,
        )
        _emit(monitor.ingest_network_observation(_store(), obs))
        return 0
    if args.monitor_cmd == "run":
        _emit(monitor.run_monitor_pass(_store()))
        return 0
    if args.monitor_cmd == "summary":
        _emit(monitor.monitor_summary(_store()))
        return 0
    print(f"napaka: neznan monitor ukaz {args.monitor_cmd!r}", file=sys.stderr)
    return 2


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="fleet-security",
        description="Robot fleet security — pasivno jedro (inventar + posture + CRA + remediacija).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_ingest = sub.add_parser("ingest", help="fingerprint tega hosta + shrani v inventar")
    p_ingest.add_argument("--device-id", default=None, help="ekspliciten device_id")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_assess = sub.add_parser("assess", help="poženi cel pasiven assess pass")
    p_assess.set_defaults(func=_cmd_assess)

    p_report = sub.add_parser("report", help="CRA skladnostni report")
    p_report.add_argument("--format", choices=["markdown", "json"], default="markdown")
    p_report.add_argument("--no-redact", action="store_true", help="izklopi PII redakcijo")
    p_report.add_argument("--out", default=None, help="shrani v datoteko")
    p_report.set_defaults(func=_cmd_report)

    for cmd, dry in (("remediate", True), ("pr", False)):
        p = sub.add_parser(cmd, help=f"{cmd}: odpri remediacijski PR")
        p.add_argument("device_id")
        p.add_argument("--kind", choices=["config", "network_policy"], default="config")
        p.set_defaults(func=_cmd_remediate, pr=not dry)

    p_monitor = sub.add_parser("monitor", help="Phase 2 — operator monitor (pasivno)")
    m_sub = p_monitor.add_subparsers(dest="monitor_cmd", required=True)
    p_tel = m_sub.add_parser("telemetry", help="pošlji telemetry vzorec")
    p_tel.add_argument("device_id")
    p_tel.add_argument("metrics", nargs="+", help="key=value key=value ...")
    p_tel.set_defaults(func=_cmd_monitor)
    p_net = m_sub.add_parser("network", help="pošlji omrežno opazko")
    p_net.add_argument("device_id")
    p_net.add_argument("dst_host")
    p_net.add_argument("dst_ip", nargs="?")
    p_net.add_argument("dst_port", nargs="?", type=int)
    p_net.add_argument("proto", nargs="?")
    p_net.set_defaults(func=_cmd_monitor)
    m_sub.add_parser("run", help="poženi monitor pass (detekcija + prune)").set_defaults(
        func=_cmd_monitor
    )
    m_sub.add_parser("summary", help="monitor povzetek").set_defaults(func=_cmd_monitor)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
