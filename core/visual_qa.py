"""core/visual_qa.py — neobvezen vizualni QA z Gemma 4 (Ollama) + Playwright.

Sistem je izključno tekstovni; UI artefakti (HTML/dashboard) niso bili nikoli
vizualno preverjeni. Ta modul doda zmožnost: zajemi zaslon HTML (Playwright
chromium) → pošlji sliko v lokalno Gemma 4 (Ollama) → strukturirano kakovostno
poročilo UI (verdict + summary + issues).

Ključno: NEOBVEZEN signal — nikoli ne blokira RSI builda. Vsak korak je
toleranten: če screenshot/Gemma pade → vrne poročilo z errorjem, ne crash.

Zahteve:
- Playwright (py) + chromium browser instalirani.
- Ollama dosegljiv na http://localhost:11434 z `gemma4:*` modelom.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Dict, Optional

OLLAMA_URL = "http://localhost:11434/api/generate"
# Default: manjši model → hitrejši na CPU-only stroju. 31b je prevelik (19 GB)
# za praktičen CPU vizualni QA (timeout → prepočasen). `gemma4:latest` (9.6 GB)
# je razumen izvedljiv kompromis; model se da preglasiti z --model flag.
DEFAULT_MODEL = "gemma4:latest"
GEM_TIMEOUT = 600.0  # sekund na vizualni odziv (ozadje, neobvezen signal)

# Prompt, ki Gemma naj vrne kratko, strukturirano UI sodbo.
VISION_PROMPT = (
    "Oceni to spletno stran vizualno. Vrni IZKLJUČNO JSON obliko brez uvoda,"
    " z natanko temi ključi: {{\"ok\": true/false, \"summary\": <1 kratka poved>,"
    " \"issues\": [<seznam opaženih vizualnih težav, prazno če ni>]}}."
    " Oceni: postavitev, berljivost, kontrast, poravnavo, ali je stran cele in"
    " profesionalna. Bodisi stroga, ampak sočutna."
)


def _ollama_generate(
    prompt: str,
    images: Optional[list] = None,
    model: str = DEFAULT_MODEL,
    timeout: float = 180.0,
) -> str:
    """Pošlji prompt (+ morebitne base64 slike) v Ollama /api/generate. Vrni text.

    Dvigne napako ob neuspehu; klicno mesto (review) jo ujame.
    """
    import requests  # v projektu

    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if images:
        payload["images"] = images
    resp = requests.post(OLLAMA_URL, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("response", "")


def _parse_gemma_verdict(text: str) -> Dict[str, Any]:
    """Iz Gemma teksta izlušči strukturirano sodbo (JSON-ish). Tolerantno."""
    text = text.strip()
    # Poskusi celoten JSON blok.
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    # Poskusi iztrgati {...} blok.
    import re as _re
    m = _re.search(r"\{.*\}", text, _re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    # Fallback: raw na besedo.
    return {"ok": None, "summary": text[:200], "issues": []}


def screenshot_html(source: str, out_png: Path, width: int = 1280) -> bool:
    """Zajemi zaslon HTML poti ali URL-ja v PNG (Playwright chromium headless).

    Vrne True ob uspehu, False ob napaki (brez crash).
    """
    try:
        from playwright.sync_api import sync_playwright

        out_png.parent.mkdir(parents=True, exist_ok=True)
        file_url = source if source.startswith(("http://", "https://")) else f"file:///{Path(source).resolve()}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.goto(file_url, wait_until="networkidle")
            page.screenshot(path=str(out_png), full_page=True)
            browser.close()
        return True
    except Exception:
        return False


def gemma_vision_review(png: Path, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """Pošlji PNG v Gemma 4 (Ollama) za vizualno sodbo. Strukturiran verdikt.

    Ob napaki (Ollama dol, timeout, parse fail) → {ok: None, error: ...} (ne crash).
    """
    model = model or DEFAULT_MODEL
    try:
        b64 = base64.b64encode(png.read_bytes()).decode("ascii")
        text = _ollama_generate(
            VISION_PROMPT, images=[b64], model=model, timeout=GEM_TIMEOUT
        )
        verdict = _parse_gemma_verdict(text)
        verdict.setdefault("model", model)
        return verdict
    except Exception as e:
        return {"ok": None, "error": f"gemma QA ni uspel: {e}", "model": model}


def review(source: str, model: str = DEFAULT_MODEL) -> Dict[str, Any]:
    """Celoten vizualni QA: screenshot → Gemma review → poročilo. Ne crash."""
    if not isinstance(source, str) or not source.strip():
        return {"ok": None, "source": source, "error": "prazen source"}
    png = Path(Path.cwd()) / ".rob_ai" / ".visual_qa_tmp.png"
    ok_shot = screenshot_html(source, png)
    if not ok_shot or not png.exists():
        return {"ok": None, "source": source, "error": "screenshot ni uspel", "screenshot_ok": False}
    report = gemma_vision_review(png, model=model or DEFAULT_MODEL)
    report["source"] = source
    report["screenshot_ok"] = True
    # Ne hranimo base64; računam/skrivmo PNG (že v .rob_ai, izven gita).
    try:
        png.unlink()
    except OSError:
        pass
    return report
