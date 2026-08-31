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
from actions.fleet_security import compliance, discovery, posture, remediation  # noqa: E402
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

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
