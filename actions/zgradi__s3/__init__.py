"""zgradi__s3 — modul za upravljanje izdelkov in zalog.

Arhitektura v treh plasteh:

  schemas.py    – Pydantic V2 sheme (Product, StockLevel, StockMovement, ...)
                   s strogimi validatorji za robne pogoje.
  zgradi__s3.py – čista async domenska logika (InventoryService: izdelki,
                   prilagajanje zalog, zgodovina premikov, nizke zaloge).
  main.py       – FastAPI router z direktnim JSONResponse 4xx/5xx handlingom.
"""

from .schemas import (
    MAX_QUANTITY,
    MovementType,
    Product,
    ProductCreate,
    ProductStatus,
    ProductUpdate,
    StockAdjustment,
    StockLevel,
    StockMovement,
    utc_now,
)
from .zgradi__s3 import (
    DomainError,
    DuplicateSkuError,
    InsufficientStockError,
    InvalidStockError,
    InventoryService,
    ProductNotFoundError,
    ProductService,
)

__all__ = [
    "MAX_QUANTITY",
    "MovementType",
    "Product",
    "ProductCreate",
    "ProductStatus",
    "ProductUpdate",
    "StockAdjustment",
    "StockLevel",
    "StockMovement",
    "utc_now",
    "DomainError",
    "DuplicateSkuError",
    "InsufficientStockError",
    "InvalidStockError",
    "InventoryService",
    "ProductNotFoundError",
    "ProductService",
]
