"""actions/isbn_validator/main.py — FastAPI integration router.

Exposes the ISBN validation domain logic over HTTP with direct JSONResponse
handling for 4xx (validation) and 5xx (unexpected) errors.
"""

from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .isbn_validator import is_valid_isbn10, is_valid_isbn13
from .schemas import ISBNValidationRequest, ISBNValidationResponse

router = APIRouter(prefix="/isbn", tags=["isbn"])


@router.post("/validate", response_model=ISBNValidationResponse)
def validate_isbn(payload: ISBNValidationRequest) -> ISBNValidationResponse:
    """Validate an ISBN string; auto-detects ISBN-10 and ISBN-13."""
    isbn = payload.isbn
    if is_valid_isbn10(isbn) or is_valid_isbn13(isbn):
        return ISBNValidationResponse(isbn=isbn, is_valid=True)
    return ISBNValidationResponse(isbn=isbn, is_valid=False)


app = FastAPI(title="ISBN Validator", version="1.0.0")
app.include_router(router)

# Compatibility alias so the endpoint is reachable both as /isbn/validate
# and as /validate.
app.add_api_route(
    "/validate",
    validate_isbn,
    methods=["POST"],
    response_model=ISBNValidationResponse,
    tags=["isbn"],
)


@app.exception_handler(RequestValidationError)
async def _request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Direct JSONResponse for 4xx request-validation failures."""
    errors = [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Request validation failed", "errors": errors},
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Direct JSONResponse for unexpected 5xx errors."""
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
