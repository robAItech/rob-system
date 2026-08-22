"""core/eval_bugs.py — P0: SWE-bench stil eval popravljanja bug-ov.

Vzemi REALEN obstoječi modul (zlata rešitev), vnesi determinističen bug,
RSI naj popravi da zlati testi spet zeleni. Neodvisna verifikacija:
pre-existing testi (test-locked) + functional checks (hard-code izhodi).

`inject_bug` OBDVEZNO preusmeri notranje uvoze (`actions.<source>` → `actions.<case>`),
sicer bi kopirani testi testirali GOLD modul (takoj zeleni → eval pokvarjen).
"""
from __future__ import annotations

import json
import shutil
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class EvalBugError(Exception):
    """Bug ni bil vnesen deterministično (string replace fragilnost)."""
    pass


# ── Contract sheme (module-level, za bugfix checks) ────────────────────────
C_CONSUMER = {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
              "required": ["id", "name"]}
C_PROVIDER_OK = {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"},
                  "extra": {"type": "string"}}, "required": ["id", "name"]}
C_PROVIDER_TYPEMISMATCH = {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "integer"}},
                           "required": ["id", "name"]}
C_PROVIDER_EXACT = {"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
                    "required": ["id", "name"]}
C_PROVIDER_MISSING = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id", "name"]}


# ── Stateful/async probe callables (target, mod) → (ok, total, reason) ─────
def _verify_event_bus_payload(bus, _mod) -> Tuple[int, int, str]:
    ok, total = 0, 2
    bus.publish("t", {"a": 1})
    msgs = bus.get_topic_messages("t")
    if len(msgs) == 1 and msgs[0]["payload"] == {"a": 1}:
        ok += 1
    if len(msgs) == 1 and msgs[0]["metadata"] == {}:
        ok += 1
    return ok, total, f"{ok}/{total} event-bus payload checks"


async def _verify_audit_hash(trail, mod) -> Tuple[int, int, str]:
    ok, total = 0, 2
    Create = mod.AuditRecordCreate
    await trail.record_event(Create(actor="admin", action="CREATE_USER", target="user_1"))
    await trail.record_event(Create(actor="user_1", action="LOGIN", target="auth_sys"))
    v = await trail.verify_chain()
    if v.is_valid is True and v.total_records == 2:
        ok += 1
    trail.chain[1].target = "tampered"          # vdor brez preračuna hasha
    v2 = await trail.verify_chain()
    if v2.is_valid is False and v2.broken_at_id == "evt_audit_2" and "Data tampered" in (v2.reason or ""):
        ok += 1
    return ok, total, f"{ok}/{total} audit chain checks"


# ── BUG_CASES ──────────────────────────────────────────────────────────────
BUG_CASES: List[Dict[str, Any]] = [
    {
        "name": "fix_currency_inverted_rate",
        "type": "bugfix", "mode": "single",
        "source_module": "currency_converter",
        "bug": [("currency_converter.py",
                 "    converted = amount_decimal * (rate_to / rate_from)",
                 "    converted = amount_decimal * (rate_from / rate_to)")],
        "function_key": "convert_currency",
        "total": 4,
        "directive": (
            "Popravi Python modul 'fix_currency_inverted_rate' v actions/fix_currency_inverted_rate/. "
            "To je obstoječi večdatotečni modul (klon currency_converter) z vneseno regresijo v funkciji "
            "convert_currency. Poišči in popravi regresijo tako, da bodo VSI obstoječi pytest testi 100% zeleni. "
            "Test datotek (test_*.py) NE spreminjaj (test-lock). Popravi le izvorno kodo."
        ),
        "checks": [
            (100, "USD", "EUR", Decimal("85.00")),
            (85, "EUR", "USD", Decimal("100.00")),
            (100, "USD", "JPY", Decimal("11000.00")),
            (100, "USD", "XYZ", "RAISE:UnsupportedCurrencyError"),
        ],
    },
    {
        "name": "fix_currency_jpy_rate",
        "type": "bugfix", "mode": "single",
        "source_module": "currency_converter",
        "bug": [("currency_converter.py", '"JPY": Decimal("110.0")', '"JPY": Decimal("100.0")')],
        "function_key": "convert_currency",
        "total": 4,
        "directive": (
            "Popravi Python modul 'fix_currency_jpy_rate' v actions/fix_currency_jpy_rate/. "
            "To je obstoječi večdatotečni modul (klon currency_converter) z vneseno regresijo v tečajih. "
            "Poišči in popravi regresijo tako, da bodo VSI obstoječi pytest testi 100% zeleni. "
            "Test datotek (test_*.py) NE spreminjaj (test-lock). Popravi le izvorno kodo."
        ),
        "checks": [
            (100, "USD", "JPY", Decimal("11000.00")),
            (100, "JPY", "USD", Decimal("0.91")),
            (100, "USD", "EUR", Decimal("85.00")),
            (100, "USD", "XYZ", "RAISE:UnsupportedCurrencyError"),
        ],
    },
    {
        "name": "fix_event_bus_payload",
        "type": "bugfix", "mode": "single",
        "source_module": "event_bus",
        "bug": [("event_bus.py", "            payload=payload,", "            payload={},")],
        "function_key": "EventBus",
        "total": 2,
        "verify": _verify_event_bus_payload,
        "directive": (
            "Popravi Python modul 'fix_event_bus_payload' v actions/fix_event_bus_payload/. "
            "To je obstoječi večdatotečni modul (klon event_bus) z vneseno regresijo v razredu EventBus. "
            "Poišči in popravi regresijo tako, da bodo VSI obstoječi pytest testi 100% zeleni. "
            "Test datotek (test_*.py) NE spreminjaj (test-lock). Popravi le izvorno kodo."
        ),
    },
    {
        "name": "fix_contract_type_check",
        "type": "bugfix", "mode": "single",
        "source_module": "contract_schema_engine",
        "bug": [("contracts.py",
                 "        if consumer_type != provider_type:",
                 "        if consumer_type == provider_type:")],
        "function_key": "ContractManager.verify_contract",
        "extract": lambda r: r[0],
        "total": 2,
        "directive": (
            "Popravi Python modul 'fix_contract_type_check' v actions/fix_contract_type_check/. "
            "To je obstoječi večdatotečni modul (klon contract_schema_engine) z vneseno regresijo v "
            "verifikaciji tipov. Poišči in popravi regresijo tako, da bodo VSI obstoječi pytest testi 100% zeleni. "
            "Test datotek (test_*.py) NE spreminjaj (test-lock). Popravi le izvorno kodo."
        ),
        "checks": [
            (C_CONSUMER, C_PROVIDER_OK, True),
            (C_CONSUMER, C_PROVIDER_TYPEMISMATCH, False),
        ],
    },
    {
        "name": "fix_contract_return_valid",
        "type": "bugfix", "mode": "single",
        "source_module": "contract_schema_engine",
        "bug": [("contracts.py",
                 "        return len(errors) == 0, errors, warnings",
                 "        return len(warnings) == 0, errors, warnings")],
        "function_key": "ContractManager.verify_contract",
        "extract": lambda r: r[0],
        "total": 3,
        "directive": (
            "Popravi Python modul 'fix_contract_return_valid' v actions/fix_contract_return_valid/. "
            "To je obstoječi večdatotečni modul (klon contract_schema_engine) z vneseno regresijo v "
            "vračanju veljavnosti. Poišči in popravi regresijo tako, da bodo VSI obstoječi pytest testi 100% zeleni. "
            "Test datotek (test_*.py) NE spreminjaj (test-lock). Popravi le izvorno kodo."
        ),
        "checks": [
            (C_CONSUMER, C_PROVIDER_EXACT, True),
            (C_CONSUMER, C_PROVIDER_OK, True),
            (C_CONSUMER, C_PROVIDER_MISSING, False),
        ],
    },
    {
        "name": "fix_audit_hash_formula",
        "type": "bugfix", "mode": "single",
        "source_module": "audit_trail",
        "bug": [("audit_trail.py",
                 'data = f"{prev_hash}|{timestamp}|{actor}|{action}|{target}|{payload_str}"',
                 'data = f"{prev_hash}|{timestamp}|{actor}|{action}|{payload_str}"')],
        "function_key": "AuditTrail",
        "total": 2,
        "verify": _verify_audit_hash,
        "directive": (
            "Popravi Python modul 'fix_audit_hash_formula' v actions/fix_audit_hash_formula/. "
            "To je obstoječi večdatotečni modul (klon audit_trail) z vneseno regresijo v hash formuli. "
            "Poišči in popravi regresijo tako, da bodo VSI obstoječi pytest testi 100% zeleni. "
            "Test datotek (test_*.py) NE spreminjaj (test-lock). Popravi le izvorno kodo."
        ),
    },
]


# ── Injekcija bug-ov ───────────────────────────────────────────────────────
def inject_bug(case: Dict, dest_root: Optional[Path] = None) -> Path:
    """Kopiraj gold modul → actions/<case_name>/, vnesi bug, preusmeri uvoze.

    Vrne target dir. RAISE ob nedeterminističnem vnosu (old ni enoličen).
    Marker `.evalbug.json` omogoča self-heal stale dir-ov ob ponovnem teku.
    """
    root = Path(dest_root) if dest_root else (ROOT / "actions")
    src, dst = root / case["source_module"], root / case["name"]
    marker = dst / ".evalbug.json"
    if dst.exists():
        if marker.exists():
            shutil.rmtree(dst)          # stale eval artefakt → samozdravljenje
        else:
            raise EvalBugError(f"target '{dst}' obstaja brez eval markerja — ne brišem")
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"))
    try:
        for rel, old, new in case["bug"]:
            p = dst / rel
            if not p.exists():
                raise EvalBugError(f"bug file ni v kopiji: {rel}")
            text = p.read_text(encoding="utf-8")
            if text.count(old) != 1:
                raise EvalBugError(f"bug string v '{rel}' ni enoličen/najden ({text.count(old)}×): {old!r}")
            p.write_text(text.replace(old, new, 1), encoding="utf-8")
        # OBDVEZNO: preusmeri notranje uvoze na KOPIJO (ne gold).
        for py in dst.rglob("*.py"):
            t = py.read_text(encoding="utf-8")
            if ("actions." + case["source_module"]) in t:
                py.write_text(t.replace("actions." + case["source_module"], "actions." + case["name"]),
                              encoding="utf-8")
        marker.write_text(json.dumps({"case": case["name"], "source_module": case["source_module"]}),
                          encoding="utf-8")
    except Exception:
        shutil.rmtree(dst, ignore_errors=True)
        raise
    return dst


def cleanup(case: Dict, dest_root: Optional[Path] = None) -> None:
    """Odstrani bugfix target dir (po izvedbi, razen --keep-artifacts)."""
    shutil.rmtree(Path(dest_root) if dest_root else (ROOT / "actions" / case["name"]), ignore_errors=True)


def check_bug_injectable(case: Dict) -> List[str]:
    """Dry-run pre-flight: old najden in enoličen v source datotekah (lovi drift)."""
    errs = []
    src = ROOT / "actions" / case["source_module"]
    if not src.is_dir():
        errs.append(f"source_module ne obstaja: {src}")
    for rel, old, _ in case.get("bug", []):
        p = src / rel
        if not p.exists():
            errs.append(f"bug file ni v source_module: {rel}")
        else:
            text = p.read_text(encoding="utf-8")
            if old not in text:
                errs.append(f"bug string ni najden v {rel}: {old!r}")
            elif text.count(old) != 1:
                errs.append(f"bug string ni enoličen v {rel}: {old!r}")
    return errs
