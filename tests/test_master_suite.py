import pytest
import sqlite3
import subprocess
import sys
from pathlib import Path
from core.gbrain_bridge import GBrainBridge
from core.graphify_bridge import GraphifyBridge
from core.gstack_bridge import GSTACKArchitectBridge
from core.hermes_bridge import HermesBuilderBridge
from core.llm_client import DeepSeekLLMClient

def test_full_repos_integrity():
    required = ["gbrain", "loopx", "gstack", "gbrain-evals", "hermes-agent", "graphify"]
    for r in required:
        path = Path(f"repos/{r}")
        assert path.exists(), f"Repozitorij repos/{r} ne obstaja"
        assert (path / "pyproject.toml").exists(), f"Repozitorij repos/{r} nima pyproject.toml"

def test_bridges_and_llm_instantiation():
    gbrain = GBrainBridge()
    task_id = gbrain.record_task("master_test", "Unit testing LLM integration", "VERIFIED GREEN", "", "pass")
    assert task_id > 0

    llm = DeepSeekLLMClient()
    extracted = llm.extract_code_block("```python\nx = 1\n```")
    assert extracted == "x = 1"

    hermes = HermesBuilderBridge("master_test")
    hermes.write_initial_stubs_if_missing()
    assert Path("actions/master_test/schemas.py").exists()

def test_all_actions_pytest_coverage():
    actions_dir = Path("actions")
    # Ground-filtriraj mape: preskoči skrite run-time mape (npr. `.pytest_cache`),
    # Python meta-mape (`__pycache__`) in posebne (`master_test`). Navadne
    # runtime artefakte (pytest_cache/__pycache__) master suite USTVARI sam na
    # actions/ ob teku — če bi jih iteriral, bi poganjal pytest na prazni mapi
    # (exit code 5 "no tests collected") in padel. Zato so izključene.
    def _is_valid_module(d) -> bool:
        if not d.is_dir():
            return False
        if d.name.startswith(".") or d.name.startswith("__"):
            return False
        if d.name == "master_test":
            return False
        return True

    actions = [d for d in actions_dir.iterdir() if _is_valid_module(d)]

    # Zberemo napake vseh modulov, da en padec ne prekine obdelave ostalih.
    failures = []
    for act in actions:
        env = {"PYTHONPATH": "."}
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", str(act)],
            capture_output=True,
            text=True,
            env=dict(subprocess.os.environ, **env)
        )
        if res.returncode != 0:
            failures.append(f"actions/{act.name}:\n{res.stdout}\n{res.stderr}")

    if failures:
        raise AssertionError(
            "Oviralo: naslednji moduli niso opravili Pytest verifikacije:\n\n"
            + "\n\n".join(failures)
        )
