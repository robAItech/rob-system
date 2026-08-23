"""Pytest testna zbirka za modul invoice_calc — izračun faktur z DDV in popusti.

Pokriva: Decimal pretvorbo in zaokroževanje (ROUND_HALF_UP), strogo Pydantic V2
validacijo (napačni tipi, bool, dodatna polja), izračun faktur (DDV v odstotkih
in ulomkih, popusti na vrstico in globalni, omejitev popusta na subtotal),
vhodne oblike (InvoiceRequest / dict / kwargs z aliasi discount/vat), async in
sinhrone API-je ter FastAPI integracijo (direktni klic + TestClient, če je
httpx na voljo).
"""
from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest
from pydantic import ValidationError

from .invoice_calc import (
    InvoiceValidationError,
    calculate_invoice,
    calculate_total,
    compute_invoice,
    compute_total,
)
from .main import app, calculate_invoice_endpoint
from .schemas import (
    Invoice,
    InvoiceItem,
    InvoiceLine,
    InvoiceRequest,
    InvoiceResult,
    round_money,
    to_decimal,
)

# ---------------------------------------------------------------------------
# Pomožne funkcije
# ---------------------------------------------------------------------------


def _item(**overrides):
    data = {
        "description": "Postavka",
        "quantity": 1,
        "unit_price": "10.00",
    }
    data.update(overrides)
    return data


def _request(**overrides):
    data = {
        "items": [_item()],
        "vat_rate": "22",
        "discount_percent": "0",
        "currency": "EUR",
    }
    data.update(overrides)
    return data


def _run(coro):
    """Požene async klic znotraj sinhronih testov (neodvisno od pytest-asyncio)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# to_decimal / round_money
# ---------------------------------------------------------------------------


def test_to_decimal_accepts_number_like():
    assert to_decimal(10) == Decimal("10")
    assert to_decimal("10.5") == Decimal("10.5")
    assert to_decimal(0.1) == Decimal("0.1")  # brez artefaktov plavajoče vejice
    assert to_decimal(Decimal("7")) == Decimal("7")


def test_to_decimal_rejects_invalid():
    with pytest.raises(ValueError):
        to_decimal(True)
    with pytest.raises(ValueError):
        to_decimal("abc")
    with pytest.raises(ValueError):
        to_decimal(None)
    with pytest.raises(ValueError):
        to_decimal([1, 2])


def test_round_money_half_up():
    assert round_money(Decimal("1.005")) == Decimal("1.01")
    assert round_money(Decimal("1.234")) == Decimal("1.23")
    assert round_money(Decimal("2.675")) == Decimal("2.68")
    assert round_money(Decimal("5")) == Decimal("5.00")
    assert round_money(Decimal("1.2345"), places=3) == Decimal("1.235")


# ---------------------------------------------------------------------------
# Validacija shem (Pydantic V2, strogo)
# ---------------------------------------------------------------------------


def test_invoice_item_valid():
    item = InvoiceItem(description="  Svetilka  ", quantity=3, unit_price="12.50")
    assert item.description == "Svetilka"
    assert item.quantity == 3
    assert item.unit_price == Decimal("12.50")
    assert item.discount_percent == Decimal("0")


def test_invoice_item_invalid_fields():
    with pytest.raises(ValidationError):
        InvoiceItem(description="  ", quantity=1, unit_price="1.00")
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=0, unit_price="1.00")
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=-2, unit_price="1.00")
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=True, unit_price="1.00")
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=1, unit_price="0")
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=1, unit_price="-1")
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=1, unit_price=True)
    with pytest.raises(ValidationError):
        InvoiceItem(
            description="A", quantity=1, unit_price="1.00", discount_percent="150"
        )
    with pytest.raises(ValidationError):
        InvoiceItem(description="A", quantity=1, unit_price="1.00", extra="x")


def test_invoice_request_validation():
    with pytest.raises(ValidationError):
        InvoiceRequest(items=[])
    with pytest.raises(ValidationError):
        InvoiceRequest(items=[_item()], vat_rate="-1")
    with pytest.raises(ValidationError):
        InvoiceRequest(items=[_item()], discount_percent="101")
    with pytest.raises(ValidationError):
        InvoiceRequest(items=[_item()], currency="EU")
    with pytest.raises(ValidationError):
        InvoiceRequest(items=[_item()], currency="EUR", extra="x")


def test_currency_normalized_to_upper():
    req = InvoiceRequest(items=[_item()], currency="usd")
    assert req.currency == "USD"


# ---------------------------------------------------------------------------
# Osnovni izračun
# ---------------------------------------------------------------------------


def test_basic_invoice_calculation():
    result = compute_invoice(
        items=[
            {"description": "A", "quantity": 2, "unit_price": "10.00"},
            {"description": "B", "quantity": 1, "unit_price": "5.00"},
        ],
        vat_rate=22,
        currency="EUR",
    )
    assert result.item_count == 2
    assert result.subtotal == Decimal("25.00")
    assert result.discount_amount == Decimal("0.00")
    assert result.taxable_amount == Decimal("25.00")
    assert result.vat_amount == Decimal("5.50")
    assert result.total == Decimal("30.50")
    assert result.currency == "EUR"


def test_vat_percent_and_fraction_equivalent():
    a = compute_invoice(items=[_item()], vat_rate=22)
    b = compute_invoice(items=[_item()], vat_rate="0.22")
    c = compute_invoice(items=[_item()], vat_rate=Decimal("22"))
    assert a.total == b.total == c.total == Decimal("12.20")
    assert a.vat_amount == b.vat_amount == c.vat_amount == Decimal("2.20")


def test_zero_vat():
    result = compute_invoice(items=[_item(unit_price="19.99")], vat_rate=0)
    assert result.vat_amount == Decimal("0.00")
    assert result.total == result.taxable_amount == Decimal("19.99")


# ---------------------------------------------------------------------------
# Popusti
# ---------------------------------------------------------------------------


def test_line_discount():
    result = compute_invoice(
        items=[
            {
                "description": "A",
                "quantity": 10,
                "unit_price": "10.00",
                "discount_percent": 20,
            }
        ],
        vat_rate=0,
    )
    assert result.subtotal == Decimal("100.00")
    assert result.discount_amount == Decimal("20.00")
    assert result.taxable_amount == Decimal("80.00")
    assert result.total == Decimal("80.00")


def test_global_discount():
    result = compute_invoice(
        items=[_item(unit_price="100.00")],
        vat_rate=0,
        discount_percent=10,
    )
    assert result.discount_amount == Decimal("10.00")
    assert result.taxable_amount == Decimal("90.00")


def test_combined_discounts_capped_at_subtotal():
    result = compute_invoice(
        items=[
            {
                "description": "A",
                "quantity": 1,
                "unit_price": "10.00",
                "discount_percent": 60,
            }
        ],
        vat_rate=0,
        discount_percent=50,
    )
    # 60 % (vrstica) + 50 % (globalno) bi dalo 11.00 > 10.00 → omejeno na subtotal
    assert result.discount_amount == Decimal("10.00")
    assert result.taxable_amount == Decimal("0.00")
    assert result.total == Decimal("0.00")


def test_discount_combined_with_vat():
    result = compute_invoice(
        items=[
            {
                "description": "A",
                "quantity": 2,
                "unit_price": "50.00",
                "discount_percent": 10,
            }
        ],
        vat_rate=20,
        discount_percent=5,
    )
    # subtotal 100; popust vrstice 10; globalni popust 5; obdavčljivo 85;
    # DDV 17; skupaj 102
    assert result.subtotal == Decimal("100.00")
    assert result.discount_amount == Decimal("15.00")
    assert result.taxable_amount == Decimal("85.00")
    assert result.vat_amount == Decimal("17.00")
    assert result.total == Decimal("102.00")


# ---------------------------------------------------------------------------
# Zaokroževanje rezultatov
# ---------------------------------------------------------------------------


def test_rounding_half_up_in_results():
    result = compute_invoice(
        items=[{"description": "A", "quantity": 1, "unit_price": "0.335"}],
        vat_rate=0,
    )
    assert result.subtotal == Decimal("0.34")
    assert result.total == Decimal("0.34")


def test_vat_rounding():
    result = compute_invoice(
        items=[{"description": "A", "quantity": 3, "unit_price": "0.01"}],
        vat_rate=22,
    )
    # subtotal 0.03; DDV 0.03*0.22 = 0.0066 → 0.01; skupaj 0.0366 → 0.04
    assert result.subtotal == Decimal("0.03")
    assert result.vat_amount == Decimal("0.01")
    assert result.total == Decimal("0.04")


# ---------------------------------------------------------------------------
# Vhodne oblike
# ---------------------------------------------------------------------------


def test_accepts_invoice_request_instance():
    req = InvoiceRequest(items=[_item()], vat_rate=22)
    result = compute_invoice(req)
    assert result.total == Decimal("12.20")


def test_accepts_dict_request():
    result = compute_invoice(_request(vat_rate="22"))
    assert result.total == Decimal("12.20")


def test_accepts_kwargs_with_aliases():
    result = compute_invoice(items=[_item()], vat="22", discount=0)
    assert result.total == Decimal("12.20")


def test_currency_case_normalized_via_kwargs():
    result = compute_invoice(items=[_item()], vat_rate=0, currency="usd")
    assert result.currency == "USD"


def test_missing_items_raises_invoice_validation_error():
    with pytest.raises(InvoiceValidationError):
        compute_invoice()
    with pytest.raises(ValueError):
        compute_invoice()


def test_invoice_validation_error_is_value_error():
    assert issubclass(InvoiceValidationError, ValueError)


def test_invalid_request_type_raises_type_error():
    with pytest.raises(TypeError):
        compute_invoice(request=12345, items=[_item()])


# ---------------------------------------------------------------------------
# Async in total API-ji
# ---------------------------------------------------------------------------


def test_async_calculate_invoice():
    result = _run(calculate_invoice(items=[_item()], vat_rate=22))
    assert isinstance(result, InvoiceResult)
    assert result.total == Decimal("12.20")


def test_calculate_total():
    total = _run(calculate_total(items=[_item()], vat_rate=22))
    assert total == Decimal("12.20")


def test_compute_total():
    assert compute_total(items=[_item()], vat_rate=22) == Decimal("12.20")


# ---------------------------------------------------------------------------
# Rezultat: lastnosti in sopomenke
# ---------------------------------------------------------------------------


def test_result_properties():
    result = compute_invoice(items=[_item()], vat_rate=22, discount_percent=10)
    assert result.net == result.taxable_amount
    assert result.vat == result.vat_amount
    assert result.discount == result.discount_amount


def test_result_rejects_extra_fields():
    with pytest.raises(ValidationError):
        InvoiceResult(
            currency="EUR",
            item_count=1,
            subtotal=Decimal("10.00"),
            discount_amount=Decimal("0.00"),
            taxable_amount=Decimal("10.00"),
            vat_amount=Decimal("0.00"),
            total=Decimal("10.00"),
            extra="x",
        )


def test_aliases():
    assert InvoiceLine is InvoiceItem
    assert Invoice is InvoiceRequest


# ---------------------------------------------------------------------------
# FastAPI integracija
# ---------------------------------------------------------------------------


def test_endpoint_returns_serialized_result():
    payload = InvoiceRequest(items=[_item()], vat_rate=22)
    response = _run(calculate_invoice_endpoint(payload))
    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "EUR"
    assert body["item_count"] == 1
    assert body["subtotal"] == "10.00"
    assert body["vat_amount"] == "2.20"
    assert body["total"] == "12.20"  # Decimal → str (mode="json")


try:
    from fastapi.testclient import TestClient
except ImportError:  # pragma: no cover — httpx ni nujno nameščen
    TestClient = None  # type: ignore[assignment]


@pytest.mark.skipif(TestClient is None, reason="TestClient (httpx) ni na voljo")
def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.skipif(TestClient is None, reason="TestClient (httpx) ni na voljo")
def test_calculate_endpoint_via_api():
    client = TestClient(app)
    response = client.post("/invoice/calculate", json=_request())
    assert response.status_code == 200
    assert response.json()["total"] == "12.20"


@pytest.mark.skipif(TestClient is None, reason="TestClient (httpx) ni na voljo")
def test_calculate_alias_endpoint_via_api():
    client = TestClient(app)
    response = client.post("/calculate", json=_request(vat_rate=0))
    assert response.status_code == 200
    assert response.json()["total"] == "10.00"


@pytest.mark.skipif(TestClient is None, reason="TestClient (httpx) ni na voljo")
def test_invalid_payload_returns_422():
    client = TestClient(app)
    response = client.post("/invoice/calculate", json={"items": []})
    assert response.status_code == 422
    assert response.json()["detail"] == "Neveljavni podatki zahteve."
