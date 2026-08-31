"""fleet_security — Pydantic V2 sheme (pasivno jedro robotske flote).

Inventar naprav, posture scoring, CRA skladnostni report in config/network
remediacijski PR. Trda pravila (CEO review 2026-08-31):

- **Pasivno-prvi**: input modeli so ``strict`` in ``extra="forbid"`` —
  neznana polja / napačni tipi se zavrnejo na ingest robu.
- **Remediacija = config/network policy SAMO**; firmware je report-only
  (fix gre skozi OEM).
- **PR se nikoli ne auto-merge-a** (human-in-the-loop).

Deterministično, brez LLM.
"""

from __future__ import annotations

from typing import Any, Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

#: Ne-prazn, strict string za identifikatorje (device_id, hostname, ...).
StrictText = Annotated[str, StringConstraints(strict=True, min_length=1)]


# ------------------------------------------------------------------ #
#  Inventar naprav
# ------------------------------------------------------------------ #
class OSInfo(BaseModel):
    """Operacijski sistem naprave (name/version/kernel)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: StrictText                       # "windows" | "linux" | "darwin"
    version: str = Field(default="", max_length=200)
    kernel: str = Field(default="", max_length=200)


class FirmwareInfo(BaseModel):
    """Ena firmware komponenta naprave (npr. motor-controller, bios, mcus)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    component: StrictText
    version: str = Field(default="", max_length=200)


class ModelInfo(BaseModel):
    """AI model na napravi (npr. lokalni LLM/vizijski model)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    name: StrictText
    version: str = Field(default="", max_length=200)
    provider: str = Field(default="", max_length=200)   # OEM / provider
    sha256: str = Field(default="", max_length=64)      # artifact hash; "" = unknown


class HostInfo(BaseModel):
    """Ingest payload — naprava sama sporoči svoj state (pasivno)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    device_id: StrictText
    hostname: StrictText
    role: str = Field(default="standalone", pattern=r"^(master|worker|standalone)$")
    os: OSInfo
    firmware: list[FirmwareInfo] = Field(default_factory=list)
    model: ModelInfo | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="local-collector", max_length=64)
    collected_at: int | None = None         # device epoch ts; server stampa, če ni


class Device(BaseModel):
    """Shranjena/persistirana naprava (inventar)."""

    device_id: StrictText
    hostname: StrictText
    role: str
    os: OSInfo
    firmware: list[FirmwareInfo]
    model: ModelInfo | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    source: str = ""
    first_seen_ts: int
    last_seen_ts: int


# ------------------------------------------------------------------ #
#  Posture (najdbe + ocena)
# ------------------------------------------------------------------ #
POSTURE_CATEGORIES = (
    "os_version_drift",
    "firmware_drift",
    "firmware_unknown",
    "model_provenance",
    "config_drift",
    "stale_heartbeat",
    "missing_device",
)
SEVERITIES = ("critical", "high", "medium", "low")


class PostureFinding(BaseModel):
    """Ena odprta/rešena najdba na napravi."""

    id: int | None = None
    device_id: StrictText
    category: str = Field(..., pattern="|".join(POSTURE_CATEGORIES))
    severity: str = Field(..., pattern="|".join(SEVERITIES))
    status: Literal["open", "resolved"] = "open"
    detail: str
    detected_at: int
    resolved_at: int | None = None


class PostureScore(BaseModel):
    """Posture ocena naprave (0–100) + grade (A–F) za en pass."""

    device_id: StrictText
    score: int = Field(ge=0, le=100)
    grade: str = Field(pattern=r"^[A-F]$")
    counts: dict[str, int] = Field(default_factory=dict)   # severity -> count
    assessed_at: int


#: Sentinel: "ključ MORA obstajati (poljubna vrednost)" v baseline zahtevah.
ANY_VALUE = object()


class Baseline(BaseModel):
    """Ciljno (desired-state) stanje za role — osnova posture scoringa."""

    model_config = ConfigDict(strict=True, extra="forbid")

    role: str = Field(pattern=r"^(master|worker|standalone)$")
    os_name: str | None = None
    os_version: str | None = None
    os_kernel: str | None = None
    firmware: dict[str, str] = Field(default_factory=dict)   # component -> expected version
    model_name: str | None = None
    model_version: str | None = None
    model_sha256: list[str] = Field(default_factory=list)    # known-good hashes
    # key -> pričakovana vrednost ALI ANY_VALUE ("mora obstajati").
    required_config_keys: dict[str, Any] = Field(default_factory=dict)
    # key -> vrednost, ki pomeni INSECURE default (če se ujema → critical).
    secure_default_checks: dict[str, Any] = Field(default_factory=dict)
    heartbeat_max_age_seconds: int = 300

    def to_jsonable(self) -> dict:
        """Serializacija za SQLite JSON stolpec (ANY_VALUE -> "__ANY__")."""
        return {
            "role": self.role,
            "os_name": self.os_name,
            "os_version": self.os_version,
            "os_kernel": self.os_kernel,
            "firmware": self.firmware,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "model_sha256": self.model_sha256,
            "required_config_keys": {
                k: (_ANY_TOKEN if v is ANY_VALUE else v)
                for k, v in self.required_config_keys.items()
            },
            "secure_default_checks": self.secure_default_checks,
            "heartbeat_max_age_seconds": self.heartbeat_max_age_seconds,
        }

    @classmethod
    def from_jsonable(cls, data: dict) -> "Baseline":
        """Deserializacija iz SQLite ("__ANY__" -> ANY_VALUE)."""
        req = dict(data.get("required_config_keys") or {})
        return cls(
            **{
                **data,
                "required_config_keys": {
                    k: (ANY_VALUE if v == _ANY_TOKEN else v) for k, v in req.items()
                },
            }
        )


_ANY_TOKEN = "__ANY__"


# ------------------------------------------------------------------ #
#  CRA skladnost + remediacija
# ------------------------------------------------------------------ #
class ComplianceReportSection(BaseModel):
    """Ena CRA zahteva v reportu: status + dokazi."""

    requirement_id: str
    title: str
    annex_ref: str
    status: Literal["compliant", "non_compliant", "partial", "not_applicable"]
    evidence: list[str] = Field(default_factory=list)
    related_findings: list[str] = Field(default_factory=list)


class RemediationRequest(BaseModel):
    """Zahteva za remediacijski PR (config/network policy SAMO)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    device_id: StrictText
    kind: Literal["config", "network_policy"] = "config"
    dry_run: bool = True


class RemediationResult(BaseModel):
    """Izid remediacije — dry-run diff ali odprt PR."""

    device_id: str
    kind: str
    diff: str = ""
    branch: str | None = None
    commit: str | None = None
    pr_url: str | None = None
    status: Literal["no_change", "diff_generated", "pr_open", "error"]
    message: str = ""
