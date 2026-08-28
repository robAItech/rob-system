"""main.py — FastAPI integracijski router za upravljanje izdelkov in zalog.

Tanka HTTP plast nad ``InventoryService``: Pydantic sheme validirajo vhod,
router delegira v čisto async logiko in VSE napake (4xx/5xx) vrača kot
neposredne ``JSONResponse`` objekte — brez zanašanja na privzete
FastAPI exception handlerje.

Uporaba:
    from zgradi__s3.main import app, create_app
    client = TestClient(create_app())   # svež servis na test
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, FastAPI, Query
from fastapi.responses import JSONResponse

try:  # paketni kontekst
    from .schemas import (
        Product,
        ProductCreate,
        ProductStatus,
        ProductUpdate,
        StockAdjustment,
        StockLevel,
        StockMovement,
    )
    from .zgradi__s3 import DomainError, InventoryService
except ImportError:  # top-level kontekst
    from schemas import (  # type: ignore
        Product,
        ProductCreate,
        ProductStatus,
        ProductUpdate,
        StockAdjustment,
        StockLevel,
        StockMovement,
    )
    from zgradi__s3 import DomainError, InventoryService  # type: ignore


def _error_response(exc: DomainError) -> JSONResponse:
    """Pretvori domensko izjemo v direktno JSONResponse (4xx/5xx)."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )


def build_router(service: InventoryService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/products")
    async def list_products(
        category: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
    ) -> JSONResponse:
        try:
            status_enum = None
            if status is not None:
                try:
                    status_enum = ProductStatus(status.lower())
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={"detail": f"Neveljaven status: '{status}'"},
                    )
            products = await service.list_products(category=category, status=status_enum)
            return JSONResponse(
                content={"items": [p.model_dump(mode="json") for p in products]}
            )
        except DomainError as exc:
            return _error_response(exc)

    @router.post("/products")
    async def create_product(data: ProductCreate) -> JSONResponse:
        try:
            product = await service.create_product(data)
            return JSONResponse(
                status_code=201,
                content=product.model_dump(mode="json"),
            )
        except DomainError as exc:
            return _error_response(exc)

    @router.get("/products/{product_id}")
    async def get_product(product_id: int) -> JSONResponse:
        try:
            product = await service.get_product(product_id)
            return JSONResponse(content=product.model_dump(mode="json"))
        except DomainError as exc:
            return _error_response(exc)

    @router.put("/products/{product_id}")
    async def update_product(product_id: int, data: ProductUpdate) -> JSONResponse:
        try:
            product = await service.update_product(product_id, data)
            return JSONResponse(content=product.model_dump(mode="json"))
        except DomainError as exc:
            return _error_response(exc)

    @router.delete("/products/{product_id}")
    async def delete_product(product_id: int) -> JSONResponse:
        try:
            product = await service.delete_product(product_id)
            return JSONResponse(content=product.model_dump(mode="json"))
        except DomainError as exc:
            return _error_response(exc)

    @router.post("/products/{product_id}/stock/adjust")
    async def adjust_stock(product_id: int, data: StockAdjustment) -> JSONResponse:
        try:
            level = await service.adjust_stock(product_id, data)
            return JSONResponse(content=level.model_dump(mode="json"))
        except DomainError as exc:
            return _error_response(exc)

    @router.get("/products/{product_id}/stock")
    async def get_stock(product_id: int) -> JSONResponse:
        try:
            level = await service.get_stock(product_id)
            return JSONResponse(content=level.model_dump(mode="json"))
        except DomainError as exc:
            return _error_response(exc)

    @router.get("/products/{product_id}/movements")
    async def list_movements(
        product_id: int,
        limit: int = Query(100, ge=1, le=1000),
    ) -> JSONResponse:
        try:
            movements = await service.list_movements(product_id=product_id, limit=limit)
            return JSONResponse(
                content={"items": [m.model_dump(mode="json") for m in movements]}
            )
        except DomainError as exc:
            return _error_response(exc)

    @router.get("/stock/low")
    async def low_stock(
        threshold: Optional[int] = Query(None, ge=0),
    ) -> JSONResponse:
        try:
            levels = await service.low_stock(threshold=threshold)
            return JSONResponse(
                content={"items": [s.model_dump(mode="json") for s in levels]}
            )
        except DomainError as exc:
            return _error_response(exc)

    return router


def create_app(service: Optional[InventoryService] = None) -> FastAPI:
    """Ustvari FastAPI aplikacijo; brez parametra dobi svež servis."""
    app = FastAPI(title="zgradi__s3 — izdelki in zaloge", version="1.0.0")
    app.state.service = service or InventoryService()
    app.include_router(build_router(app.state.service))
    return app


app = create_app()
