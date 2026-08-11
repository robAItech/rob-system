import pytest
from pathlib import Path

def test_all_six_repos_present():
    repos_dir = Path("repos")
    required_repos = ["gbrain", "loopx", "gstack", "gbrain-evals", "hermes-agent", "graphify"]
    for repo in required_repos:
        repo_path = repos_dir / repo
        assert repo_path.exists(), f"Repozitorij {repo} ne obstaja v repos/"

def test_core_bridges_exist():
    core_dir = Path("core")
    bridges = ["gbrain_bridge.py", "graphify_bridge.py", "gstack_bridge.py", "hermes_bridge.py", "loopx_bridge.py", "orchestrator.py"]
    for bridge in bridges:
        assert (core_dir / bridge).exists(), f"Most {bridge} ne obstaja v core/"

def test_editable_packages_importable():
    # Preverjanje uvoza vseh 6 modulov
    import gbrain
    import loopx
    import gstack
    import gbrain_evals
    import hermes_agent

    try:
        import graphifyy
    except ImportError:
        import graphify

    assert gbrain is not None
    assert loopx is not None
    assert gstack is not None
    assert gbrain_evals is not None
    assert hermes_agent is not None
