"""pii_masking_sanitizer — jedro domenske logike: PII maskiranje (GDPR/HIPAA).

Kot predlaga arhitekturna revizija (2026): domenski moduli (`invoice_calc`,
`warehouse_inventory`, `report_builder`) obdelujejo osebne podatke; ta modul
doda enoten maskirni sloj:
  - registracija PII-polj prek dekoratorja ``@PII("email")`` ali ročno,
  - deterministično maskiranje (mask / partial / tokenize) — ista vrednost +
    isti secret → isti token,
  - redakcija prostega besedila (e-pošta, telefon, IBAN) z regex-i,
  - politika na nivoju kategorije.

Vse je čisto in uporablja samo standardno knjižnico.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

#: Vrste maskirnih strategij.
MASKS = ("mask", "partial", "tokenize", "redact")

#: Redakcijski vzorci za prosto besedilo.
#: Vrstni red ključev JE pomemben: najprej IBAN (specifičnejši, dovoljuje
#: presledke), nato telefon (sicer ujame števke znotraj IBAN-a), nazadnje email.
REDACTION_PATTERNS: Dict[str, str] = {
    "iban": r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){9,29}[A-Z0-9]\b",
    "phone": r"\+?\d[\d\s\-]{7,}\d",
    "email": r"[\w.+-]+@[\w-]+\.[\w.-]+",
}


class PIICategory(str):
    """Kategorija osebnega podatka (npr. email, iban, phone, ssn)."""


@dataclass(frozen=True)
class PIIField:
    """Registrirano PII polje: ime + kategorija + strategija."""

    name: str
    category: str
    strategy: str = "mask"

    def __post_init__(self) -> None:
        if self.strategy not in MASKS:
            raise ValueError(f"neznana strategija: {self.strategy}")


class PII:
    """Dekorator za označevanje PII-polj na shemi/modelu.

    ```python
    class User(BaseModel):
        name: str
        email: str = PII("email", strategy="partial")
    ```
    """

    def __init__(self, category: str, strategy: str = "mask"):
        if strategy not in MASKS:
            raise ValueError(f"neznana strategija: {strategy}")
        self.category = category
        self.strategy = strategy


class PIIMasker:
    """Maskiranje/tokenizacija PII podatkov (deterministično z secret-om)."""

    def __init__(self, secret: str = "dev-pii-secret"):
        self.secret = secret
        self.fields: Dict[str, PIIField] = {}

    # ── Registracija ────────────────────────────────────────────────────────
    def register_field(self, name: str, category: str, strategy: str = "mask") -> PIIField:
        """Registriraj PII polje (ročno ali iz dekoratorja)."""
        field = PIIField(name=name, category=category, strategy=strategy)
        self.fields[name] = field
        return field

    def register_schema(self, schema_type: type) -> List[PIIField]:
        """Registriraj vsa polja označena z ``PII(...)`` dekoratorjem.

        Zajame tako anotirana polja (``email: PII = PII("email")``) kot polja
        brez anotacij (``email = PII("email")``).
        """
        registered: List[PIIField] = []

        def _add(name: str, marker: PII) -> None:
            self.register_field(name, marker.category, marker.strategy)
            registered.append(self.fields[name])

        # (a) Vsi class atributi, ki so PII instance.
        for name, value in vars(schema_type).items():
            if isinstance(value, PII):
                _add(name, value)
        # (b) Anotirana polja, kjer je anotacija ali privzeta vrednost PII.
        for name, annotation in getattr(schema_type, "__annotations__", {}).items():
            if isinstance(annotation, PII):
                _add(name, annotation)
            elif isinstance(getattr(schema_type, name, None), PII):
                _add(name, getattr(schema_type, name))
        return registered

    # ── Tokenizacija (deterministična) ──────────────────────────────────────
    def tokenize(self, value: str, category: str) -> str:
        """Determinističen token: HMAC(value, secret) skrajšan, s prefix kategorije."""
        digest = hmac.new(
            f"{self.secret}:{category}".encode(), str(value).encode(), hashlib.sha256
        ).hexdigest()[:16]
        return f"tok_{category[:4]}_{digest}"

    # ── Eno polje ───────────────────────────────────────────────────────────
    def mask_value(self, name: str, value: Any) -> Any:
        """Maskiraj vrednost po registrirani strategiji; neregistrirano = nespremenjeno."""
        field = self.fields.get(name)
        if field is None or value is None:
            return value
        text = str(value)
        if field.strategy == "mask":
            return "***"
        if field.strategy == "redact":
            return self.redact_text(text)
        if field.strategy == "tokenize":
            return self.tokenize(text, field.category)
        if field.strategy == "partial":
            if len(text) <= 4:
                return "****"
            return f"{text[:2]}***{text[-2:]}"
        return value

    # ── Rekurzivno maskiranje objekta ───────────────────────────────────────
    def mask(self, obj: Any) -> Any:
        """Rekurzivno maskiraj registrirana PII polja v dict/list/objektu."""
        if isinstance(obj, dict):
            return {k: self.mask_value(k, self.mask(v)) if k in self.fields else self.mask(v)
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.mask(item) for item in obj]
        if isinstance(obj, tuple):
            return tuple(self.mask(item) for item in obj)
        return obj

    # ── Redakcija prostega besedila ─────────────────────────────────────────
    def redact_text(self, text: str, patterns: Optional[Dict[str, str]] = None) -> str:
        """Zamenjaj e-pošte/telefone/IBAN v besedilu z maskami."""
        result = text
        for category, pattern in (patterns or REDACTION_PATTERNS).items():
            result = re.sub(pattern, f"[{category}-REDACTED]", result)
        return result


__all__ = ["PII", "PIIField", "PIIMasker", "PIICategory", "MASKS", "REDACTION_PATTERNS"]
