"""FastAPI Integration Router — izpostavi aplikacijo in API funkcije order_api."""

try:  # paketni kontekst
    from .order_api import (
        app,
        create_order,
        get_order,
        get_all_orders,
        reset_store,
    )
except ImportError:  # top-level kontekst
    from order_api import (
        app,
        create_order,
        get_order,
        get_all_orders,
        reset_store,
    )

__all__ = ["app", "create_order", "get_order", "get_all_orders", "reset_store"]