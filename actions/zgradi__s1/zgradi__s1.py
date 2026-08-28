"""zgradi__s1.py — čista async domenska logika za upravljanje naročil.

Vsebuje poslovna pravila sistema: izračun vsot (subtotal, poštnina, DDV,
skupaj), preverjanje prehodov statusov in pomnilniško shrambo naročil.
Povsem asynchronna (async/await) in brez odvisnosti od FastAPI ali Pydantic
v logiki — sheme se uporabljajo le za podatkovne objekte.

Robni pogoji so eksplicitno zajeti v tipiziranih izjemah DomainError,
ki jih HTTP plast pretvori v direktne JSONResponse 4xx/5xx odgovore.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Mapping, Optional

try:  # paketni kontekst
    from .schemas import (
        Address,
        Customer,
        Order,
        OrderCreate,
        OrderItem,
        OrderStatus,
        OrderUpdate,
        Payment,
        utc_now,
    )
except ImportError:  # top-level kontekst
    from schemas import (
        Address,
        Customer,
        Order,
        OrderCreate,
        OrderItem,
        OrderStatus,
        OrderUpdate,
        Payment,
        utc_now,
    )

__all__ = [
    "TAX_RATE",
    "SHIPPING_FEE",
    "FREE_SHIPPING_THRESHOLD",
    "MAX_ITEMS_PER_ORDER",
    "ALLOWED_TRANSITIONS",
    "DomainError",
    "OrderNotFoundError",
    "InvalidStatusTransitionError",
    "EmptyOrderError",
    "DuplicateProductError",
    "OrderLimitError",
    "InMemoryOrderStore",
    "OrderService",
    "calculate_totals",
    "validate_transition",
]

# ---------------------------------------------------------------------------
# Poslovne konstante
# ---------------------------------------------------------------------------

TAX_RATE = Decimal("0.22")          # 22 % DDV
SHIPPING_FEE = Decimal("3.99")      # pavšalna poštnina
FREE_SHIPPING_THRESHOLD = Decimal("50.00")  # nad tem zneskom je poštnina 0
MAX_ITEMS_PER_ORDER = 20            # zgornja meja števila postavk

# Dovoljeni prehodi statusov — ključ je izvorni status, vrednost množica ciljev.
ALLOWED_TRANSITIONS: Dict[OrderStatus, set] = {
    OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED},
    OrderStatus.PAID: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
    OrderStatus.DELIVERED: set(),
    OrderStatus.CANCELLED: set(),
}


# ---------------------------------------------------------------------------
# Tipizirane domenske izjeme
# ---------------------------------------------------------------------------

class DomainError(Exception):
    """Osnovna domenska napaka; nosi HTTP status in strojno kodo."""

    status_code = 400
    code = "domain_error"

    def __init__(self, detail: str, status_code: Optional[int] = None,
                 code: Optional[str] = None):
        super().__init__(detail)
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class OrderNotFoundError(DomainError):
    def __init__(self, order_id: str):
        super().__init__(
            detail=f"naročilo {order_id!r} ne obstaja",
            status_code=404,
            code="order_not_found",
        )


class InvalidStatusTransitionError(DomainError):
    def __init__(self, current: OrderStatus, target: OrderStatus):
        super().__init__(
            detail=f"nedovoljen prehod statusa: {current.value} -> {target.value}",
            status_code=409,
            code="invalid_status_transition",
        )


class EmptyOrderError(DomainError):
    def __init__(self):
        super().__init__(
            detail="naročilo mora vsebovati vsaj eno postavko",
            status_code=422,
            code="empty_order",
        )


class DuplicateProductError(DomainError):
    def __init__(self, product_id: str):
        super().__init__(
            detail=f"izdelek {product_id!r} se v naročilu pojavi večkrat",
            status_code=422,
            code="duplicate_product",
        )


class OrderLimitError(DomainError):
    def __init__(self, limit: int):
        super().__init__(
            detail=f"naročilo lahko vsebuje največ {limit} postavk",
            status_code=422,
            code="order_limit_exceeded",
        )


# ---------------------------------------------------------------------------
# Pomožne funkcije
# ---------------------------------------------------------------------------

def calculate_totals(items: List[OrderItem],
                     shipping_fee: Decimal = SHIPPING_FEE,
                     tax_rate: Decimal = TAX_RATE,
                     free_shipping_threshold: Decimal = FREE_SHIPPING_THRESHOLD
                     ) -> Dict[str, Decimal]:
    """Izračuna subtotal, poštnino, DDV in skupni znesek.

    - subtotal: vsota (količina * cena) po postavkah
    - poštnina: 0, če subtotal >= prag, sicer pavšal
    - tax: subtotal * stopnja
    - total: subtotal + poštnina + DDV
    """
    subtotal = sum(
        (item.quantity * item.unit_price for item in items), Decimal("0.00")
    )
    subtotal = subtotal.quantize(Decimal("0.01"))
    fee = Decimal("0.00") if subtotal >= free_shipping_threshold else shipping_fee
    tax = (subtotal * tax_rate).quantize(Decimal("0.01"))
    total = (subtotal + fee + tax).quantize(Decimal("0.01"))
    return {
        "subtotal": subtotal,
        "shipping_fee": fee,
        "tax": tax,
        "total": total,
    }


def validate_transition(current: OrderStatus, target: OrderStatus) -> None:
    """Preveri, ali je prehod statusa dovoljen; sicer vrže napako.

    Sprejme tudi nize ("pending", "paid", ...) — pretvori jih v enum, da
    članstvo v množici deluje tudi ob neposrednih klicih storitve z nizi.
    """
    if isinstance(current, str):
        current = OrderStatus(current)
    if isinstance(target, str):
        target = OrderStatus(target)
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise InvalidStatusTransitionError(current, target)


# ---------------------------------------------------------------------------
# Shramba
# ---------------------------------------------------------------------------

class InMemoryOrderStore:
    """Preprosta pomnilniška shramba naročil (izolacija med testi)."""

    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._lock = asyncio.Lock()

    async def get(self, order_id: str) -> Optional[Order]:
        async with self._lock:
            return self._orders.get(order_id)

    async def list_all(self) -> List[Order]:
        async with self._lock:
            return list(self._orders.values())

    async def put(self, order: Order) -> None:
        async with self._lock:
            self._orders[order.id] = order

    async def delete(self, order_id: str) -> bool:
        async with self._lock:
            return self._orders.pop(order_id, None) is not None

    async def clear(self) -> None:
        async with self._lock:
            self._orders.clear()


# ---------------------------------------------------------------------------
# Storitev — čista async logika
# ---------------------------------------------------------------------------

class OrderService:
    """Domenska storitev: ustvari, poišči, posodobi, izbriši naročilo."""

    def __init__(self, store: Optional[InMemoryOrderStore] = None) -> None:
        self._store = store or InMemoryOrderStore()

    # -- interne pomožne metode ------------------------------------------------

    async def _require_order(self, order_id: str) -> Order:
        order = await self._store.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order

    @staticmethod
    def _build_order(payload: OrderCreate, order_id: str,
                     created_at: Optional[datetime] = None) -> Order:
        """Zgradi domenski Order iz OrderCreate in izračuna finančne vsote."""
        if not payload.items:
            raise EmptyOrderError()

        seen: set = set()
        for item in payload.items:
            if item.product_id in seen:
                raise DuplicateProductError(item.product_id)
            seen.add(item.product_id)

        if len(payload.items) > MAX_ITEMS_PER_ORDER:
            raise OrderLimitError(MAX_ITEMS_PER_ORDER)

        totals = calculate_totals(payload.items)
        customer = payload.customer
        payment = payload.payment

        # Ko plačilo ni podano (ali je njegov znesek 0/negativen), zapišemo
        # zgolj predviden znesek — izračunan total naročila.
        if payment is None or payment.amount <= 0:
            payment = Payment(amount=totals["total"])

        stamp = created_at or utc_now()
        return Order(
            id=order_id,
            customer=customer,
            items=payload.items,
            payment=payment,
            status=OrderStatus.PENDING,
            subtotal=totals["subtotal"],
            shipping_fee=totals["shipping_fee"],
            tax=totals["tax"],
            total=totals["total"],
            created_at=stamp,
            updated_at=stamp,
        )

    # -- javni API --------------------------------------------------------------

    async def create_order(self, payload: OrderCreate) -> Order:
        """Ustvari naročilo; order_id je enoličen UUID."""
        order_id = str(uuid.uuid4())
        order = self._build_order(payload, order_id)
        await self._store.put(order)
        return order

    async def get_order(self, order_id: str) -> Order:
        """Vrne naročilo ali vrže OrderNotFoundError (404)."""
        return await self._require_order(order_id)

    async def list_orders(self, status: Optional[OrderStatus] = None) -> List[Order]:
        """Vrne vsa naročila; opcijsko filtrirana po statusu."""
        orders = await self._store.list_all()
        if status is None:
            return orders
        return [order for order in orders if order.status == status]

    async def update_status(self, order_id: str,
                            new_status: OrderStatus) -> Order:
        """Posodobi status ob upoštevanju dovoljenih prehodov (409)."""
        order = await self._require_order(order_id)
        validate_transition(order.status, new_status)
        updated = order.model_copy(update={
            "status": new_status,
            "updated_at": utc_now(),
        })
        await self._store.put(updated)
        return updated

    async def delete_order(self, order_id: str) -> None:
        """Izbriše naročilo; neobstoječe vrže OrderNotFoundError (404)."""
        await self._require_order(order_id)
        await self._store.delete(order_id)
