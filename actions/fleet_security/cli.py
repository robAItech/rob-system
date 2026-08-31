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
    redteam,
    remediation,
    supplychain,
    threatintel,
)
from actions.fleet_security.schemas import (  # noqa: E402
    ModelInfo,
    NetworkObservation,
    TelemetrySample,
)
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


# ── Phase 3 — red team / supply chain / threat intel ────────────────────
def _cmd_redteam(args) -> int:
    if args.redteam_cmd == "run":
        target = redteam.MockBrainTarget(secure=(args.mock == "secure"))
        selected = None
        if args.payloads:
            ids = [i.strip() for i in args.payloads.split(",") if i.strip()]
            by_id = {p["id"]: p for p in redteam.PAYLOAD_LIBRARY}
            selected = [by_id[i] for i in ids if i in by_id]
        _emit(redteam.run_red_team(
            _store(), args.robot_id, target, args.system_prompt, payloads=selected
        ))
        return 0
    if args.redteam_cmd == "runs":
        _emit({"runs": _store().list_redteam_runs(args.device_id)})
        return 0
    if args.redteam_cmd == "harden":
        if args.pr:
            result = redteam.open_prompt_hardening_pr(
                _store(), args.robot_id, args.system_prompt, dry_run=False
            )
            _emit(result.model_dump())
        else:
            hardened, diff = redteam.harden_system_prompt(args.system_prompt)
            _emit({"hardened": hardened, "diff": diff})
        return 0
    print(f"napaka: neznan redteam ukaz {args.redteam_cmd!r}", file=sys.stderr)
    return 2


def _cmd_supplychain(args) -> int:
    if args.sc_cmd == "record":
        model = ModelInfo(
            name=args.model_name, version=args.model_version,
            provider=args.provider or "", sha256=args.sha256 or "",
        )
        row_id = supplychain.record_model(
            _store(), args.device_id, model, pushed_by=args.pushed_by
        )
        _emit({"id": row_id, "device_id": args.device_id})
        return 0
    if args.sc_cmd == "check":
        _emit(supplychain.run_supplychain_pass(_store()))
        return 0
    if args.sc_cmd == "history":
        _emit({"history": _store().list_model_history(args.device_id)})
        return 0
    print(f"napaka: neznan supplychain ukaz {args.sc_cmd!r}", file=sys.stderr)
    return 2


def _cmd_threatintel(args) -> int:
    if args.ti_cmd == "check":
        feed = threatintel.load_feed(args.feed) if args.feed else None
        _emit(threatintel.run_threatintel_pass(_store(), feed=feed))
        return 0
    if args.ti_cmd == "feed":
        feed = threatintel.load_feed(args.feed) if args.feed else None
        _emit({"advisories": [a.model_dump() for a in (feed or [])]})
        return 0
    print(f"napaka: neznan threatintel ukaz {args.ti_cmd!r}", file=sys.stderr)
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

    # Phase 3 — red team (SIMULACIJA samo).
    p_rt = sub.add_parser("redteam", help="Phase 3 — embodied-AI red team (sim)")
    rt_sub = p_rt.add_subparsers(dest="redteam_cmd", required=True)
    p_run = rt_sub.add_parser("run", help="poženi red-team pass na simuliranem možganu")
    p_run.add_argument("robot_id")
    p_run.add_argument("--system-prompt", default="")
    p_run.add_argument("--payloads", default=None, help="vejica-ločeni payload id-i")
    p_run.add_argument("--mock", choices=["secure", "naive"], default="naive")
    p_run.set_defaults(func=_cmd_redteam)
    p_runs = rt_sub.add_parser("runs", help="zgodovina run-ov")
    p_runs.add_argument("--device-id", default=None)
    p_runs.set_defaults(func=_cmd_redteam)
    p_har = rt_sub.add_parser("harden", help="prompt hardening (+ opcijski PR)")
    p_har.add_argument("robot_id")
    p_har.add_argument("--system-prompt", required=True)
    p_har.add_argument("--pr", action="store_true", help="odpri remediacijski PR")
    p_har.set_defaults(func=_cmd_redteam)

    # Phase 3 — supply chain.
    p_sc = sub.add_parser("supplychain", help="Phase 3 — model supply-chain verifikacija")
    sc_sub = p_sc.add_subparsers(dest="sc_cmd", required=True)
    p_rec = sc_sub.add_parser("record", help="eksplicitno zabeleži model v provenance")
    p_rec.add_argument("device_id")
    p_rec.add_argument("--model-name", required=True)
    p_rec.add_argument("--model-version", default="")
    p_rec.add_argument("--sha256", default="")
    p_rec.add_argument("--provider", default="")
    p_rec.add_argument("--pushed-by", default=None)
    p_rec.set_defaults(func=_cmd_supplychain)
    sc_sub.add_parser("check", help="poženi supply-chain pass").set_defaults(
        func=_cmd_supplychain
    )
    p_hist = sc_sub.add_parser("history", help="provenance history")
    p_hist.add_argument("--device-id", default=None)
    p_hist.set_defaults(func=_cmd_supplychain)

    # Phase 3 — threat intel.
    p_ti = sub.add_parser("threatintel", help="Phase 3 — threat intel feed")
    ti_sub = p_ti.add_subparsers(dest="ti_cmd", required=True)
    p_chk = ti_sub.add_parser("check", help="poženi threat-intel pass")
    p_chk.add_argument("--feed", default=None, help="override poti feed JSON")
    p_chk.set_defaults(func=_cmd_threatintel)
    p_fd = ti_sub.add_parser("feed", help="prikaži feed advisory-e")
    p_fd.add_argument("--feed", default=None)
    p_fd.set_defaults(func=_cmd_threatintel)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
