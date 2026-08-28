# Core Domain Logic
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, Optional

# Fixed exchange rates (base: USD)
EXCHANGE_RATES: Dict[str, Decimal] = {
    "USD": Decimal("1.0"),
    "EUR": Decimal("0.85"),
    "GBP": Decimal("0.75"),
    "JPY": Decimal("110.0"),
    "CHF": Decimal("0.92"),
    "CAD": Decimal("1.25"),
    "AUD": Decimal("1.35"),
    "CNY": Decimal("6.45"),
}

SUPPORTED_CURRENCIES = set(EXCHANGE_RATES.keys())


class CurrencyConversionError(Exception):
    """Base exception for currency conversion errors."""
    pass


class UnsupportedCurrencyError(CurrencyConversionError):
    """Raised when a currency is not supported."""
    pass


class InvalidAmountError(CurrencyConversionError):
    """Raised when the amount is invalid (non-positive or non-numeric)."""
    pass


class InvertedRateError(CurrencyConversionError):
    """Raised when a custom rate table looks inverted relative to the base rates.

    Arhitekturna konsolidacija nekdanjega `fix_currency_inverted_rate`: namesto
    samostojne "patch" Action je detekcija obrnjenih tečajev zdaj notranja
    strategija jedra (`InvertRateSanitizer`). Neveljaven vhod se ujame pri viru,
    ne tiho zmoti pretvorbe.
    """
    pass


def validate_currency(currency: str) -> str:
    """Validate that a currency code is supported."""
    if not isinstance(currency, str):
        raise UnsupportedCurrencyError(f"Currency must be a string, got {type(currency).__name__}")
    currency = currency.upper().strip()
    if currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(
            f"Unsupported currency: {currency}. Supported currencies: {', '.join(sorted(SUPPORTED_CURRENCIES))}"
        )
    return currency


def validate_amount(amount) -> Decimal:
    """Validate that an amount is a positive number."""
    try:
        amount_decimal = Decimal(str(amount))
    except (ValueError, TypeError, InvalidOperation):
        raise InvalidAmountError(f"Invalid amount: {amount}. Amount must be a valid number.")

    if not amount_decimal.is_finite():
        raise InvalidAmountError(f"Invalid amount: {amount}. Amount must be finite.")

    if amount_decimal <= 0:
        raise InvalidAmountError(f"Invalid amount: {amount}. Amount must be positive.")

    return amount_decimal


class InvertRateSanitizer:
    """Defenzivna strategija: zazna obrnjene tečaje v custom rate tabelah.

    Bug razred, ki ga je nekoč krpal samostojen ``fix_currency_inverted_rate``
    (tečaj podan kot recipročna vrednost), se zdaj lovi tukaj. Če je vrednost v
    custom tabeli bližje reciproku referenčnega tečaja kot samemu tečaju, je
    vnos skoraj zagotovo obrnjen — namesto tihe napačne pretvorbe dvignemo
    ``InvertedRateError``.
    """

    def __init__(self, reference: Optional[Dict[str, Decimal]] = None):
        # Referenca = bazne tečaje jedra (base: USD); korekcija na 1.0 za base.
        ref = dict(reference) if reference is not None else dict(EXCHANGE_RATES)
        ref.setdefault("USD", Decimal("1.0"))
        self.reference = {k: Decimal(v) for k, v in ref.items() if Decimal(v) > 0}

    def sanitize(self, rates: Dict[str, Decimal]) -> Dict[str, Decimal]:
        """Preveri vsako valuto v ``rates`` proti referenci; dvigne ob obratu.

        Args:
            rates: custom tečajna tabela (ključi = kode valut, vrednosti = Decimal).

        Returns:
            Nespremenjeno ``rates``, če je tabela konsistentna z referenco.

        Raises:
            InvertedRateError: če je kateri od vnosov obrnjen glede na referenco.
        """
        for currency, value in rates.items():
            ref_rate = self.reference.get(currency.upper())
            if ref_rate is None or ref_rate <= 0:
                continue
            value = Decimal(value)
            if value <= 0:
                continue
            reciprocal = Decimal(1) / ref_rate
            # Obrnjen vnos je bližje reciproku kot pravemu tečaju.
            if abs(value - reciprocal) < abs(value - ref_rate):
                raise InvertedRateError(
                    f"Inverted rate for '{currency}': {value} looks like the "
                    f"reciprocal of expected {ref_rate} (expected ≈ {reciprocal})."
                )
        return rates


async def convert_currency(
    amount,
    from_currency: str,
    to_currency: str,
    rates: Optional[Dict[str, Decimal]] = None
) -> Decimal:
    """
    Convert an amount from one currency to another using fixed exchange rates.
    
    Args:
        amount: The amount to convert (must be positive).
        from_currency: Source currency code (e.g., "USD").
        to_currency: Target currency code (e.g., "EUR").
        rates: Optional custom exchange rates dictionary (defaults to EXCHANGE_RATES).
    
    Returns:
        Decimal: The converted amount rounded to 2 decimal places.
    
    Raises:
        UnsupportedCurrencyError: If either currency is not supported.
        InvalidAmountError: If the amount is not positive or not a valid number.
    """
    # Use default rates if not provided
    if rates is None:
        rates = EXCHANGE_RATES
    else:
        # Custom tabela → defenzivna strategija: ulovi obrnjene tečaje pri viru
        # (arhitekturna absorbcija nekdanjega fix_currency_inverted_rate).
        InvertRateSanitizer().sanitize(rates)

    # Validate inputs
    from_currency = validate_currency(from_currency)
    to_currency = validate_currency(to_currency)
    amount_decimal = validate_amount(amount)
    
    # Perform conversion: amount * (rate_to / rate_from)
    rate_from = rates[from_currency]
    rate_to = rates[to_currency]
    
    # Convert to base (USD) then to target
    converted = amount_decimal * (rate_to / rate_from)
    
    # Round to 2 decimal places
    return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)