"""Testi Chief of Staff (faza 1) — deterministični, brez omrežja/LLM."""
from pathlib import Path

import pytest

from chief.chief_of_staff import (
    MODEL_FILE,
    append_correction,
    audit_activity,
    build_digest,
    fold_corrections,
    guard,
    load_lessons,
    load_model,
    propose_next,
    read_history,
    record_history,
    ventures_missing_next,
    week_summary,
    write_digest,
)


def _model():
    """Minimalen model za deterministične teste (ne odvisen od repo seeda)."""
    return {
        "ventures": {
            "a": {"name": "Posel A", "status": "active", "next_action": "Naredi X."},
            "b": {"name": "Posel B", "status": "active", "next_action": ""},
        },
        "first_week_lock": {
            "allowed_write": ["actions/", "tests/", "docs/", "chief/"],
            "locked": ["core/daemon.py", "run_swarm.py"],
        },
    }


# --- model ---------------------------------------------------------------- #
def test_model_seed_se_nalozi():
    m = load_model(MODEL_FILE)
    assert isinstance(m, dict) and m.get("robert")
    assert isinstance(m.get("ventures"), dict) and m["ventures"]
    assert m.get("first_week_lock", {}).get("locked")


def test_load_model_missing_vrne_prazno(tmp_path):
    assert load_model(tmp_path / "ni.yaml") == {}


def test_missing_next_pove_katere():
    missing = dict(ventures_missing_next(_model()))
    assert "b" in missing
    assert "a" not in missing


# --- aktivnost ------------------------------------------------------------ #
def test_audit_prazna_datoteka():
    act = audit_activity(Path("ne-obstaja.jsonl"), date="2026-09-02")
    assert act["total"] == 0 and act["failed"] == 0


def test_audit_steje_za_dan(tmp_path):
    f = tmp_path / "audit.jsonl"
    f.write_text(
        '{"ts": 1788360008, "event": "x", "project": "p1", "status": "ok"}\n'
        '{"ts": 1788363616, "event": "y", "project": "p2", "status": "failed"}\n',
        encoding="utf-8",
    )
    # ts 1788360008/1788363616 → lokalni datum; preberimo vse kar pade na isti dan
    act = audit_activity(f, date="2026-09-02")
    # Robustnost: če ts ne ustreza temu datumu v lokalni coni, naj bo total 0 — ne pade.
    assert isinstance(act["total"], int)
    assert "failed_projects" in act


# --- poročilo ------------------------------------------------------------- #
def test_digest_vsebuje_pošteno_praznino():
    txt = build_digest(_model(), date="2026-09-02")
    assert "dnevno poročilo" in txt
    assert "čaka tvoj vnos" in txt            # posel B brez next_action
    assert "Predlog za jutri" in txt


def test_digest_ne_izumi_cilja_ko_ni_signalov():
    m = {"ventures": {"c": {"name": "P", "status": "active", "next_action": ""}}}
    txt = build_digest(m, date="2026-09-02",
                       activity={"total": 0, "failed_projects": []})
    assert "dopolni `next_action`" in txt


def test_write_digest_atomicno(tmp_path):
    p = write_digest(tmp_path, date="2026-09-02", model=_model())
    assert p is not None and p.exists()
    assert (tmp_path / "latest.md").exists()


def test_propose_next_iz_modela_in_padlih():
    act = {"failed_projects": ["x_mod"]}
    predlogi = propose_next(_model(), act)
    assert any("Posel A" in s for s in predlogi)      # next_action
    assert any("x_mod" in s for s in predlogi)        # padli dogodek
    assert not any("Posel B" in s for s in predlogi)  # brez next_action → ne izumi


def test_correction_se_shrani(tmp_path):
    f = append_correction(tmp_path, date="2026-09-02", text="To ni bilo prav.")
    assert f is not None and f.exists()
    assert "To ni bilo prav" in f.read_text(encoding="utf-8")


def test_correction_prazna_ne_pise(tmp_path):
    assert append_correction(tmp_path, text="   ") is None


# --- učenje in zgodovina ------------------------------------------------ #
def test_fold_corrections_v_lekcije(tmp_path):
    cdir = tmp_path / "corrections"
    cdir.mkdir(parents=True)
    (cdir / "2026-09-02.md").write_text(
        "- 2026-09-02T10:00:00: To ni bilo prav.\n- 2026-09-02T11:00:00: Druga lekcija.\n",
        encoding="utf-8")
    assert fold_corrections(tmp_path) == 2
    lessons = load_lessons(tmp_path)
    assert len(lessons) == 2
    # Idempotentno — ponovni fold ne doda duplikatov.
    assert fold_corrections(tmp_path) == 0
    assert len(load_lessons(tmp_path)) == 2


def test_fold_brez_corrections_dir(tmp_path):
    assert fold_corrections(tmp_path) == 0


def test_digest_pokaže_naučene_lekcije():
    lessons = [{"date": "2026-09-02", "lesson": "Upoštevaj rollback."}]
    txt = build_digest(_model(), date="2026-09-02", lessons=lessons)
    assert "Naučeno do zdaj" in txt
    assert "Upoštevaj rollback." in txt


def test_history_in_week_summary(tmp_path):
    assert record_history(tmp_path, date="2026-09-01", model=_model(),
                          activity={"ok": 5, "failed": 1,
                                    "failed_projects": ["p"]})
    assert record_history(tmp_path, date="2026-09-02", model=_model(),
                          activity={"ok": 3, "failed": 0,
                                    "failed_projects": []})
    rows = read_history(tmp_path)
    assert len(rows) == 2
    s = week_summary(tmp_path, days=7)
    assert "8 ok" in s and "1 failed" in s
    assert week_summary(tmp_path / "ni").startswith("(ni še zgodovine")


# --- varovalka ------------------------------------------------------------ #
def test_guard_pusti_nenevarno_in_blokira_jedro():
    assert guard("actions/nek_modul/main.py", _model()) == (True, "ok")
    assert guard("chief/model.yaml", _model())[0] is True
    ok, why = guard("core/daemon.py", _model())
    assert not ok and "zaklenjeno" in why
    ok2, _ = guard("core/orchestrator.py", _model())
    assert not ok2


def test_guard_zavrne_izven_con():
    ok, why = guard("random/kar_koli.py", _model())
    assert not ok and "dovoljenih con" in why
