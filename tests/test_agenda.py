"""Testi za Fazo 2 — agenda z `source` polje (več vhodov → skupna vrsta).

Brez pravih zunanjih virov. AGENDA_FILE se presmeri na tmp, da ne piše v
realni repo .rob_ai/agenda.json.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import core.agenda as agenda


@pytest.fixture
def iso(tmp_path, monkeypatch):
    """Izoliraj agenda datoteko na tmp (ne koren repo)."""
    f = tmp_path / "agenda.json"
    monkeypatch.setattr(agenda, "AGENDA_FILE", f)
    return f


def test_add_z_source_vsebuje_polje(iso):
    item = agenda.add("Izdelaj predlog", kind="markdown", source="gmail")
    assert item["status"] == "pending"     # čaka na potrditev, ne obdelan
    assert item["source"] == "gmail"
    assert item["kind"] == "markdown"
    # v datoteki prisotno
    data = agenda.all_()
    assert len(data) == 1 and data[0]["source"] == "gmail"


def test_add_brez_source_default(iso):
    """Obstoječi klici (brez source) → brez napake, brez source polja."""
    item = agenda.add("Obdelaj", kind="python")
    assert "source" not in item
    assert item["status"] == "pending"


def test_pending_iz_gmail_ni_avtomatsko_obdelan(iso):
    """Gmail vnos ostane pending, dokler ga uporabnik ne zažene."""
    agenda.add("Povpraševanje od stranke", kind="markdown", source="gmail")
    p = agenda.pending()
    assert len(p) == 1
    # ni statusa running/done → ni bil samodejno obdelan
    assert p[0]["status"] == "pending"


def test_claim_pending_fifo_and_limit(iso):
    a = agenda.add("a", target="t1", source="cli")
    b = agenda.add("b", target="t2", source="cli")
    c = agenda.add("c", target="t3", source="cli")
    claimed = agenda.claim_pending(limit=2)
    assert [x["id"] for x in claimed] == [a["id"], b["id"]]
    assert len(agenda.claim_pending(limit=10)) == 3


def test_claim_pending_distinct_targets(iso):
    agenda.add("a", target="t1", source="cli")
    agenda.add("b", target="t2", source="cli")
    agenda.add("c", target="t1", source="cli")   # isti target kot a
    agenda.add("d", target="t3", source="cli")
    claimed = agenda.claim_pending(limit=10)
    targets = [x["target"] for x in claimed]
    assert targets == ["t1", "t2", "t3"]   # samo prvi pojav vsakega targeta


def test_claim_pending_excludes_active_targets(iso):
    agenda.add("a", target="t1", source="cli")
    agenda.add("b", target="t2", source="cli")
    claimed = agenda.claim_pending(exclude_targets={"t1"}, limit=10)
    assert [x["target"] for x in claimed] == ["t2"]


def test_mark_concurrent_no_lost_update(iso):
    """Regression guard za cross-process lock: N sočasnih mark ne sme izgubiti
    posodobitve (paralelni daemon — N subprocesov kliče mark hkrati)."""
    import threading
    items = [agenda.add(f"n{i}", target=f"t{i}", source="cli") for i in range(5)]
    threads = [threading.Thread(target=agenda.mark, args=(it["id"], "done"))
               for it in items]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    statuses = [agenda.get(it["id"])["status"] for it in items]
    assert statuses == ["done"] * 5


def test_add_concurrent_no_lost_update(iso):
    import threading
    threads = [threading.Thread(target=agenda.add, args=(f"naloga{i}",), kwargs={"source": "cli"})
               for i in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(agenda.all_()) == 5


def test_add_extra_polja_se_zdruzijo(iso):
    """SURGICAL — fix naloga nosi test= strukturno (ne samo v direktivi)."""
    item = agenda.add("fix billing", kind="python", target="billing",
                      source="fix_loop", test="test_billing")
    assert item["test"] == "test_billing"
    # persistirano v datoteki
    assert agenda.all_()[0]["test"] == "test_billing"
    # običajni klici (brez extra) delujejo naprej
    item2 = agenda.add("Obdelaj", kind="python")
    assert "test" not in item2
