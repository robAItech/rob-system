"""Testi pregledovalnika dashboarda (deterministični, brez omrežja)."""
from pathlib import Path

import pytest

from actions.dashboard_review.pregled import (
    ROOT,
    SERVER_TS,
    components,
    endpoints,
    summarize,
)


def test_endpoints_prepozna_znane_poti():
    eps = endpoints()
    assert isinstance(eps, list)
    assert "/api/health" in eps
    assert "/api/metrics" in eps


def test_endpoints_prazno_ob_manjkajoci_datoteki(tmp_path):
    assert endpoints("") == []
    # Poklic brez branja diska ni možen; testiramo branje neobstoječe prek
    # direktnega klica z besedilom (parser pričakuje navedene poti, kot v kodi).
    assert endpoints("GET '/api/a' · POST '/api/b'") == ["/api/a", "/api/b"]


def test_components_vsebuje_agendo(tmp_path):
    comps = components()
    assert "agenda.ts" in comps
    assert "graph.ts" in comps


def test_summarize_vrne_kljuce():
    s = summarize()
    assert s["api_endpoints"] >= 10
    assert s["frontend_components"]
    assert s["server_ts_lines"] > 1000


@pytest.mark.skipif(not SERVER_TS.exists(), reason="src ni v tem okolju")
def test_server_obstaja_v_repu():
    assert SERVER_TS.exists()
    assert (ROOT / "src" / "web" / "main.ts").exists()
