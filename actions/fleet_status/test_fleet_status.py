"""Pytest testi za modul fleet_status (≥5 testov, vsi zeleni)."""

import importlib
import json
from pathlib import Path

import pytest


def _load(module_name: str):
    """Importira modul; deluje tako s korenom kot z `actions.` paketom."""
    try:
        return importlib.import_module(module_name)
    except ImportError:
        return importlib.import_module(f"actions.{module_name}")


fs = _load("fleet_status")
schemas = _load("fleet_status.schemas")


def _write(tmp_path: Path, daemon: dict, workers: dict) -> Path:
    # Konvencija A: base_dir = repo koren → datoteke v base_dir/.rob_ai/.
    rob_ai = tmp_path / ".rob_ai"
    rob_ai.mkdir(exist_ok=True)
    (rob_ai / "daemon.json").write_text(json.dumps(daemon), encoding="utf-8")
    (rob_ai / "fleet_workers.json").write_text(
        json.dumps(workers), encoding="utf-8"
    )
    return tmp_path


def test_collect_status_returns_daemon_state_and_heartbeat(tmp_path):
    data_dir = _write(
        tmp_path,
        {"state": "running", "heartbeat_ts": 1234.5},
        {"w1": {"last_seen": 100.0}},
    )
    status = fs.collect_status(data_dir)
    assert status["daemon"]["state"] == "running"
    assert status["daemon"]["heartbeat_ts"] == 1234.5


def test_collect_status_returns_workers_last_seen(tmp_path):
    data_dir = _write(
        tmp_path,
        {"state": "idle", "heartbeat_ts": 1.0},
        {
            "alpha": {"last_seen": 42.0},
            "beta": {"last_seen": 43.0},
        },
    )
    status = fs.collect_status(data_dir)
    assert status["workers"] == {"alpha": 42.0, "beta": 43.0}


def test_collect_status_accepts_plain_numeric_worker_values(tmp_path):
    data_dir = _write(
        tmp_path,
        {"state": "stopped", "heartbeat_ts": 0.0},
        {"gamma": 7.0},
    )
    status = fs.collect_status(data_dir)
    assert status["workers"] == {"gamma": 7.0}


def test_collect_status_raises_file_not_found_when_files_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        fs.collect_status(tmp_path / "does-not-exist")


def test_collect_status_raises_value_error_on_corrupted_json(tmp_path):
    rob_ai = tmp_path / ".rob_ai"
    rob_ai.mkdir(exist_ok=True)
    (rob_ai / "daemon.json").write_text("{not json", encoding="utf-8")
    (rob_ai / "fleet_workers.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        fs.collect_status(tmp_path)


def test_summary_contains_daemon_state_and_heartbeat(tmp_path):
    data_dir = _write(
        tmp_path,
        {"state": "running", "heartbeat_ts": 5.0},
        {},
    )
    text = fs.summary(data_dir)
    assert "running" in text
    assert "5.0" in text


def test_summary_lists_workers_with_last_seen(tmp_path):
    data_dir = _write(
        tmp_path,
        {"state": "idle", "heartbeat_ts": 1.0},
        {"w1": {"last_seen": 99.0}},
    )
    text = fs.summary(data_dir)
    assert "w1" in text
    assert "99.0" in text


def test_summary_handles_empty_workers(tmp_path):
    data_dir = _write(
        tmp_path,
        {"state": "stopped", "heartbeat_ts": 1.0},
        {},
    )
    assert "stopped" in fs.summary(data_dir)


def test_daemon_status_schema_rejects_empty_state():
    with pytest.raises(ValueError):
        schemas.DaemonStatus(state="   ")


def test_fleet_status_schema_rejects_non_numeric_last_seen():
    with pytest.raises(ValueError):
        schemas.FleetStatus(
            daemon={"state": "running", "heartbeat_ts": 1.0},
            workers={"w1": "not-a-number"},
        )


def test_api_endpoint_returns_200_json(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("httpx")
    from starlette.testclient import TestClient

    main_mod = _load("fleet_status.main")
    data_dir = _write(
        tmp_path,
        {"state": "running", "heartbeat_ts": 1.5},
        {"w1": {"last_seen": 2.0}},
    )
    client = TestClient(main_mod.router)
    resp = client.get("/api/fleet/status", params={"data_dir": str(data_dir)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["daemon"]["state"] == "running"
    assert body["workers"] == {"w1": 2.0}
