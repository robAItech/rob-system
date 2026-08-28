"""Pytest test suite za actions/api_version_manager.

Deterministično: weighted routing z injiciranim fiksnim ``rng``. Preveri SemVer
parsanje/primerjavo, registracijo, deprecation, BC-break detekcijo in FastAPI.
"""

from typing import List

import pytest
from fastapi.testclient import TestClient

from actions.api_version_manager.main import app, manager
from actions.api_version_manager.version_manager import SemVer, VersionManager


class FixedRng:
    """Rng, ki vedno vrne določeno vrednost → determinističen routing."""

    def __init__(self, value: float):
        self.value = value

    def __call__(self) -> float:
        return self.value


@pytest.fixture(autouse=True)
def _fresh_manager():
    manager.versions.clear()
    yield


# ── SemVer ──────────────────────────────────────────────────────────────────
def test_semver_parse_forms():
    assert SemVer.parse("1.2.3") == SemVer(1, 2, 3)
    assert SemVer.parse("v2.1.0") == SemVer(2, 1, 0)
    assert SemVer.parse("5") == SemVer(5, 0, 0)
    with pytest.raises(ValueError):
        SemVer.parse("abc")


def test_semver_ordering():
    assert SemVer(1, 9, 0) < SemVer(2, 0, 0)
    assert SemVer(2, 0, 0) == SemVer(2, 0, 0)
    assert SemVer(2, 0, 1) > SemVer(2, 0, 0)


def test_semver_compatibility():
    # Sprememba major → prelomna; minor/patch → kompatibilna.
    assert SemVer(1, 0, 0).is_compatible_with(SemVer(1, 5, 0)) is True
    assert SemVer(1, 0, 0).is_compatible_with(SemVer(2, 0, 0)) is False


def test_semver_to_tag():
    assert SemVer(3, 2, 1).to_tag() == "v3"


# ── Registracija + deprecation ──────────────────────────────────────────────
def test_register_and_list_sorted():
    mgr = VersionManager()
    mgr.register_version("v2", SemVer(2, 0, 0))
    mgr.register_version("v1", SemVer(1, 0, 0))
    tags = [v.tag for v in mgr.list_versions()]
    assert tags == ["v1", "v2"]


def test_deprecate_and_headers():
    mgr = VersionManager()
    mgr.register_version("v1", SemVer(1, 0, 0))
    assert mgr.deprecate("v1", notice="upgrade to v2", sunset="2027-01-01") is True
    assert mgr.deprecate("missing", notice="x") is False
    headers = mgr.deprecation_headers("v1")
    assert "Deprecation: true" in headers
    assert any(h.startswith("Sunset:") for h in headers)
    assert mgr.deprecation_headers("v2") == []  # nedeprecirana → brez headerjev


# ── Weighted routing ────────────────────────────────────────────────────────
def test_route_all_weight_to_v2():
    mgr = VersionManager(rng=FixedRng(0.99))
    mgr.register_version("v1", SemVer(1, 0, 0), weight=10)
    mgr.register_version("v2", SemVer(2, 0, 0), weight=90)
    tag, ver = mgr.route([("v1", 10), ("v2", 90)])
    assert tag == "v2"  # 99% → znotraj v2 (10..100)
    assert ver == SemVer(2, 0, 0)


def test_route_all_weight_to_v1():
    mgr = VersionManager(rng=FixedRng(0.01))
    mgr.register_version("v1", SemVer(1, 0, 0), weight=10)
    mgr.register_version("v2", SemVer(2, 0, 0), weight=90)
    tag, _ = mgr.route([("v1", 10), ("v2", 90)])
    assert tag == "v1"  # 1% → znotraj v1 (0..10)


def test_route_distribution_smoke():
    # Statistical smoke: pri 60/40 se pojavita obe veje v 1000 rollih.
    import random
    mgr = VersionManager(rng=random.random)
    mgr.register_version("v1", SemVer(1, 0, 0), weight=60)
    mgr.register_version("v2", SemVer(2, 0, 0), weight=40)
    picks: List[str] = [mgr.route([("v1", 60), ("v2", 40)])[0] for _ in range(1000)]
    assert "v1" in picks and "v2" in picks


def test_route_none_when_no_active():
    mgr = VersionManager()
    mgr.register_version("v1", SemVer(1, 0, 0), weight=0, active=False)
    assert mgr.route([("v1", 0)]) is None


# ── BC-break detekcija ──────────────────────────────────────────────────────
def test_additive_change_is_non_breaking():
    old_schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
    new_schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": "string"}},
        "required": ["id"],
    }
    is_breaking, changes = VersionManager.detect_breaking_change(old_schema, new_schema)
    assert is_breaking is False
    assert any("added" in c for c in changes)


def test_removed_required_is_breaking():
    old_schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
    new_schema = {"type": "object", "properties": {}}
    is_breaking, changes = VersionManager.detect_breaking_change(old_schema, new_schema)
    assert is_breaking is True
    assert any("'id'" in c for c in changes)


def test_type_change_is_breaking():
    old_schema = {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}
    new_schema = {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}
    is_breaking, changes = VersionManager.detect_breaking_change(old_schema, new_schema)
    assert is_breaking is True
    assert any("type changed" in c for c in changes)


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_register_route_bc_health():
    client = TestClient(app)
    r = client.post("/versions", json={
        "tag": "v1", "version": {"major": 1, "minor": 0, "patch": 0}, "weight": 100,
    })
    assert r.status_code == 200
    assert r.json()["version"] == "1.0.0"

    # Routing — v1 edina aktivna, teža 100 → vedno v1.
    r2 = client.post("/route", json={"versions": [{"tag": "v1", "weight": 100}]})
    assert r2.status_code == 200
    assert r2.json()["selected"] == "v1"

    # BC-break: dodajanje polja ni prelomno.
    r3 = client.post("/check-bc", json={
        "old_schema": {"properties": {"id": {"type": "integer"}}, "required": ["id"]},
        "new_schema": {"properties": {"id": {"type": "integer"}, "x": {"type": "string"}}, "required": ["id"]},
    })
    assert r3.status_code == 200
    assert r3.json()["is_breaking"] is False

    h = client.get("/health")
    assert h.json()["status"] == "UP"
