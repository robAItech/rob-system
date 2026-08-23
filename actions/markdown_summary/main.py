"""FastAPI integration router for the markdown_summary module.

Architectural guideline mapping:
  - API: FastAPI z direct JSONResponse 4xx/5xx handlingom -> vsi odzivi so
    JSONResponse; 404 za manjkajočo datoteko, 500 za napake generiranja.
"""

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .markdown_summary import DEFAULT_FILENAME, MODULE_DIR, generate_summary, render_markdown, write_summary_file
from .schemas import SummaryDocument

router = APIRouter(prefix="/markdown-summary", tags=["markdown_summary"])


@router.get("/summary.md")
async def get_summary() -> JSONResponse:
    """Vrni vsebino generiranega Markdown dokumenta (ali 404, če ne obstaja)."""
    path: Path = MODULE_DIR / DEFAULT_FILENAME
    if not path.exists():
        return JSONResponse(
            status_code=404,
            content={"error": "summary.md not found"},
        )
    return JSONResponse(
        status_code=200,
        content={"filename": DEFAULT_FILENAME, "content": path.read_text(encoding="utf-8")},
    )


@router.post("/generate")
async def post_generate(document: SummaryDocument) -> JSONResponse:
    """Generiraj summary.md iz podanega dokumenta (500 ob nepričakovani napaki)."""
    try:
        path: Path = await generate_summary(document)
    except Exception as exc:  # pragma: no cover - obrambni 5xx handling
        return JSONResponse(
            status_code=500,
            content={"error": f"generation failed: {exc}"},
        )
    return JSONResponse(
        status_code=200,
        content={"path": str(path), "content": render_markdown(document)},
    )


@router.post("/generate-default")
async def post_generate_default() -> JSONResponse:
    """Generiraj summary.md s privzetim vsebino (brez telesa zahteve)."""
    try:
        path: Path = await generate_summary()
    except Exception as exc:  # pragma: no cover - obrambni 5xx handling
        return JSONResponse(
            status_code=500,
            content={"error": f"generation failed: {exc}"},
        )
    return JSONResponse(status_code=200, content={"path": str(path)})