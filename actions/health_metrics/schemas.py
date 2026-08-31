"""Pydantic V2 sheme za modul health_metrics.

Vse sheme uporabljajo strogo validacijo (``ConfigDict(strict=True)``)
in stroge validatorje — ne veljajo implicitne konverzije tipov.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_DEFAULT_STATE = "unknown"


class DaemonState(BaseModel):
    """Stanje daemona: ``state`` + čas zadnjega srčnega utripa."""

    model_config = ConfigDict(strict=True)

    state: str = Field(default=_DEFAULT_STATE, min_length=1)
    heartbeat_ts: Optional[str] = None

    @field_validator("state")
    @classmethod
    def _state_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("state must not be blank")
        return value


class AgendaCounts(BaseModel):
    """Števci agende po statusih — nenegativna cela števila."""

    model_config = ConfigDict(strict=True)

    pending: int = Field(default=0, ge=0)
    done: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)

    @field_validator("pending", "done", "failed")
    @classmethod
    def _counts_non_negative(cls, value: int) -> int:
        if value < 0:
            raise ValueError("counts must be non-negative")
        return value


class HealthMetrics(BaseModel):
    """Celoten rezultat metrik, kot ga vrača ``collect_metrics()``."""

    model_config = ConfigDict(strict=True)

    daemon: DaemonState
    agenda: AgendaCounts
    healthy: bool