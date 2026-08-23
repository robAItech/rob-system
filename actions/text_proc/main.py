"""main.py — FastAPI integracijski router za modul text_proc.

Router izpostavi tri končne točke (tokenize, normalize, word_freq) z
direktnim JSONResponse 4xx/5xx handlingom. Notranja logika ostaja čista
in neodvisna od API plasti.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from actions.text_proc.normalizer import normalize
from actions.text_proc.schemas import (
    NormalizeOutput,
    ProcessOutput,
    TextInput,
    TokenizeOutput,
    WordFreqOutput,
)
from actions.text_proc.stats import word_freq
from actions.text_proc.text_proc import process
from actions.text_proc.tokenizer import tokenize

router = APIRouter(prefix="/text_proc", tags=["text_proc"])


@router.post("/tokenize", response_model=TokenizeOutput)
async def api_tokenize(payload: TextInput) -> JSONResponse:
    """Razčleni niz v seznam besed."""
    try:
        return JSONResponse(status_code=200, content={"tokens": tokenize(payload.text)})
    except Exception as exc:  # pragma: no cover - zaščitni 5xx handler
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/normalize", response_model=NormalizeOutput)
async def api_normalize(payload: TextInput) -> JSONResponse:
    """Normalizira niz (male črke, strnjeni presledki)."""
    try:
        return JSONResponse(status_code=200, content={"normalized": normalize(payload.text)})
    except Exception as exc:  # pragma: no cover - zaščitni 5xx handler
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/word_freq", response_model=WordFreqOutput)
async def api_word_freq(payload: TextInput) -> JSONResponse:
    """Vrni pogostost besed v nizu."""
    try:
        return JSONResponse(status_code=200, content={"word_freq": word_freq(payload.text)})
    except Exception as exc:  # pragma: no cover - zaščitni 5xx handler
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.post("/process", response_model=ProcessOutput)
async def api_process(payload: TextInput) -> JSONResponse:
    """Kombinirana obdelava: normalizacija + tokenizacija + frekvence."""
    try:
        return JSONResponse(status_code=200, content=process(payload.text))
    except Exception as exc:  # pragma: no cover - zaščitni 5xx handler
        return JSONResponse(status_code=500, content={"error": str(exc)})