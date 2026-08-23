"""Pytest testna zbirka za actions.report_builder.

Pokriva jedro (build_report, _row_title, _normalize_rows), async priročnico,
Pydantic V2 sheme in FastAPI endpoint (direktni klic brez TestClient/HTTP).
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from actions.report_builder.main import build_report_endpoint
from actions.report_builder.report_builder import (
    _normalize_rows,
    _row_title,
    build_report,
    build_report_async,
)
from actions.report_builder.schemas import BuildReportRequest, BuildReportResponse
from actions.string_ops import slug


def _first_value(row: Any) -> Any:
    """Prva vrednost vrstice (deluje za dict in list izhod parse_csv)."""
    if isinstance(row, dict):
        for col in ("naslov", "title"):
            if row.get(col):
                return row[col]
        return next(iter(row.values()))
    return row[0]


# ---------------------------------------------------------------------------
# build_report — združevanje, vrstni red, robni pogoji
# ---------------------------------------------------------------------------


def test_build_report_zdruzi_po_naslovu_ohrani_vrstni_red():
    csv_tekst = (
        "naslov,opis\n"
        "Prvi del,besedilo1\n"
        "Prvi del,besedilo2\n"
        "Drugi del,besedilo3\n"
    )
    report = build_report(csv_tekst)
    assert list(report) == [slug("Prvi del"), slug("Drugi del")]
    assert len(report[slug("Prvi del")]) == 2
    assert len(report[slug("Drugi del")]) == 1
    assert _first_value(report[slug("Prvi del")][0]) == "Prvi del"
    assert _first_value(report[slug("Prvi del")][1]) == "Prvi del"
    assert _first_value(report[slug("Drugi del")][0]) == "Drugi del"


def test_build_report_fallback_title_stolpec():
    report = build_report("title,opis\nNaslov X,besedilo\n")
    assert list(report) == [slug("Naslov X")]
    assert _first_value(report[slug("Naslov X")][0]) == "Naslov X"


def test_build_report_naslov_ima_prednost_pred_title():
    report = build_report("naslov,title,opis\nA,B,x\n")
    assert list(report) == [slug("A")]


def test_build_report_fallback_prva_vrednost():
    report = build_report("stolpec1,stolpec2\nvrednost1,vrednost2\n")
    assert report
    assert slug("vrednost1") in report


def test_build_report_prazne_vrstice_se_izpustijo():
    report = build_report("naslov,opis\nA,x\n\nB,y\n")
    assert list(report) == [slug("A"), slug("B")]


def test_build_report_samo_glava_vrne_prazno():
    assert build_report("naslov,opis\n") == {}


def test_build_report_prazen_vnos_vrne_prazno():
    assert build_report("") == {}
    assert build_report("   \n") == {}


def test_build_report_none_vrze_value_error():
    with pytest.raises(ValueError):
        build_report(None)


def test_build_report_ne_str_vrze_type_error():
    with pytest.raises(TypeError):
        build_report(123)


def test_build_report_parse_csv_none_je_prazen(monkeypatch):
    import actions.report_builder.report_builder as rb

    monkeypatch.setattr(rb, "parse_csv", lambda text: None)
    assert build_report("naslov\nA\n") == {}


@pytest.mark.asyncio
async def test_build_report_async_ustreza_sinhronemu():
    csv_tekst = "naslov,opis\nPrvi del,x\nDrugi del,y\n"
    assert await build_report_async(csv_tekst) == build_report(csv_tekst)


# ---------------------------------------------------------------------------
# _row_title — izbira naslova iz vrstice
# ---------------------------------------------------------------------------


def test_row_title_naslov_stolpec():
    assert _row_title({"naslov": "A", "opis": "x"}) == "A"


def test_row_title_fallback_title():
    assert _row_title({"title": "B", "opis": "x"}) == "B"


def test_row_title_naslov_ima_prednost():
    assert _row_title({"naslov": "A", "title": "B"}) == "A"


def test_row_title_prva_vrednost_mappinga():
    assert _row_title({"opis": "C"}) == "C"


def test_row_title_prazen_mapping_je_none():
    assert _row_title({}) is None
    assert _row_title({"naslov": "   "}) is None


def test_row_title_seznam_prva_vrednost():
    assert _row_title(["D", "E"]) == "D"
    assert _row_title([]) is None
    assert _row_title([None, "E"]) is None


def test_row_title_none_in_skalar():
    assert _row_title(None) is None
    assert _row_title("F") == "F"
    assert _row_title("   ") is None


# ---------------------------------------------------------------------------
# _normalize_rows — poenotenje izhoda parse_csv
# ---------------------------------------------------------------------------


def test_normalize_rows_prazno():
    assert _normalize_rows([]) == []


def test_normalize_rows_dicti_ostanejo():
    rows = [{"naslov": "A", "opis": "x"}]
    assert _normalize_rows(rows) == rows


def test_normalize_rows_seznam_z_glavo_naslov():
    rows = [["naslov", "opis"], ["A", "x"]]
    assert _normalize_rows(rows) == [{"naslov": "A", "opis": "x"}]


def test_normalize_rows_seznam_z_glavo_title():
    rows = [["title", "opis"], ["B", "y"]]
    assert _normalize_rows(rows) == [{"title": "B", "opis": "y"}]


def test_normalize_rows_seznam_brez_glave_ostane():
    rows = [["a", "b"], ["x", "y"]]
    assert _normalize_rows(rows) == rows


# ---------------------------------------------------------------------------
# Pydantic V2 sheme
# ---------------------------------------------------------------------------


def test_schema_request_veljaven():
    req = BuildReportRequest(csv_tekst="naslov\nA\n")
    assert req.csv_tekst == "naslov\nA\n"


def test_schema_request_prazen_niz_zavrnjen():
    with pytest.raises(ValidationError):
        BuildReportRequest(csv_tekst="")


def test_schema_request_strict_tip_zavrnjen():
    with pytest.raises(ValidationError):
        BuildReportRequest(csv_tekst=123)


def test_schema_request_extra_forbid():
    with pytest.raises(ValidationError):
        BuildReportRequest(csv_tekst="x", dodatno="y")


def test_schema_response_sprejme_porocilo():
    resp = BuildReportResponse(report={"a": [{"naslov": "A"}]})
    assert resp.report["a"][0]["naslov"] == "A"


# ---------------------------------------------------------------------------
# FastAPI endpoint (direktni klic, brez TestClient/HTTP)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_prazen_vhod_400():
    resp = await build_report_endpoint(BuildReportRequest(csv_tekst="   "))
    assert resp.status_code == 400
    assert json.loads(resp.body)["detail"] == "csv_tekst ne sme biti prazen."


@pytest.mark.asyncio
async def test_endpoint_veljaven_vhod_200():
    resp = await build_report_endpoint(
        BuildReportRequest(csv_tekst="naslov,opis\nA,x\n")
    )
    assert resp.status_code == 200
    data = json.loads(resp.body)
    assert list(data) == [slug("A")]
    assert len(data[slug("A")]) == 1


@pytest.mark.asyncio
async def test_endpoint_type_error_400(monkeypatch):
    import actions.report_builder.main as main_mod

    def boom(text: str) -> dict:
        raise TypeError("napaka tipa")

    monkeypatch.setattr(main_mod, "build_report", boom)
    resp = await build_report_endpoint(BuildReportRequest(csv_tekst="naslov\nA\n"))
    assert resp.status_code == 400
    assert "napaka tipa" in json.loads(resp.body)["detail"]


@pytest.mark.asyncio
async def test_endpoint_value_error_400(monkeypatch):
    import actions.report_builder.main as main_mod

    def boom(text: str) -> dict:
        raise ValueError("napaka vrednosti")

    monkeypatch.setattr(main_mod, "build_report", boom)
    resp = await build_report_endpoint(BuildReportRequest(csv_tekst="naslov\nA\n"))
    assert resp.status_code == 400
    assert "napaka vrednosti" in json.loads(resp.body)["detail"]


@pytest.mark.asyncio
async def test_endpoint_notranja_napaka_500(monkeypatch):
    import actions.report_builder.main as main_mod

    def boom(text: str) -> dict:
        raise RuntimeError("kaboom")

    monkeypatch.setattr(main_mod, "build_report", boom)
    resp = await build_report_endpoint(BuildReportRequest(csv_tekst="naslov\nA\n"))
    assert resp.status_code == 500
    assert "kaboom" in json.loads(resp.body)["detail"]


# ---------------------------------------------------------------------------
# Paketni API in router
# ---------------------------------------------------------------------------


def test_init_reexport_javnega_api():
    from actions.report_builder import build_report as br

    assert br is build_report


def test_router_konfiguracija():
    from actions.report_builder.main import router

    assert router.prefix == "/api/report-builder"
    assert router.tags == ["report_builder"]
