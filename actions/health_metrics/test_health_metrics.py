"""Pytest test suite za actions/health_metrics.

Pokriva normalne in robne pogoje modula:
- uspešno branje daemon.json + agenda.json,
- manjkajoč daemon.json / agenda.json,
- poškodovan JSON,
- štetje statusov (tudi neznani statusi / gol seznam nalog),
- izračun ``healthy``,
- format ``summary()`` (brez ``None`` v izpisu),
- strogo validacijo pydantic shem.
"""

import json

import pytest

from health_metrics import collect_metrics, summary

try:
    # Ko je actions/ na sys.path (paket health_metrics).
    from health_metrics.schemas import AgendaCounts, DaemonState, HealthMetrics
except ImportError:  # pragma: no cover — odvisno od sys.path konfiguracije
    # Ko je actions/health_metrics/ neposredno na sys.path.
    from schemas import AgendaCounts, DaemonState, HealthMetrics


def _write_json(tmp_path, name, payload):
    """Zapiši JSON datoteko v ``.rob_ai/`` pod ``tmp_path``."""
    rob_ai = tmp_path / ".rob_ai"
    rob_ai.mkdir(exist_ok=True)
    path = rob_ai / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_collect_metrics_happy_path(tmp_path):
    """Uspešno branje obeh datotek vrne pričakovane metrike."""
    _write_json(
        tmp_path,
        "daemon.json",
        {"state": "running", "heartbeat_ts": "2025-01-01T00:00:00Z"},
    )
    _write_json(
        tmp_path,
        "agenda.json",
        {
            "items": [
                {"id": 1, "status": "pending"},
                {"id": 2, "status": "done"},
                {"id": 3, "status": "done"},
                {"id": 4, "status": "failed"},
            ]
        },
    )

    metrics = collect_metrics(tmp_path)

    assert metrics["daemon"] == {
        "state": "running",
        "heartbeat_ts": "2025-01-01T00:00:00Z",
    }
    assert metrics["agenda"] == {"pending": 1, "done": 2, "failed": 1}
    assert metrics["healthy"] is True
    assert "error" not in metrics


def test_collect_metrics_missing_daemon(tmp_path):
    """Manjkajoč daemon.json → privzet state, healthy False, error ključ."""
    _write_json(tmp_path, "agenda.json", {"tasks": [{"status": "pending"}]})

    metrics = collect_metrics(tmp_path)

    assert metrics["daemon"] == {"state": "unknown", "heartbeat_ts": None}
    assert metrics["healthy"] is False
    assert "daemon.json missing or invalid" in metrics["error"]


def test_collect_metrics_missing_agenda(tmp_path):
    """Manjkajoč agenda.json → prazni števci, error ključ."""
    _write_json(tmp_path, "daemon.json", {"state": "stopped", "heartbeat_ts": None})

    metrics = collect_metrics(tmp_path)

    assert metrics["agenda"] == {"pending": 0, "done": 0, "failed": 0}
    assert "agenda.json missing or invalid" in metrics["error"]


def test_collect_metrics_invalid_json(tmp_path):
    """Poškodovan JSON v obeh datotekah → defaults + error, brez izjeme."""
    rob_ai = tmp_path / ".rob_ai"
    rob_ai.mkdir(exist_ok=True)
    (rob_ai / "daemon.json").write_text("{broken json", encoding="utf-8")
    (rob_ai / "agenda.json").write_text(":::not json:::", encoding="utf-8")

    metrics = collect_metrics(tmp_path)

    assert metrics["daemon"]["state"] == "unknown"
    assert metrics["agenda"] == {"pending": 0, "done": 0, "failed": 0}
    assert "daemon.json missing or invalid" in metrics["error"]
    assert "agenda.json missing or invalid" in metrics["error"]


def test_collect_metrics_unknown_statuses_ignored(tmp_path):
    """Neznani statusi se ne štejejo v pending/done/failed."""
    _write_json(tmp_path, "daemon.json", {"state": "running", "heartbeat_ts": "t0"})
    _write_json(
        tmp_path,
        "agenda.json",
        {
            "entries": [
                {"status": "pending"},
                {"status": "weird"},
                {"status": "done"},
                {"status": "failed"},
                {"status": "pending"},
                {"status": None},
                {"no_status": True},
            ]
        },
    )

    metrics = collect_metrics(tmp_path)

    assert metrics["agenda"] == {"pending": 2, "done": 1, "failed": 1}


def test_collect_metrics_agenda_raw_list(tmp_path):
    """agenda.json kot gol seznam nalog je podprt in se prešteje."""
    _write_json(tmp_path, "daemon.json", {"state": "running", "heartbeat_ts": "hb"})
    _write_json(
        tmp_path,
        "agenda.json",
        [{"status": "pending"}, {"status": "failed"}],
    )

    metrics = collect_metrics(tmp_path)

    assert metrics["agenda"] == {"pending": 1, "done": 0, "failed": 1}
    assert "error" not in metrics


def test_healthy_requires_heartbeat(tmp_path):
    """State running brez heartbeata → healthy False."""
    _write_json(tmp_path, "daemon.json", {"state": "running", "heartbeat_ts": None})
    _write_json(tmp_path, "agenda.json", {"items": []})

    metrics = collect_metrics(tmp_path)

    assert metrics["daemon"]["state"] == "running"
    assert metrics["daemon"]["heartbeat_ts"] is None
    assert metrics["healthy"] is False


def test_summary_format(tmp_path):
    """Summary je determinističen in vsebuje stanje, heartbeat in števce."""
    _write_json(
        tmp_path,
        "daemon.json",
        {"state": "running", "heartbeat_ts": "2025-01-01T00:00:00Z"},
    )
    items = [{"status": "pending"}] * 3 + [{"status": "done"}] * 12 + [
        {"status": "failed"}
    ]
    _write_json(tmp_path, "agenda.json", {"items": items})

    text = summary(tmp_path)

    assert "Daemon: running" in text
    assert "heartbeat 2025-01-01T00:00:00Z" in text
    assert "3 pending, 12 done, 1 failed" in text
    assert "None" not in text


def test_summary_unknown_when_no_files(tmp_path):
    """Brez datotek → 'unknown' v izpisu, nikoli 'None'."""
    text = summary(tmp_path)

    assert "unknown" in text
    assert "None" not in text
    assert "0 pending, 0 done, 0 failed" in text


def test_schemas_strict_validation():
    """Pydantic sheme veljajo za veljavne vnose in zavrnejo neveljavne."""
    daemon = DaemonState(state="running", heartbeat_ts="2025-01-01T00:00:00Z")
    assert daemon.state == "running"
    assert daemon.heartbeat_ts == "2025-01-01T00:00:00Z"

    counts = AgendaCounts(pending=1, done=2, failed=0)
    assert counts.pending == 1

    metrics_model = HealthMetrics(daemon=daemon, agenda=counts, healthy=True)
    assert metrics_model.healthy is True

    with pytest.raises(ValueError):
        DaemonState(state="   ")  # blank state ni dovoljen
    with pytest.raises(ValueError):
        AgendaCounts(pending=-1)  # negativni števci niso dovoljeni
