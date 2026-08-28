"""zgradi__s1 — skupna podatkovna shema in arhitektura sistema za upravljanje naročil.

Modul vsebuje:
  schemas.py    – Pydantic V2 sheme (Order, Customer, Address, OrderItem, ...)
                   s strogimi validatorji za robne pogoje.
  zgradi__s1.py – čista async domenska logika (OrderService, izračun vsot,
                   prehodi statusov, shramba v pomnilniku).
  main.py       – FastAPI router z direktnim JSONResponse 4xx/5xx handlingom.
"""

from .schemas import (
    Address,
    Customer,
    Order,
    OrderCreate,
    OrderItem,
    OrderStatus,
    OrderUpdate,
    Payment,
    PaymentMethod,
    money,
    utc_now,
)
from .zgradi__s1 import (
    TAX_RATE,
    SHIPPING_FEE,
    FREE_SHIPPING_THRESHOLD,
    MAX_ITEMS_PER_ORDER,
    ALLOWED_TRANSITIONS,
    DomainError,
    OrderNotFoundError,
    InvalidStatusTransitionError,
    EmptyOrderError,
    DuplicateProductError,
    OrderLimitError,
    InMemoryOrderStore,
    OrderService,
    calculate_totals,
    validate_transition,
)
from .main import app, build_router, create_app, router

__version__ = "1.0.0"

__all__ = [
    "Address",
    "Customer",
    "Order",
    "OrderCreate",
    "OrderItem",
    "OrderStatus",
    "OrderUpdate",
    "Payment",
    "PaymentMethod",
    "money",
    "utc_now",
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
    "app",
    "build_router",
    "create_app",
    "router",
    "__version__",
]