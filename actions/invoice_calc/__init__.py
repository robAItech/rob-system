"""invoice_calc — izračun faktur z DDV in popusti.

Javni API:
- `calculate_invoice` / `compute_invoice` / `calculate_total` / `compute_total`
- sheme: `InvoiceRequest`, `InvoiceItem`, `InvoiceLine`, `Invoice`, `InvoiceResult`
- FastAPI: `app` (TestClient) in `router`
"""
from .invoice_calc import (
    InvoiceValidationError,
    calculate_invoice,
    calculate_total,
    compute_invoice,
    compute_total,
)
from .schemas import (
    Invoice,
    InvoiceItem,
    InvoiceLine,
    InvoiceRequest,
    InvoiceResult,
    round_money,
    to_decimal,
)
from .main import app, router

__all__ = [
    "Invoice",
    "InvoiceItem",
    "InvoiceLine",
    "InvoiceRequest",
    "InvoiceResult",
    "InvoiceValidationError",
    "app",
    "calculate_invoice",
    "calculate_total",
    "compute_invoice",
    "compute_total",
    "round_money",
    "router",
    "to_decimal",
]

__version__ = "1.0.0"
