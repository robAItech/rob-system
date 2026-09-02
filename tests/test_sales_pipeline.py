"""Testi prodajnega cevovoda (izoliran business ledger v tmp)."""
import pytest

from core import business
from core.sales_pipeline import (
    STAGES,
    advance,
    new_lead,
    open_leads,
    report,
    set_next,
)


@pytest.fixture(autouse=True)
def _izoliran_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(business, "LEDGER_FILE", tmp_path / "business_ledger.json")


def test_nov_lead_na_fazi_lead():
    e = new_lead("Podjetje d.o.o.", "Avtomatski back-office", next_action="Pokliči v torek.")
    assert e is not None and e["stage"] == "lead"
    assert e["company"] == "Podjetje d.o.o."
    assert business.list_ledger()  # v isti glavni knjigi


def test_nov_lead_brez_imena_vrne_none():
    assert new_lead("   ") is None


def test_advance_in_prekini_next():
    e = new_lead("X", "Y")
    assert advance(e["id"], "contacted")
    assert advance(e["id"], "proposal")
    set_next(e["id"], "Pošlji predlog.")
    assert advance(e["id"], "won")
    up = business.list_ledger()[0]
    assert up["stage"] == "won"
    assert up["next_action"] == ""          # končano → brez naslednjega koraka


def test_advance_neveljavna_faza():
    e = new_lead("X", "Y")
    assert advance(e["id"], "nonsense") is False
    assert not advance("ne-obstaja", "won")


def test_open_leads_in_report():
    a = new_lead("A", "…")
    b = new_lead("B", "…")
    advance(b["id"], "won")
    o = open_leads()
    assert len(o) == 1 and o[0]["id"] == a["id"]
    r = report()
    assert r["counts"]["lead"] == 1
    assert r["counts"]["won"] == 1
    assert r["open"] == 1
    assert r["won"] == 1
