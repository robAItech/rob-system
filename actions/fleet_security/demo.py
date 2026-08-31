"""fleet_security — produktni demo: CELOTNA zgodba platforme (Phase 1+2+3).

Varen fleet → incident (3 vektorji) → detekcija (6 dimenzij) → vpliv na
posture/CRA → odziv (remediacija + prompt hardening). Determinističen,
offline, ponovljiv. Uporabi SVOJO demo DB + demo audit/escalations — realno
stanje se NE dotika.

Uporaba:
    python -m actions.fleet_security.demo [--db PATH] [--out demo_report.md] [--no-color]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import audit as _audit  # noqa: E402
from core import quality as _quality  # noqa: E402
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
    Baseline,
    FirmwareInfo,
    HostInfo,
    ModelInfo,
    NetworkObservation,
    OSInfo,
    TelemetrySample,
)
from actions.fleet_security.store import FleetSecurityStore  # noqa: E402

#: Determinističen čas zgodbe (fiksno za ponovljivost).
NOW = 1_700_000_000

SHA_A = "a" * 64
SHA_B = "b" * 64

#: Baseline za role "worker" — VARNA (fixed) firmware/model verzije.
BASELINE = Baseline(
    role="worker",
    os_name="linux",
    os_version="5.15.2",     # fixed verzija (ni v CVE feedu)
    os_kernel="5.15.2",
    firmware={"motor-controller": "1.1.1", "bms-firmware": "2.2.0", "vision-fw": "1.0.0"},
    model_name="vision-model",
    model_sha256=[SHA_A],
    required_config_keys={"log_level": "info"},
    secure_default_checks={"allow_anonymous": True, "password": ""},
    heartbeat_max_age_seconds=600,
)


def _color(text: str, code: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


# ------------------------------------------------------------------ #
#  Demo store + roboti
# ------------------------------------------------------------------ #
def _demo_store(db_path: Path) -> FleetSecurityStore:
    """Sveža demo DB + preusmeritev audit/escalations na demo poti."""
    stem = db_path.stem
    # Počisti VSE demo artefakte (DB + audit/escalations) → ponovljiv demo.
    for p in list(db_path.parent.glob(f"{stem}*")):
        p.unlink(missing_ok=True)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    _audit.AUDIT_FILE = db_path.parent / f"{stem}.audit.jsonl"
    _quality.ESCALATIONS_FILE = db_path.parent / f"{stem}.escalations.json"
    _quality.QUALITY_REGISTRY = db_path.parent / f"{stem}.quality_registry.json"
    _quality.REENABLE_GRACE_FILE = db_path.parent / f"{stem}.reenable_grace.json"
    # Inline default baseline za settings.fleet_role ne sme ustvariti
    # missing_device → demo uporabi role "worker" za vse robote.
    settings.fleet_role = "worker"
    return FleetSecurityStore(db_path)


def _robot(
    device_id: str,
    *,
    motor: str = "1.1.1",
    bms: str = "2.2.0",
    vision_fw: str = "1.0.0",
    model_version: str = "1.0",
    model_sha: str = SHA_A,
    config: dict | None = None,
) -> HostInfo:
    return HostInfo(
        device_id=device_id,
        hostname=f"{device_id}.fleet.local",
        role="worker",
        os=OSInfo(name="linux", version="5.15.2", kernel="5.15.2"),
        firmware=[
            FirmwareInfo(component="motor-controller", version=motor),
            FirmwareInfo(component="bms-firmware", version=bms),
            FirmwareInfo(component="vision-fw", version=vision_fw),
        ],
        model=ModelInfo(
            name="vision-model", version=model_version, provider="oem", sha256=model_sha
        ),
        config=config if config is not None else {"log_level": "info"},
        source="demo",
        collected_at=NOW,
    )


def _seed_telemetry(store: FleetSecurityStore, device_id: str, values: list[float]) -> None:
    """Telemetry vzorce cpu_pct (monotoni ts, da z-score anomalija deluje)."""
    for i, v in enumerate(values):
        monitor.ingest_telemetry(
            store,
            TelemetrySample(
                device_id=device_id, ts=NOW + 100 + i, source="demo",
                metrics={"cpu_pct": v, "mem_pct": 40.0},
            ),
            now=NOW + 100 + i,
        )


# ------------------------------------------------------------------ #
#  Prikaz
# ------------------------------------------------------------------ #
class Demo:
    def __init__(self, color: bool):
        self.color = color
        self.md: list[str] = []

    def section(self, title: str) -> None:
        print()
        print(_color(f"=== {title} ===", "1;36", self.color))
        self.md.append(f"## {title}")
        self.md.append("")

    def line(self, text: str, color: str = "") -> None:
        print(_color(text, color, self.color) if color else text)
        self.md.append(text)

    def raw(self, text: str) -> None:
        print(text)
        self.md.append(text)

    def scores(self, store: FleetSecurityStore) -> None:
        for device in store.list_devices():
            score = store.latest_score(device.device_id)
            if score:
                color = "1;32" if score.score >= 90 else ("1;33" if score.score >= 60 else "1;31")
                self.line(
                    f"  {device.device_id:<12} score {score.score:>3}  grade {score.grade}",
                    color,
                )

    def findings(self, store: FleetSecurityStore) -> None:
        findings = store.list_open_findings()
        if not findings:
            self.line("  (ni odprtih najdb)", "1;32")
            return
        for f in sorted(findings, key=lambda x: (x.severity, x.device_id)):
            color = {"critical": "1;31", "high": "1;33"}.get(f.severity, "")
            self.line(f"  [{f.severity.upper():<8}] {f.device_id}  {f.category}: {f.detail[:90]}", color)

    def cra(self, store: FleetSecurityStore) -> None:
        data = compliance.generate_report_json(store, now=NOW)
        for req in data["requirements"]:
            mark = {"compliant": "✓", "non_compliant": "✗", "partial": "~", "not_applicable": "·"}.get(req["status"], "?")
            self.line(f"  {req['requirement_id']} {mark} {req['status']:<14} {req['title']}")


# ------------------------------------------------------------------ #
#  Glavna zgodba
# ------------------------------------------------------------------ #
def run(db_path: Path, out_path: Path, color: bool) -> int:
    store = _demo_store(db_path)
    demo = Demo(color)

    print(_color("┌────────────────────────────────────────────────────────────┐", "1;36", color))
    print(_color("│  ROBOT FLEET SECURITY — Autonomous AI Red Team & Defense   │", "1;36", color))
    print(_color("│  Platforma: inventar · posture · CRA · monitor · red team  │", "1;36", color))
    print(_color("└────────────────────────────────────────────────────────────┘", "1;36", color))
    demo.md.append("# Robot Fleet Security — Produktni demo")
    demo.md.append("")
    demo.md.append("_Determinističen demo (Phase 1+2+3), ponovljiv — vsa detekcija na istem findings toku._")
    demo.md.append("")

    # ══════════════════════════════════════════════════════════════════
    demo.section("1 · Varen fleet (baseline)")
    demo.line("Trije roboti se vpnejo v inventar z VARNIM stanjem (os, firmware, model, config).")
    store.upsert_baseline(BASELINE)
    for dev in ("rob-wh-01", "rob-dl-01", "rob-hu-01"):
        discovery.ingest_hostinfo(store, _robot(dev), now=NOW)

    posture.run_assessment(store, now=NOW)
    supplychain.run_supplychain_pass(store, now=NOW)      # model v1 → baseline provenance
    threatintel.run_threatintel_pass(store, now=NOW)      # ni znanih CVE
    redteam.run_red_team(
        store, "rob-hu-01", redteam.MockBrainTarget(secure=True),
        system_prompt="You are a safe humanoid robot.", now=NOW,
    )

    demo.line("Posture vseh treh:", "1;32")
    demo.scores(store)
    demo.line("CRA zahteve:", "1;32")
    demo.cra(store)

    # ══════════════════════════════════════════════════════════════════
    demo.section("2 · Incident — 3 različni napadi")
    demo.line("Nasprotnik izkoristi tri različne vektorje:")

    demo.line("▸ rob-wh-01 — firmware drift na ranljivo verzijo + insecure config + zamenjan model")
    discovery.ingest_hostinfo(
        store,
        _robot("rob-wh-01", motor="1.0.1", config={"allow_anonymous": True}),
        now=NOW + 100,
    )
    discovery.ingest_hostinfo(
        store,
        _robot("rob-wh-01", motor="1.0.1", model_version="2.0", model_sha=SHA_B,
               config={"allow_anonymous": True}),
        now=NOW + 200,
    )

    demo.line("▸ rob-dl-01 — telemetry CPU skok (97%) + egress na neznano C2 destinacijo")
    _seed_telemetry(store, "rob-dl-01", [28, 29, 30, 31, 32, 29, 30, 28, 31, 97.0])
    monitor.ingest_network_observation(
        store,
        NetworkObservation(device_id="rob-dl-01", ts=NOW + 300,
                           dst_host="10.66.66.66", dst_ip="10.66.66.66",
                           dst_port=4444, proto="tcp"),
        now=NOW + 300,
    )

    demo.line("▸ rob-hu-01 — prompt-injection napadi na action-decider ('možgani')")
    redteam.run_red_team(
        store, "rob-hu-01", redteam.MockBrainTarget(secure=False),
        system_prompt="You are a safe humanoid robot.", now=NOW + 400,
    )

    # ══════════════════════════════════════════════════════════════════
    demo.section("3 · Detekcija — 6 dimenzij, isti findings tok")
    demo.line("Vsi pasivni/preverjalni pass-i tečejo → najdbe v istem toku:")

    # Monitor / supply chain / threat intel najprej, POSTURE assess NAZADNJE —
    # da score odraža VSE odprte najdbe (assess šteje open findings po upsertu).
    monitor.run_monitor_pass(store, now=NOW + 500, allowlist="")
    supplychain.run_supplychain_pass(store, now=NOW + 500)
    threatintel.run_threatintel_pass(store, now=NOW + 500)
    posture.run_assessment(store, now=NOW + 500)

    demo.line("Odprte najdbe:")
    demo.findings(store)

    # ══════════════════════════════════════════════════════════════════
    demo.section("4 · Vpliv — posture pade, CRA non-compliant, eskalacije")
    demo.line("Posture po incidentu (prej 100/A vs. zdaj):")
    demo.scores(store)
    demo.line("CRA zahteve po incidentu:", "1;31")
    demo.cra(store)
    demo.line("Eskalacije (operator feed):")
    for e in _quality.open_escalations():
        demo.line(f"  ⚠ {e['project']}: {e['reason']} ({e['detail']})", "1;31")

    # ══════════════════════════════════════════════════════════════════
    demo.section("5 · Odziv — remediacija + hardening")
    demo.line("rob-wh-01 → config remediacijski PR (dry-run diff):")
    wh_result = remediation.open_remediation_pr(
        store, "rob-wh-01", kind="config", dry_run=True, now=NOW + 600
    )
    for ln in (wh_result.diff or "").splitlines():
        demo.raw(f"  {ln}")
    if wh_result.status == "diff_generated":
        demo.line("  → PR pripravljen (human-in-the-loop, nikoli auto-merge)", "1;32")

    demo.line("rob-hu-01 → hardened system prompt (dry-run diff):")
    hardened, harden_diff = redteam.harden_system_prompt(
        "You are a safe humanoid robot."
    )
    for ln in harden_diff.splitlines()[:6]:
        demo.raw(f"  {ln}")
    demo.line("  …", "")
    demo.line("  → hardened prompt pripravljen za remediacijski PR", "1;32")

    # ══════════════════════════════════════════════════════════════════
    demo.section("Zaključek")
    demo.line(
        "Platforma od vpisa naprave do odkrivanja 6 vrst tveganj (prompt-injection, "
        "firmware drift, insecure config, model supply-chain, telemetry anomalija, "
        "C2 egress, znane CVE) — in pripravi remediacijske PR-je. Vse pasivno, "
        "v simulaciji, z EU CRA skladnostnim poročilom."
    )

    # ── Demo report (Markdown) ────────────────────────────────────────
    demo.md.append("---")
    demo.md.append("_Robot Fleet Security · produktni demo · deterministično ponovljiv_")
    out_path.write_text("\n".join(demo.md) + "\n", encoding="utf-8")
    print()
    print(_color(f"✓ Demo report → {out_path}", "1;32", color))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fleet-security-demo",
        description="Produktni demo — celotna zgodba robot fleet security platforme.",
    )
    parser.add_argument("--db", default=".rob_ai/fleet_security_demo.db")
    parser.add_argument("--out", default="demo_report.md")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args(argv)
    return run(Path(args.db), Path(args.out), color=not args.no_color)


if __name__ == "__main__":
    raise SystemExit(main())
