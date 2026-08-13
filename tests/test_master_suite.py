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
    actions = [d for d in actions_dir.iterdir() if d.is_dir() and not d.name.startswith("__")]

    for act in actions:
        if act.name == "master_test":
            continue
        env = {"PYTHONPATH": "."}
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "-v", str(act)],
            capture_output=True,
            text=True,
            env=dict(subprocess.os.environ, **env)
        )
        assert res.returncode == 0, f"Modul v actions/{act.name} ni opravil Pytest verifikacije:\n{res.stdout}\n{res.stderr}"
