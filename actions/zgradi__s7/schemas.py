"""schemas.py — Pydantic V2 sheme za integracijski sistem zgradi__s7.

Strogi validatorji:
  * ``strict=True``  — brez tihe koercije tipov (int ne postane str, itd.)
  * ``extra="forbid"`` — neznana polja so zavrnjena
  * eksplicitni validatorji — robni pogoji (imena, semver, duplikati, praznine)
"""

import re
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Dovoli tudi paketna imena z vodilnim podčrtajem (npr. "__init__").
MODULE_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{0,63}$")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


class ModuleStatus(str, Enum):
    """Življenjsko stanje modula v integracijskem sistemu."""

    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class IntegrationPhase(str, Enum):
    """Faze, skozi katere mora modul preiti, da je del povezanega sistema."""

    SCHEMA = "schema"
    LOGIC = "logic"
    API = "api"
    TESTS = "tests"
    DONE = "done"


def _coerce_enum(enum_cls, value, field_name: str):
    """Pretvori surovo vrednost (npr. iz JSON-a) v člana enuma ali vrže napako."""
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        try:
            return enum_cls(value)
        except ValueError:
            raise ValueError(f"neznana vrednost za {field_name}: {value!r}")
    raise ValueError(f"{field_name} mora biti niz ali član enuma")


class ModuleSpec(BaseModel):
    """Opis enega modula, ki ga želimo integrirati."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    version: str
    status: ModuleStatus = ModuleStatus.PENDING
    phases: List[IntegrationPhase] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, value):
        return _coerce_enum(ModuleStatus, value, "status")

    @field_validator("phases", mode="before")
    @classmethod
    def _coerce_phases(cls, value):
        if isinstance(value, (list, tuple)):
            return [_coerce_enum(IntegrationPhase, item, "phases") for item in value]
        raise ValueError("phases mora biti seznam faz")

    @field_validator("name")
    @classmethod
    def _check_name(cls, value: str) -> str:
        if not MODULE_NAME_RE.fullmatch(value):
            raise ValueError("ime modula mora ustrezati [a-z_][a-z0-9_]* (1–64 znakov)")
        return value

    @field_validator("version")
    @classmethod
    def _check_version(cls, value: str) -> str:
        if not SEMVER_RE.fullmatch(value):
            raise ValueError("verzija mora biti semver X.Y.Z")
        return value

    @field_validator("phases")
    @classmethod
    def _check_phases_unique(cls, value: List[IntegrationPhase]) -> List[IntegrationPhase]:
        if len(value) != len(set(value)):
            raise ValueError("phases ne sme vsebovati duplikatov")
        return value


class IntegrationRequest(BaseModel):
    """Zahtevek za integracijo modulov v povezan sistem."""

    model_config = ConfigDict(strict=True, extra="forbid")

    modules: List[ModuleSpec] = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=512)

    @field_validator("modules")
    @classmethod
    def _check_unique_modules(cls, value: List[ModuleSpec]) -> List[ModuleSpec]:
        seen = set()
        duplicates = set()
        for module in value:
            if module.name in seen:
                duplicates.add(module.name)
            seen.add(module.name)
        if duplicates:
            raise ValueError("podvojeni moduli: " + ", ".join(sorted(duplicates)))
        return value


class IntegrationIssue(BaseModel):
    """Ena težava, odkrita med integracijo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    module: str
    phase: IntegrationPhase
    message: str

    @field_validator("phase", mode="before")
    @classmethod
    def _coerce_phase(cls, value):
        return _coerce_enum(IntegrationPhase, value, "phase")

    @field_validator("module", "message")
    @classmethod
    def _check_not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("polje ne sme biti prazno")
        return value


class IntegrationResult(BaseModel):
    """Rezultat integracije: uspeh, integrirani moduli, težave in poročilo."""

    model_config = ConfigDict(strict=True, extra="forbid")

    ok: bool
    integrated: List[str] = Field(default_factory=list)
    issues: List[IntegrationIssue] = Field(default_factory=list)
    report: str = ""
