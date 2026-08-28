"""Pytest test suite za actions/secret_rotation.

Deterministično: injicirana fiktivna ura + fiksni generator vrednosti. Preveri
double-buffer prehod, scheduler (due), audit sled, revoke in FastAPI plast.
"""

from typing import List

import pytest
from fastapi.testclient import TestClient

from actions.secret_rotation.main import app, manager
from actions.secret_rotation.rotation import SecretRotationManager


class FakeClock:
    """Fiktivna ura za deterministične rotacije."""

    def __init__(self, start: float = 1_700_000_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class SequencedGenerator:
    """Generator, ki vrednosti izdaja po vrstnem redu (for i in range)."""

    def __init__(self, values: List[str]):
        self.values = list(values)
        self.index = 0

    def __call__(self) -> str:
        value = f"{self.values[self.index % len(self.values)]}"
        self.index += 1
        return value


@pytest.fixture(autouse=True)
def _fresh_manager():
    manager.secrets.clear()
    manager.audit.clear()
    yield


# ── Registracija ────────────────────────────────────────────────────────────
def test_register_creates_active_secret_with_rotation_schedule():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["sk-1"]))
    state = mgr.register_secret("db_pass", kind="db_password", rotation_interval_days=30)
    assert state.phase == "active"
    assert state.active_value == "sk-1"
    assert state.next_rotation_at == clock() + 30 * 86400.0
    assert len(mgr.audit) == 1


# ── Double buffer ───────────────────────────────────────────────────────────
def test_rotate_stages_without_touching_active():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["old", "new"]))
    mgr.register_secret("api_key", kind="api_key")
    state = mgr.rotate("api_key")

    assert state.staged_value == "new"      # pripravljena nova
    assert state.active_value == "old"      # stara še vedno aktivna (zero-downtime)
    assert state.phase == "staged"


def test_activate_promotes_staged_and_old_goes_passive():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["old", "new"]))
    mgr.register_secret("api_key", kind="api_key")
    mgr.rotate("api_key")
    state = mgr.activate("api_key")

    assert state.active_value == "new"
    assert state.passive_value == "old"     # rollback rezerva
    assert state.staged_value is None
    assert state.phase == "active"
    assert state.next_rotation_at > state.rotated_at


def test_activate_without_staged_is_noop():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["only"]))
    mgr.register_secret("api_key", kind="api_key")
    state = mgr.activate("api_key")
    assert state.active_value == "only"     # ni staged → nespremenjeno


# ── Scheduler (due) ─────────────────────────────────────────────────────────
def test_due_secrets_after_interval():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["a", "b"]))
    mgr.register_secret("api_key", kind="api_key", rotation_interval_days=30)
    assert mgr.due_secrets() == []          # ni še zapadlo

    clock.advance(30 * 86400.0)             # +30 dni
    due = mgr.due_secrets()
    assert [s.name for s in due] == ["api_key"]

    mgr.rotate("api_key")
    mgr.activate("api_key")                 # rotirano → nov next_rotation_at
    assert mgr.due_secrets() == []          # spet ni zapadlo


# ── Revoke (auto-revoke) ────────────────────────────────────────────────────
def test_revoke_marks_inactive_and_audits():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["s"]))
    mgr.register_secret("api_key", kind="api_key")
    assert mgr.revoke("api_key", reason="suspicious access") is True

    state = mgr.status_of("api_key")
    assert state.revoked is True
    assert state.active is False
    assert state.phase == "none"
    assert mgr.rotate("api_key") is None    # umaknjena → ni rotacije
    assert any(a.action == "revoke" for a in mgr.audit)


def test_revoke_missing_secret_returns_false():
    mgr = SecretRotationManager()
    assert mgr.revoke("missing", reason="x") is False


# ── Audit sled ──────────────────────────────────────────────────────────────
def test_audit_records_register_rotate_activate():
    clock = FakeClock()
    mgr = SecretRotationManager(clock=clock, value_generator=SequencedGenerator(["a", "b", "c"]))
    mgr.register_secret("api_key", kind="api_key")
    mgr.rotate("api_key")
    mgr.activate("api_key")
    actions = [a.action for a in mgr.audit]
    assert actions == ["register", "rotate", "activate"]


# ── FastAPI plast ───────────────────────────────────────────────────────────
def test_api_register_status_due_revoke():
    client = TestClient(app)
    r = client.post("/secrets", json={"name": "db_pass", "kind": "db_password", "rotation_interval_days": 30})
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "active"
    assert body["active_value_masked"].endswith("…")  # vrednost maskirana
    assert "db_pass" not in body["active_value_masked"][:4]  # ne razkrijemo polne

    st = client.get("/status")
    assert st.status_code == 200
    assert st.json()[0]["name"] == "db_pass"

    due = client.get("/due")
    assert due.json() == []  # ni zapadlo (ura realna, interval 30 dni)

    rv = client.post("/revoke", json={"name": "db_pass", "reason": "test"})
    assert rv.status_code == 200
    assert rv.json()["revoked"] is True

    h = client.get("/health")
    assert h.json()["status"] == "UP"
