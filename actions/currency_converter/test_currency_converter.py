# Pytest Test Suite
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from fastapi import FastAPI

from .currency_converter import (
    convert_currency,
    validate_currency,
    validate_amount,
    EXCHANGE_RATES,
    SUPPORTED_CURRENCIES,
    CurrencyConversionError,
    UnsupportedCurrencyError,
    InvalidAmountError,
    InvertedRateError,
    InvertRateSanitizer,
)
from .schemas import ConversionRequest, ConversionResponse, ErrorResponse
from .main import router


# Create test app
app = FastAPI()
app.include_router(router)
client = TestClient(app)


# --- Unit Tests for validate_currency ---

class TestValidateCurrency:
    def test_valid_currency(self):
        assert validate_currency("usd") == "USD"
        assert validate_currency("EUR") == "EUR"
        assert validate_currency("  gbp  ") == "GBP"

    def test_invalid_currency(self):
        with pytest.raises(UnsupportedCurrencyError):
            validate_currency("XYZ")
        with pytest.raises(UnsupportedCurrencyError):
            validate_currency("")

    def test_non_string_currency(self):
        with pytest.raises(UnsupportedCurrencyError):
            validate_currency(123)
        with pytest.raises(UnsupportedCurrencyError):
            validate_currency(None)


# --- Unit Tests for validate_amount ---

class TestValidateAmount:
    def test_valid_amounts(self):
        assert validate_amount(100) == Decimal("100")
        assert validate_amount(100.50) == Decimal("100.50")
        assert validate_amount("50") == Decimal("50")
        assert validate_amount(Decimal("25.75")) == Decimal("25.75")

    def test_invalid_amounts(self):
        with pytest.raises(InvalidAmountError):
            validate_amount(0)
        with pytest.raises(InvalidAmountError):
            validate_amount(-100)
        with pytest.raises(InvalidAmountError):
            validate_amount("abc")
        with pytest.raises(InvalidAmountError):
            validate_amount(None)
        with pytest.raises(InvalidAmountError):
            validate_amount(float("inf"))
        with pytest.raises(InvalidAmountError):
            validate_amount(float("nan"))


# --- Unit Tests for convert_currency ---

class TestConvertCurrency:
    @pytest.mark.asyncio
    async def test_usd_to_eur(self):
        result = await convert_currency(100, "USD", "EUR")
        assert result == Decimal("85.00")

    @pytest.mark.asyncio
    async def test_eur_to_usd(self):
        result = await convert_currency(85, "EUR", "USD")
        assert result == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_usd_to_jpy(self):
        result = await convert_currency(100, "USD", "JPY")
        assert result == Decimal("11000.00")

    @pytest.mark.asyncio
    async def test_same_currency(self):
        result = await convert_currency(100, "USD", "USD")
        assert result == Decimal("100.00")

    @pytest.mark.asyncio
    async def test_custom_rates(self):
        custom_rates = {
            "USD": Decimal("1.0"),
            "EUR": Decimal("0.9"),
        }
        result = await convert_currency(100, "USD", "EUR", rates=custom_rates)
        assert result == Decimal("90.00")

    @pytest.mark.asyncio
    async def test_rounding(self):
        result = await convert_currency(100, "USD", "EUR")
        assert result == Decimal("85.00")

    @pytest.mark.asyncio
    async def test_invalid_currency(self):
        with pytest.raises(UnsupportedCurrencyError):
            await convert_currency(100, "XYZ", "USD")
        with pytest.raises(UnsupportedCurrencyError):
            await convert_currency(100, "USD", "XYZ")

    @pytest.mark.asyncio
    async def test_invalid_amount(self):
        with pytest.raises(InvalidAmountError):
            await convert_currency(0, "USD", "EUR")
        with pytest.raises(InvalidAmountError):
            await convert_currency(-100, "USD", "EUR")


# --- API Tests ---

class TestConvertAPI:
    def test_successful_conversion(self):
        response = client.post("/api/v1/convert", json={
            "amount": 100,
            "from_currency": "USD",
            "to_currency": "EUR"
        })
        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == 100
        assert data["from_currency"] == "USD"
        assert data["to_currency"] == "EUR"
        assert data["converted_amount"] == 85.0
        assert data["rate"] == 0.85

    def test_invalid_currency(self):
        response = client.post("/api/v1/convert", json={
            "amount": 100,
            "from_currency": "XYZ",
            "to_currency": "EUR"
        })
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "Unsupported currency"

    def test_invalid_amount(self):
        response = client.post("/api/v1/convert", json={
            "amount": -100,
            "from_currency": "USD",
            "to_currency": "EUR"
        })
        assert response.status_code == 422  # Pydantic schema validira amount > 0

    def test_validation_error(self):
        response = client.post("/api/v1/convert", json={
            "amount": "invalid",
            "from_currency": "USD",
            "to_currency": "EUR"
        })
        assert response.status_code == 422

    def test_missing_fields(self):
        response = client.post("/api/v1/convert", json={})
        assert response.status_code == 422

    def test_extra_fields(self):
        response = client.post("/api/v1/convert", json={
            "amount": 100,
            "from_currency": "USD",
            "to_currency": "EUR",
            "extra": "field"
        })
        assert response.status_code == 422


# --- Regression Tests: InvertRateSanitizer (absorbcija fix_currency_inverted_rate) ---

class TestInvertRateSanitizer:
    """Obrnjeni tečaji v custom tabelah se ujamejo pri viru, ne tiho zmotijo."""

    def test_ok_rates_pass_unchanged(self):
        custom_rates = {
            "USD": Decimal("1.0"),
            "EUR": Decimal("0.85"),
            "JPY": Decimal("110.0"),
        }
        result = InvertRateSanitizer().sanitize(custom_rates)
        assert result == custom_rates

    def test_inverted_eur_detected(self):
        # 0.85 EUR/USD je pravilen; 1.18 je recipročen (USD/EUR) → obrnjen.
        inverted = {"EUR": Decimal("1.18")}
        with pytest.raises(InvertedRateError):
            InvertRateSanitizer().sanitize(inverted)

    def test_inverted_jpy_detected(self):
        inverted = {"JPY": Decimal("0.0091")}  # reciprok od 110
        with pytest.raises(InvertedRateError):
            InvertRateSanitizer().sanitize(inverted)

    @pytest.mark.asyncio
    async def test_convert_currency_custom_inverted_raises(self):
        with pytest.raises(InvertedRateError):
            await convert_currency(
                100, "USD", "EUR",
                rates={"USD": Decimal("1.0"), "EUR": Decimal("1.18")},
            )

    def test_custom_reference_supported(self):
        # Reference po meri (npr. base: EUR) — vnos mora biti konsistenten z njo.
        sanitizer = InvertRateSanitizer(reference={"USD": Decimal("1.0"), "EUR": Decimal("0.85")})
        assert sanitizer.sanitize({"USD": Decimal("1.0"), "EUR": Decimal("0.85")})

    def test_default_rates_not_touched(self):
        # Privzete tečaje jedra vhodna strategija pusti nedotaknjene.
        assert InvertRateSanitizer().sanitize(dict(EXCHANGE_RATES)) == dict(EXCHANGE_RATES)


# --- Schema Tests ---

class TestSchemas:
    def test_conversion_request_valid(self):
        request = ConversionRequest(amount=100, from_currency="usd", to_currency="eur")
        assert request.amount == 100
        assert request.from_currency == "USD"
        assert request.to_currency == "EUR"

    def test_conversion_request_invalid_amount(self):
        with pytest.raises(ValueError):
            ConversionRequest(amount=0, from_currency="USD", to_currency="EUR")

    def test_conversion_request_invalid_currency(self):
        with pytest.raises(ValueError):
            ConversionRequest(amount=100, from_currency="US1", to_currency="EUR")

    def test_conversion_response_valid(self):
        response = ConversionResponse(
            amount=100,
            from_currency="USD",
            to_currency="EUR",
            converted_amount=85.0,
            rate=0.85
        )
        assert response.amount == 100
        assert response.converted_amount == 85.0

    def test_error_response_valid(self):
        error = ErrorResponse(error="Test error", detail="Test detail")
        assert error.error == "Test error"
        assert error.detail == "Test detail"