"""Testi za core/visual_qa.py — neobvezen vizualni QA (Gemma 4 + Playwright).

Brez pravih Ollama/brskalnika — vse mocka. Preveri: screenshot mock, gemma
verdict parse, review orkestracijo, in da LoopX (HTML zelen) pokliče visual
QA ne da bi blokiral build.
"""
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import visual_qa
from core.loopx_bridge import LoopXEngineBridge


# ------------------------------------------------------------------ #
#  gemma_vision_review
# ------------------------------------------------------------------ #
def test_gemma_parse_strukture():
    """Parse Gemma JSON → dict."""
    import json as _j
    v = visual_qa._parse_gemma_verdict('{"ok": true, "summary": "OK", "issues": []}')
    assert v["ok"] is True
    v2 = visual_qa._parse_gemma_verdict('tekst {\n"ok":false,"issues":["x"]\n}')
    assert v2["ok"] is False


def test_gemma_vision_review_vrne_verdict(tmp_path):
    """Mock _ollama_generate → struktura verdikta."""
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG")
    with mock.patch.object(visual_qa, "_ollama_generate",
                           return_value='{"ok": true, "summary": "v redu", "issues": []}'):
        r = visual_qa.gemma_vision_review(png)
    assert r["ok"] is True
    assert "issues" in r


def test_gemma_vision_review_ob_napaki_ne_crash(tmp_path):
    """Ollama napaka → {ok: None, error} (ne crash)."""
    png = tmp_path / "shot.png"
    png.write_bytes(b"x")
    with mock.patch.object(visual_qa, "_ollama_generate", side_effect=RuntimeError("ollama dol")):
        r = visual_qa.gemma_vision_review(png)
    assert r["ok"] is None
    assert "error" in r


# ------------------------------------------------------------------ #
#  screenshot_html
# ------------------------------------------------------------------ #
def test_screenshot_html_vrne_true(tmp_path):
    """Mock Playwright → vrne True."""
    with mock.patch("playwright.sync_api.sync_playwright"):
        ok = visual_qa.screenshot_html(str(tmp_path / "x.html"), tmp_path / "out.png")
    assert ok is True


def test_screenshot_html_ob_izjemi_vrne_false(tmp_path):
    """Playwright napaka → False (ne crash)."""
    with mock.patch("playwright.sync_api.sync_playwright",
                    side_effect=RuntimeError("browser fail")):
        ok = visual_qa.screenshot_html("x.html", tmp_path / "o.png")
    assert ok is False


# ------------------------------------------------------------------ #
#  review orkestracija
# ------------------------------------------------------------------ #
def test_review_orkestrra(tmp_path, monkeypatch):
    """Screenshot + gemma mock → struktura poročila."""
    tmp_html = tmp_path / "neki.html"
    tmp_html.write_text("<html>...</html>", encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # review piše PNG pod .rob_ai/ tmp
    # review preveri png.exists() — mock screenshot ne naredi PNG, zato
    # predhodno ustvarimo mesto, kamor bi screenshot pisal.
    (tmp_path / ".rob_ai").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".rob_ai" / ".visual_qa_tmp.png").write_bytes(b"\x89PNG")
    with mock.patch.object(visual_qa, "screenshot_html", return_value=True), \
         mock.patch.object(visual_qa, "gemma_vision_review",
                           return_value={"ok": True, "summary": "lepo", "issues": []}):
        r = visual_qa.review(str(tmp_html))
    assert r["ok"] is True
    assert r["screenshot_ok"] is True


def test_review_ob_screenshot_napaki(tmp_path, monkeypatch):
    """Screenshot fail → {ok: None, error}, ne crash."""
    monkeypatch.chdir(tmp_path)
    with mock.patch.object(visual_qa, "screenshot_html", return_value=False):
        r = visual_qa.review("neki.html")
    assert r["ok"] is None
    assert "screenshot" in r["error"]


# ------------------------------------------------------------------ #
#  LoopX integracija (HTML zelen → neobvezen visual QA, ne blokira)
# ------------------------------------------------------------------ #
def _engine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "actions" / "site").mkdir(parents=True, exist_ok=True)
    (tmp_path / "actions" / "site" / "index.html").write_text("<html></html>", encoding="utf-8")
    e = LoopXEngineBridge("site", db_path=tmp_path / "memory.db")
    e.target_dir = (tmp_path / "actions" / "site").resolve()
    return e


def test_loopx_html_zelen_prikli_visualqa_ne_blokira(tmp_path, monkeypatch):
    """HTML zelen → visual_qa.review poklican + build še vedno True (signala)."""
    from unittest import mock as _m
    e = _engine(tmp_path, monkeypatch)
    captured = {}
    # pytest željen zelen → build True.
    with _m.patch.object(e, "_verify_ruff", return_value=(True, "")), \
         _m.patch.object(e, "_docker_available", return_value=False), \
         _m.patch.object(subprocess, "run",
                         return_value=_m.Mock(returncode=0, stderr="", stdout="ok")), \
         _m.patch.object(e, "_run_optional_visual_qa",
                         side_effect=lambda: captured.setdefault("vqa", True)):
        r = e.execute_and_heal("Izdelaj HTML spletno stran", spec_hint="")
    assert r is True                # build uspe
    assert captured.get("vqa") is True  # visual QA se je sprožil


def test_loopx_visualqa_napaka_ne_zlomi_builda(tmp_path, monkeypatch):
    """Če visual QA pade (realno review dvigne) → build še vedno True.

    Ne mock-a _run_optional_visual_qa — ta ima realni try/except; mock-a
    core.visual_qa.review, da dvigne (kar ujame notranji try/except)."""
    from unittest import mock as _m
    e = _engine(tmp_path, monkeypatch)
    with _m.patch.object(e, "_verify_ruff", return_value=(True, "")), \
         _m.patch.object(e, "_docker_available", return_value=False), \
         _m.patch.object(subprocess, "run",
                         return_value=_m.Mock(returncode=0, stderr="", stdout="ok")), \
         _m.patch("core.visual_qa.review", side_effect=RuntimeError("qa crash")):
        r = e.execute_and_heal("Izdelaj HTML spletno stran")
    assert r is True  # build ni zlomljen ob vizualni napaki


def test_loopx_visualqa_porocilo_se_shrani_v_gbrain(tmp_path, monkeypatch):
    """_run_optional_visual_qa shrani poročilo v gbrain memory."""
    from unittest import mock as _m
    e = _engine(tmp_path, monkeypatch)
    stored = {}
    # Mock core.visual_qa.review (uspešen verdikt) in gbrain.store_memory_node.
    with _m.patch("core.visual_qa.review",
                  return_value={"ok": True, "summary": "lepo", "issues": []}), \
         _m.patch.object(e.gbrain, "store_memory_node",
                         side_effect=lambda **kw: stored.update(kw)):
        e._run_optional_visual_qa()
    assert stored.get("key") == "visual_qa/site"
    assert stored.get("tags")[:2] == ["visual_qa", "html"]
