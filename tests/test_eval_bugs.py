"""Testi za P0 — real eval bugfix (core/eval_bugs.py). Brez LLM/Docker.

Najpomembnejši invariant: inject_bug → pytest RDEČ; inverz (new→old) → ZELEN.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from shutil import copytree, ignore_patterns
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.eval_bugs import BUG_CASES, EvalBugError, cleanup, inject_bug
from evaluate_autonomy import EVAL_CASES, AutonomyEval, validate_case

ROOT = Path(__file__).resolve().parents[1]


def test_bug_cases_veljavni_in_pripeti():
    assert len(BUG_CASES) >= 4
    assert {c.get("type") for c in BUG_CASES} == {"bugfix"}
    for c in BUG_CASES:
        errs = validate_case(c)
        assert not errs, f"{c['name']}: {errs}"
        assert any(x["name"] == c["name"] for x in EVAL_CASES)


def test_bug_stringi_enolicni_v_source():
    for c in BUG_CASES:
        src = ROOT / "actions" / c["source_module"]
        for rel, old, _new in c["bug"]:
            text = (src / rel).read_text(encoding="utf-8")
            assert old in text, f"{c['name']}: {old!r} ni najden v {rel}"
            assert text.count(old) == 1, f"{c['name']}: {old!r} ni enoličen"


def _copy_source(c, root: Path) -> Path:
    """Kopiraj gold source v tmp actions/ (s paketom), da inject_bug dela izolirano."""
    src_root = root / "actions"
    src_root.mkdir(parents=True, exist_ok=True)
    (root / "actions" / "__init__.py").write_text("", encoding="utf-8")
    copytree(ROOT / "actions" / c["source_module"], src_root / c["source_module"],
             ignore=ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
             dirs_exist_ok=True)
    # Navzkrižne odvisnosti (npr. audit_trail → actions.event_bus) morajo biti v tmp.
    for py in (ROOT / "actions" / c["source_module"]).glob("*.py"):
        t = py.read_text(encoding="utf-8")
        for dep in re.findall(r"from actions\.([\w.]+) import", t):
            dep = dep.split(".")[0]
            if dep != c["source_module"]:
                dep_src = ROOT / "actions" / dep
                if dep_src.is_dir():
                    copytree(dep_src, src_root / dep,
                             ignore=ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
                             dirs_exist_ok=True)
    return src_root


def test_inject_bug_kopira_zamenja_in_preusmeri_uvoze(tmp_path):
    c = BUG_CASES[0]
    src_root = _copy_source(c, tmp_path)
    dst = inject_bug(c, dest_root=src_root)
    assert (dst / "currency_converter.py").exists()
    text = (dst / "currency_converter.py").read_text(encoding="utf-8")
    assert "actions." + c["name"] not in text          # currency: no package imports (no-op)
    assert (dst / ".evalbug.json").exists()
    # Import-rewrite: vsaj ena .py v event_bus kopiji vsebuje actions.<case_name>.
    event_case = next(c2 for c2 in BUG_CASES if c2["source_module"] == "event_bus")
    _copy_source(event_case, tmp_path)
    dst2 = inject_bug(event_case, dest_root=src_root)
    assert any("actions." + event_case["name"] in p.read_text(encoding="utf-8")
               for p in dst2.rglob("*.py"))
    cleanup(event_case, dest_root=src_root)


def test_inject_bug_missing_old_raises(tmp_path):
    c = BUG_CASES[0]
    src_root = _copy_source(c, tmp_path)
    bad = {"name": "fix_bad", "source_module": c["source_module"],
           "bug": [("currency_converter.py", "TA STRING NE OBSTAJA", "x")]}
    with pytest.raises(EvalBugError):
        inject_bug(bad, dest_root=src_root)
    assert not (src_root / "fix_bad").exists()


def _run_pytest(target_dir: Path, root: Path) -> int:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root)
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(target_dir)],
                       capture_output=True, env=env)
    return r.returncode


@pytest.mark.parametrize("idx", [0, 2, 3, 5])  # currency, event_bus, contract, audit
def test_bugfix_rdec_po_injekciji_zelen_po_restore(tmp_path, idx):
    c = BUG_CASES[idx]
    root = tmp_path / "root"
    src_root = _copy_source(c, root)
    dst = inject_bug(c, dest_root=src_root)
    assert _run_pytest(dst, root) != 0          # RDEČ (bug prisoten)
    for rel, old, new in c["bug"]:              # inverz → popravljeno
        p = dst / rel
        t = p.read_text(encoding="utf-8")
        assert new in t
        p.write_text(t.replace(new, old, 1), encoding="utf-8")
    assert _run_pytest(dst, root) == 0          # ZELEN (popravljeno)


def test_run_case_bugfix_mock_rsi(tmp_path, monkeypatch):
    c = BUG_CASES[0]
    ev = AutonomyEval([c], keep_artifacts=True)
    monkeypatch.setattr(ev, "_verify_bugfix_inline",
                        lambda name, case: {"checks_ok": 4, "checks_total": 4, "reason": "ok"})
    with mock.patch("core.orchestrator.RobAIOrchestrator.run", return_value=True):
        res = ev.run_case(c)
    assert res["rsi_ok"] is True
    assert res["checks_ok"] == 4


def test_run_case_guarded_ujame_inject_bug_izjemo(tmp_path, monkeypatch):
    c = BUG_CASES[0]
    ev = AutonomyEval([c])
    with mock.patch("evaluate_autonomy.inject_bug", side_effect=EvalBugError("old ni najden")):
        res = ev._run_case_guarded(c)
    assert res["rsi_ok"] is False
    assert "bug ni vnesen" in res["reason"]
