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
