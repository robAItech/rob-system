"""order_report — generiranje Markdown poročila o naročilih.

Poročilo vsebuje tabelo naročil, skupni znesek in štetje; zapiše se v
``order_report.md`` (v delovnem imeniku).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Optional

REPORT_FILENAME = "order_report.md"


def _fmt(value: float) -> str:
    try:
        return f"{Decimal(str(value)):.2f}"
    except Exception:  # noqa: BLE001 — neveljaven znesek -> surova vrednost
        return str(value)


def generate_report(orders: Iterable[Mapping]) -> str:
    """Sestavi Markdown poročilo iz seznama naročil (dict-ov).

    Vsebuje naslov (#), skupni znesek, štetje in tabelo naročil
    (ID, stranka, št. postavk, skupaj z DDV).
    """
    order_list = list(orders or [])
    total = Decimal("0")
    for order in order_list:
        try:
            total += Decimal(str(order.get("total", 0)))
        except Exception:  # noqa: BLE001 — neveljaven znesek preskočimo
            continue

    lines: list = []
    lines.append("# Poročilo o naročilih")
    lines.append("")
    lines.append(f"Število naročil: **{len(order_list)}**")
    lines.append(f"Skupni znesek (z DDV): **{_fmt(float(total))} EUR**")
    lines.append("")
    lines.append("| ID | Stranka | Št. postavk | Skupaj (EUR) |")
    lines.append("|---|---|---|---|")
    for order in order_list:
        order_id = order.get("id", "-")
        customer = order.get("customer", "-")
        items = order.get("items") or []
        lines.append(
            f"| {order_id} | {customer} | {len(items)} | {_fmt(order.get('total', 0))} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("*Poročilo je ustvaril order_platform.*")
    lines.append("")
    return "\n".join(lines)


def write_report(orders: Iterable[Mapping], path: Optional[str] = None) -> str:
    """Zapiši poročilo v Markdown datoteko in vrni vsebino."""
    content = generate_report(orders)
    target = Path(path or REPORT_FILENAME)
    target.write_text(content, encoding="utf-8")
    return content