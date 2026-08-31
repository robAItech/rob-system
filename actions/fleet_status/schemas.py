"""Pydantic V2 sheme za modul fleet_status.

Sheme so stroge: zavržejo dodatne ključe (extra="forbid"), prazna stanja
in neštevilske timestamp-e. Pri workerjih je veljaven tako neposreden
številski `last_seen` kot oblika `{"last_seen": <ts>}`.
"""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, field_validator


class DaemonStatus(BaseModel):
    """Stanje daemona: `state` in `heartbeat_ts`.

    `extra="ignore"` — realni `daemon.json` vsebuje tudi `pid`, `jobs`,
    `last_run_summary` itd.; modul rabi samo state + heartbeat_ts, ostalo
    se ignorira (če bi bilo `forbid`, bi realni podatki zrušili validacijo).
    """

    model_config = ConfigDict(extra="ignore")

    state: str
    heartbeat_ts: Optional[float] = None

    @field_validator("state")
    @classmethod
    def state_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("state must not be empty")
        return value

    @field_validator("heartbeat_ts", mode="before")
    @classmethod
    def coerce_heartbeat_ts(cls, value):
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("heartbeat_ts must be numeric") from exc


class FleetStatus(BaseModel):
    """Celoten pogled na floto: daemon + workerji."""

    model_config = ConfigDict(extra="forbid")

    daemon: DaemonStatus
    workers: Dict[str, Optional[float]] = {}

    @field_validator("workers", mode="before")
    @classmethod
    def coerce_workers(cls, value):
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("workers must be a JSON object")
        out: Dict[str, Optional[float]] = {}
        for name, raw in value.items():
            if isinstance(raw, dict):
                raw = raw.get("last_seen")
            if raw is None:
                out[name] = None
                continue
            try:
                out[name] = float(raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"last_seen for worker {name!r} must be numeric"
                ) from exc
        return out