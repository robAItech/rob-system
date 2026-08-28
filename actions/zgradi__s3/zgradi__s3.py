"""zgradi__s3.py — čista async domenska logika za upravljanje izdelkov in zalog.

Arhitektura v treh plasteh:

  schemas.py    – Pydantic V2 sheme (skupni podatkovni model)
  zgradi__s3.py – čista async poslovna logika (ta modul, brez HTTP-ja)
  main.py       – FastAPI router, ki domenske izjeme prevaja v JSONResponse

Domenska plast ne pozna HTTP-ja: za neveljavna poslovna stanja dviga izjeme
(``DomainError`` in podrazrede), ki jih API plast preslika v 4xx/5xx
JSONResponse. Stanje hranimo v pomnilniku (modulski dict kot vir stanja),
zato je servis enostavno testirati in kasneje zamenjati za pravo shrambo.
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Optional

try:  # paketni kontekst
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
except ImportError:  # top-level kontekst
    from schemas import (  # type: ignore
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


class DomainError(Exception):
    """Bazna izjema domenske plasti (preslika se v JSONResponse 4xx/5xx)."""

    status_code = 400

    def __init__(self, message: str, *, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code


class ProductNotFoundError(DomainError):
    status_code = 404


class DuplicateSkuError(DomainError):
    status_code = 409


class InvalidStockError(DomainError):
    status_code = 400


class InsufficientStockError(DomainError):
    status_code = 409


class InventoryService:
    """Async servis za izdelke in zaloge s shrambo v pomnilniku."""

    def __init__(self) -> None:
        self._products: Dict[int, Product] = {}
        self._sku_index: Dict[str, int] = {}
        self._stock: Dict[int, StockLevel] = {}
        self._movements: List[StockMovement] = []
        self._product_seq = itertools.count(1)
        self._movement_seq = itertools.count(1)

    # ------------------------------------------------------------------ izdelki
    async def create_product(self, data: ProductCreate) -> Product:
        """Ustvari izdelek (SKU mora biti unikaten, neobčutljiv na velikost črk)."""
        sku = data.sku.strip()
        key = sku.upper()
        if key in self._sku_index:
            raise DuplicateSkuError(f"Izdelek s SKU '{sku}' že obstaja")
        pid = next(self._product_seq)
        now = utc_now()
        product = Product(**data.model_dump(), id=pid, created_at=now, updated_at=now)
        self._products[pid] = product
        self._sku_index[key] = pid
        self._stock[pid] = StockLevel(product_id=pid, quantity=0, updated_at=now)
        return product

    async def get_product(self, product_id: int) -> Product:
        product = self._products.get(product_id)
        if product is None:
            raise ProductNotFoundError(f"Izdelek z ID {product_id} ne obstaja")
        return product

    async def list_products(
        self,
        category: Optional[str] = None,
        status: Optional[ProductStatus] = None,
    ) -> List[Product]:
        items = list(self._products.values())
        if category is not None:
            items = [p for p in items if p.category == category]
        if status is not None:
            items = [p for p in items if p.status == status]
        return sorted(items, key=lambda p: p.id)

    async def update_product(self, product_id: int, data: ProductUpdate) -> Product:
        """Delno posodobi izdelek; SKU sprememba preverja unikatnost."""
        product = await self.get_product(product_id)
        updates = data.model_dump(exclude_unset=True)
        # Ekspliciten None je smiseln le za tekstovna polja (počisti jih),
        # pri ostalih pa pomeni "pusti nespremenjeno".
        for key in ("sku", "name", "price", "status", "reorder_level"):
            if updates.get(key) is None:
                updates.pop(key, None)
        if "sku" in updates:
            new_sku = updates["sku"].strip()
            key = new_sku.upper()
            existing = self._sku_index.get(key)
            if existing is not None and existing != product_id:
                raise DuplicateSkuError(f"Izdelek s SKU '{new_sku}' že obstaja")
            updates["sku"] = new_sku
        if not updates:
            return product
        merged = product.model_dump()
        merged.update(updates)
        merged["updated_at"] = utc_now()
        updated = Product(**merged)
        self._products[product_id] = updated
        if "sku" in updates and updates["sku"].upper() != product.sku.upper():
            self._sku_index.pop(product.sku.upper(), None)
            self._sku_index[updates["sku"].upper()] = product_id
        return updated

    async def delete_product(self, product_id: int) -> Product:
        """Izbriše izdelek skupaj z njegovo zalogo in vrne izbrisani izdelek."""
        product = await self.get_product(product_id)
        del self._products[product_id]
        self._sku_index.pop(product.sku.upper(), None)
        self._stock.pop(product_id, None)
        return product

    # ------------------------------------------------------------------- zaloge
    async def adjust_stock(self, product_id: int, adjustment: StockAdjustment) -> StockLevel:
        """Spremeni zalogo (IN/OUT/ADJUST) in zapiše premik v zgodovino."""
        await self.get_product(product_id)
        level = self._stock.get(product_id)
        if level is None:
            level = StockLevel(product_id=product_id, quantity=0)
        qty = adjustment.quantity
        if adjustment.type == MovementType.IN:
            new_qty = level.quantity + qty
        elif adjustment.type == MovementType.OUT:
            if qty > level.quantity:
                raise InsufficientStockError(
                    f"Premalo zaloge: na voljo {level.quantity}, zahtevano {qty}"
                )
            new_qty = level.quantity - qty
        else:  # ADJUST → absolutna količina
            new_qty = qty
        if new_qty > MAX_QUANTITY:
            raise InvalidStockError(
                f"Količina zaloge presega maksimum {MAX_QUANTITY}"
            )
        now = utc_now()
        new_level = StockLevel(product_id=product_id, quantity=new_qty, updated_at=now)
        self._stock[product_id] = new_level
        self._movements.append(
            StockMovement(
                id=next(self._movement_seq),
                product_id=product_id,
                type=adjustment.type,
                quantity=qty,
                reason=adjustment.reason,
                created_at=now,
            )
        )
        return new_level

    async def get_stock(self, product_id: int) -> StockLevel:
        await self.get_product(product_id)
        level = self._stock.get(product_id)
        if level is None:
            level = StockLevel(product_id=product_id, quantity=0)
            self._stock[product_id] = level
        return level

    async def list_movements(
        self,
        product_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[StockMovement]:
        """Zgodovina premikov zaloge (po izdelku in/ali omejena na zadnjih N)."""
        if limit < 1:
            raise InvalidStockError("limit mora biti večji od 0")
        items = self._movements
        if product_id is not None:
            await self.get_product(product_id)
            items = [m for m in items if m.product_id == product_id]
        return items[-limit:]

    async def low_stock(self, threshold: Optional[int] = None) -> List[StockLevel]:
        """Zaloge pod pragom; privzeto prag = reorder_level izdelka."""
        result = []
        for pid, level in self._stock.items():
            if threshold is None:
                product = self._products.get(pid)
                if product is None:
                    continue
                limit_qty = product.reorder_level
            else:
                limit_qty = threshold
            if level.quantity <= limit_qty:
                result.append(level)
        return sorted(result, key=lambda s: s.product_id)


# Udoben vzdevek za simetrijo z imenom modula.
ProductService = InventoryService
