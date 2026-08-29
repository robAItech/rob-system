"""Pydantic V2 schemas for governance_policy_enforcer (policy, context, decision)."""

from __future__ import annotations

import re
from datetime import datetime
from ipaddress import ip_address, ip_network
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def _validate_time_value(value: str) -> str:
    """Validate a strict HH:MM 24h time string and return it unchanged."""
    if not _TIME_RE.match(value):
        raise ValueError(f"invalid time {value!r}, expected HH:MM in 24h format")
    datetime.strptime(value, "%H:%M")  # defensive: must parse as a real time
    return value


def _validate_ip_value(value: str) -> str:
    """Validate an IP address or CIDR network string and return it unchanged."""
    try:
        if "/" in value:
            ip_network(value, strict=False)
        else:
            ip_address(value)
    except ValueError:
        raise ValueError(f"invalid IP or CIDR: {value!r}") from None
    return value


class Context(BaseModel):
    """Runtime context for ABAC evaluation (IP, time window, attributes)."""

    model_config = ConfigDict(strict=True)

    ip: Optional[str] = None
    time: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None

    @field_validator("ip")
    @classmethod
    def _validate_ip(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_ip_value(value)

    @field_validator("time")
    @classmethod
    def _validate_time(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_time_value(value)


class ContextCondition(BaseModel):
    """Optional ABAC condition attached to a rule (IP allowlist, time window, attributes)."""

    model_config = ConfigDict(strict=True)

    allowed_ips: Optional[List[str]] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    required_attributes: Optional[Dict[str, str]] = None

    @field_validator("allowed_ips")
    @classmethod
    def _validate_allowed_ips(cls, value: Optional[List[str]]) -> Optional[List[str]]:
        if value is None:
            return value
        return [_validate_ip_value(entry) for entry in value]

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_time(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value
        return _validate_time_value(value)

    def evaluate(self, context: Optional[Context]) -> bool:
        """Return True iff the given runtime context satisfies this condition."""
        if isinstance(context, dict):
            context = Context(**context)
        if context is None:
            return not (
                self.allowed_ips or self.start_time or self.end_time or self.required_attributes
            )
        if self.allowed_ips is not None:
            if context.ip is None or not self._ip_allowed(context.ip):
                return False
        if self.start_time or self.end_time:
            if context.time is None:
                return False
            if not self._time_allowed(context.time):
                return False
        if self.required_attributes:
            attrs = context.attributes or {}
            if any(attrs.get(key) != value for key, value in self.required_attributes.items()):
                return False
        return True

    def _ip_allowed(self, ip: str) -> bool:
        addr = ip_address(ip)
        for entry in self.allowed_ips or ():
            if "/" in entry:
                if addr in ip_network(entry, strict=False):
                    return True
            elif ip == entry:
                return True
        return False

    def _time_allowed(self, time_value: str) -> bool:
        now = datetime.strptime(time_value, "%H:%M").time()
        start = datetime.strptime(self.start_time, "%H:%M").time() if self.start_time else None
        end = datetime.strptime(self.end_time, "%H:%M").time() if self.end_time else None
        if start is not None and end is not None:
            if start <= end:
                return start <= now <= end
            return now >= start or now <= end  # window crosses midnight
        if start is not None:
            return now >= start
        if end is not None:
            return now <= end
        return True


class PolicyRule(BaseModel):
    """A single RBAC/ABAC rule in declarative policy form."""

    model_config = ConfigDict(strict=True)

    role: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    effect: Literal["allow", "deny"] = "allow"
    condition: Optional[ContextCondition] = None


class Policy(BaseModel):
    """A named collection of rules."""

    model_config = ConfigDict(strict=True)

    name: str = Field(min_length=1)
    rules: List[PolicyRule] = Field(default_factory=list)


class Decision(BaseModel):
    """Result of an authorization evaluation."""

    model_config = ConfigDict(strict=True)

    allowed: bool
    role: str
    action: str
    resource: str
    reason: str
    rule: Optional[str] = None


class EvaluationRequest(BaseModel):
    """Payload for the /evaluate endpoint."""

    model_config = ConfigDict(strict=True)

    role: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource: str = Field(min_length=1)
    context: Optional[Context] = None