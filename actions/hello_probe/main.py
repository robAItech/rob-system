"""FastAPI integracijski router za hello_probe."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from .hello_probe import greet
from .schemas import GreetRequest

router = APIRouter(prefix="/hello", tags=["hello_probe"])


@router.post("/greet")
async def greet_endpoint(payload: GreetRequest) -> JSONResponse:
    """Vrne pozdrav za ime iz zahtevka.

    Validacijske napake (422) obravnava FastAPI sam; morebitne
    nepričakovane napake vrnemo kot 500 z JSONResponse.
    """
    try:
        message = greet(payload.name)
    except Exception as exc:  # pragma: no cover - defensivno
        return JSONResponse(status_code=500, content={"detail": f"Napaka: {exc}"})
    return JSONResponse(status_code=200, content={"message": message})