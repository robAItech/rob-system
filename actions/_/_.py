"""Core Domain Logic — vstopna točka order_platform (modul '_').

Re-export celotnega sistema, da delujejo vsi uvozni stili:
  from _ import calculate_total, apply_discount, round_money
  from _ import Item, Order
  from _ import app, process_order, write_report
"""

try:  # paketni kontekst (actions._ kot paket)
    from .order_engine import (
        VAT_RATE,
        DISCOUNT_TIERS,
        calculate_total,
        apply_discount,
        round_money,
        discount_rate,
        generate_order_id,
    )
    from .order_models import Item, Order
    from .order_api import app, create_order, get_order, get_all_orders, reset_store
    from .order_cli import process_order
    from .order_report import generate_report, write_report, REPORT_FILENAME
except ImportError:  # top-level kontekst (actions/_ na sys.path prek conftest)
    from order_engine import (
        VAT_RATE,
        DISCOUNT_TIERS,
        calculate_total,
        apply_discount,
        round_money,
        discount_rate,
        generate_order_id,
    )
    from order_models import Item, Order
    from order_api import app, create_order, get_order, get_all_orders, reset_store
    from order_cli import process_order
    from order_report import generate_report, write_report, REPORT_FILENAME

__all__ = [
    "VAT_RATE",
    "DISCOUNT_TIERS",
    "calculate_total",
    "apply_discount",
    "round_money",
    "discount_rate",
    "generate_order_id",
    "Item",
    "Order",
    "app",
    "create_order",
    "get_order",
    "get_all_orders",
    "reset_store",
    "process_order",
    "generate_report",
    "write_report",
    "REPORT_FILENAME",
]