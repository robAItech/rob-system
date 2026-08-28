"""order_api — FastAPI aplikacija s trdnim in-memory shranjevanjem.

Endpoints:
- ``POST /orders``  -> 201 (ustvarjeno) / 422 (validacijska napaka)
- ``GET /orders/{id}`` -> 200 / 404
- ``GET /health`` -> 200
"""

from __future__ import annotations

import threading
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, Response, status
from fastapi.responses import JSONResponse

from .order_engine import calculate_total, generate_order_id
from .order_models import Item, Order

app = FastAPI(title="Order Platform API", version="1.0.0")

#: In-memory store: {order_id: Order} — modulski dict kot vir stanja.
_store: Dict[str, Order] = {}
_store_lock = threading.Lock()


def _health_check() -> dict:
    return {"status": "ok", "orders": len(_store)}


@app.get("/health", tags=["system"])
def health() -> JSONResponse:
    """Preveri delovanje storitve."""
    return JSONResponse(content=_health_check(), status_code=200)


@app.post("/orders", response_model=Order, status_code=status.HTTP_201_CREATED, tags=["orders"])
def create_order(payload: dict) -> JSONResponse:
    """Ustvari naročilo: izračuna znesek, validira in shrani.

    Sprejme surovi dict (npr. iz CLI-ja ali testa), izračuna skupni znesek
    z 22 % DDV ter vrne 201 s shranjenim naročilom; pri napaki validacije
    vrne JSONResponse 422 namesto FastAPI-jevih 422 podrobnosti.
    """
    try:
        customer = payload.get("customer") or ""
        raw_items = payload.get("items") or []
        total = calculate_total(raw_items)
        order_id = generate_order_id(len(_store) + 1)
        order = Order(id=order_id, customer=customer, items=raw_items, total=float(total))
    except Exception as exc:  # noqa: BLE001 — vhod napaka -> 422
        return JSONResponse(
            content={"detail": f"Validacijska napaka: {exc}"},
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    with _store_lock:
        _store[order.id] = order
    return JSONResponse(content=order.model_dump(), status_code=status.HTTP_201_CREATED)


@app.get("/orders/{order_id}", response_model=Order, tags=["orders"])
def get_order(order_id: str) -> JSONResponse:
    """Vrni naročilo po ID-ju (200) ali 404, če ne obstaja."""
    with _store_lock:
        order = _store.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Naročilo {order_id!r} ne obstaja")
    return JSONResponse(content=order.model_dump(), status_code=200)


@app.get("/orders", tags=["orders"])
def get_all_orders() -> JSONResponse:
    """Vrni vsa naročila (po ID-ju, za poročila in pregled)."""
    with _store_lock:
        items = [order.model_dump() for order in sorted(_store.values(), key=lambda o: o.id)]
    return JSONResponse(content={"orders": items, "count": len(items)}, status_code=200)


def reset_store() -> None:
    """Počisti shrambo (uporablja se v testih za izolacijo)."""
    with _store_lock:
        _store.clear()