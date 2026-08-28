"""order_cli — wrapper, ki poveže VSE module order_platform.

Pot naročila: sprejme (dict) -> izračuna (order_engine) -> validira
(order_models) -> shrani (order_api) -> izpiše poročilo (order_report).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

try:  # paketni kontekst
    from .order_engine import calculate_total
    from .order_models import Order
    from .order_report import write_report
except ImportError:  # top-level kontekst
    from order_engine import calculate_total
    from order_models import Order
    from order_report import write_report

REPORT_FILENAME = "order_report.md"


def process_order(
    payload: Mapping[str, Any],
    order_id: Optional[str] = None,
    report_path: Optional[str] = None,
) -> Order:
    """Obdelaj naročilo skozi celotno verigo in vrni veljavno ``Order``.

    1. order_engine: izračuna skupni znesek (popusti + 22 % DDV).
    2. order_models: validira shemo (prazne postavke -> napaka).
    3. order_api: shrani v in-memory shrambo (če je na voljo).
    4. order_report: zapiše poročilo v Markdown datoteko.
    """
    from . import order_api as _order_api  # lazy, da ni trde odvisnosti

    customer = payload.get("customer") or "Neznana stranka"
    raw_items = payload.get("items") or []
    total = calculate_total(raw_items)
    order = Order(
        id=order_id or f"ORD-{(len(_order_api._store) + 1):04d}",
        customer=customer,
        items=raw_items,
        total=float(total),
    )
    _order_api._store[order.id] = order
    write_report(_order_api._store.values(), report_path)
    return order


def run_cli(argv: Optional[List[str]] = None) -> int:
    """CLI vhod: `python order_cli.py <customer> <sku> <name> <price> <qty> [...]`."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 5 or (len(argv) - 1) % 4 != 0:
        print(
            "Uporaba: python order_cli.py <stranka> <sku> <ime> <cena> <količina> "
            "[<sku> <ime> <cena> <količina> ...]",
            file=sys.stderr,
        )
        return 2
    customer = argv[0]
    items: List[dict] = []
    pos = 1
    while pos + 3 <= len(argv):
        items.append(
            {
                "sku": argv[pos],
                "name": argv[pos + 1],
                "price": float(argv[pos + 2]),
                "quantity": int(argv[pos + 3]),
            }
        )
        pos += 4
    payload: Dict[str, Any] = {"customer": customer, "items": items}
    order = process_order(payload)
    print(f"Ustvarjeno naročilo: {order.id} (skupaj {order.total:.2f} EUR)")
    print(f"Poročilo: {Path(REPORT_FILENAME).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli())