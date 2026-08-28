"""main.py — FastAPI integracijski router za sistem upravljanja naročil.

Tanka HTTP plast nad ``OrderService``: Pydantic sheme validirajo vhod,
router delegira v čisto async logiko in VSE napake (4xx/5xx) vrača kot
neposredne ``JSONResponse`` objekte — brez zanašanja na privzete
FastAPI exception handlerje.

Uporaba:
    from zgradi__s1.main import app, create_app
    client = TestClient(create_app())   # svež servis na test
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, FastAPI, Query, Response
from fastapi.responses import JSONResponse

try:  # paketni kontekst
    from .schemas import OrderCreate, OrderStatus, OrderUpdate
    from .zgradi__s1 import DomainError, OrderService
except ImportError:  # top-level kontekst
    from schemas import OrderCreate, OrderStatus, OrderUpdate
    from zgradi__s1 import DomainError, OrderService

__all__ = ["build_router", "create_app", "app", "router"]


def _error_response(status_code: int, detail: str, code: str) -> JSONResponse:
    """Sestavi enoten JSONResponse za napake (4xx/5xx)."""
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "code": code},
    )


def build_router(service: Optional[OrderService] = None) -> APIRouter:
    """Sestavi APIRouter; brez podanega servisa uporabi svežega."""
    router = APIRouter(prefix="/orders", tags=["orders"])
    svc = service or OrderService()

    @router.post("", status_code=201)
    async def create_order(payload: OrderCreate) -> JSONResponse:
        try:
            order = await svc.create_order(payload)
        except DomainError as exc:
            return _error_response(exc.status_code, exc.detail, exc.code)
        except Exception:  # defensivno: vedno JSONResponse, nikoli gol stack
            return _error_response(500, "notranja napaka", "internal_error")
        return JSONResponse(status_code=201, content=order.model_dump(mode="json"))

    @router.get("")
    async def list_orders(
        status: Optional[OrderStatus] = Query(default=None),
    ) -> JSONResponse:
        try:
            orders = await svc.list_orders(status=status)
        except DomainError as exc:
            return _error_response(exc.status_code, exc.detail, exc.code)
        return JSONResponse(
            status_code=200,
            content=[order.model_dump(mode="json") for order in orders],
        )

    @router.get("/{order_id}")
    async def get_order(order_id: str) -> JSONResponse:
        try:
            order = await svc.get_order(order_id)
        except DomainError as exc:
            return _error_response(exc.status_code, exc.detail, exc.code)
        return JSONResponse(status_code=200, content=order.model_dump(mode="json"))

    @router.patch("/{order_id}")
    async def update_order(order_id: str, payload: OrderUpdate) -> JSONResponse:
        try:
            order = await svc.update_status(order_id, payload.status)
        except DomainError as exc:
            return _error_response(exc.status_code, exc.detail, exc.code)
        return JSONResponse(status_code=200, content=order.model_dump(mode="json"))

    @router.delete("/{order_id}", status_code=204)
    async def delete_order(order_id: str) -> Response:
        try:
            await svc.delete_order(order_id)
        except DomainError as exc:
            return _error_response(exc.status_code, exc.detail, exc.code)
        # HTTP 204 nima telesa: prazen Response (ne JSONResponse z vsebino "null").
        return Response(status_code=204)

    return router


def create_app(service: Optional[OrderService] = None) -> FastAPI:
    """Ustvari FastAPI aplikacijo; privzeto s svežim servisom (testna izolacija)."""
    application = FastAPI(
        title="Order Management System",
        description=(
            "Skupna podatkovna shema in arhitektura sistema za upravljanje naročil."
        ),
        version="1.0.0",
    )
    application.include_router(build_router(service))
    return application


# Modulna primera: `app` in `router` delita en skupen servis.
_default_service = OrderService()
app = create_app(_default_service)
router = build_router(_default_service)
