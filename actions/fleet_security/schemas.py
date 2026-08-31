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
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

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
    # Phase 2 — operator monitor (telemetry/egress najdbe v ISTI findings tok).
    "telemetry_anomaly",
    "unknown_egress",
    "egress_anomaly",
    # Phase 3 — premium moduli (vsi SIMULACIJA / pasivno-only).
    "redteam_injection",
    "model_changed",
    "model_unverified",
    "known_vulnerability",
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


# ------------------------------------------------------------------ #
#  Phase 2 — operator monitor (telemetry + omrežne opazke)
# ------------------------------------------------------------------ #
class TelemetrySample(BaseModel):
    """Pasiven telemetry vzorec naprave (device-reported, nikoli probed).

    ``metrics`` so imenovane skalarne vrednosti (cpu_pct, mem_pct, ...).
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    device_id: StrictText
    ts: int | None = None                       # device epoch; server stampa, če ni
    source: str = Field(default="device", max_length=64)
    metrics: dict[str, float] = Field(default_factory=dict)


class NetworkObservation(BaseModel):
    """Pasivna omrežna opazka (dst tuple iz logov/netstat; nikoli skenirano).

    Vsaj eden od ``dst_host``/``dst_ip`` naj bo podan; ``dst_ip`` se validira
    prek ``ipaddress``.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    device_id: StrictText
    ts: int | None = None
    dst_host: str | None = Field(default=None, max_length=253)
    dst_ip: str | None = Field(default=None, max_length=45)
    dst_port: int | None = Field(default=None, ge=1, le=65535)
    proto: str | None = Field(default=None, max_length=16)

    @field_validator("dst_ip")
    @classmethod
    def _valid_ip(cls, v: str | None) -> str | None:
        if v is None:
            return None
        from ipaddress import ip_address

        try:
            ip_address(v)
        except ValueError:
            raise ValueError(f"invalid dst_ip: {v!r}") from None
        return v


# ------------------------------------------------------------------ #
#  Phase 3 — threat intel + red team + supply chain
# ------------------------------------------------------------------ #
class VulnerabilityAdvisory(BaseModel):
    """Ena ranljivost iz threat intel feeda (seed JSON, module-relative).

    ``affected_versions`` = ekspliciten seznam; ``fixed_in`` = range za vse
    nižje. Oboje prazno → advisory ni nikoli affected.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    cve_id: StrictText
    component: StrictText                     # sovpada s firmware komponento / os.name / model.name
    affected_versions: list[str] = Field(default_factory=list)
    fixed_in: str = Field(default="", max_length=200)
    cvss_score: float = Field(ge=0, le=10)
    severity: str = Field(default="info", max_length=16)   # seed metadata
    title: str = Field(default="", max_length=300)


class RedTeamRunRequest(BaseModel):
    """Zahteva za red-team pass (SIMULACIJA samo — MockBrain)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    robot_id: StrictText
    system_prompt: str = ""
    policy: list[str] | None = None           # prepovedane fraze; None = privzeti seznam
    payload_ids: list[str] | None = None      # None = celoten PAYLOAD_LIBRARY
    mock_mode: Literal["secure", "naive"] = "naive"


class PromptHardeningRequest(BaseModel):
    """Zahteva za prompt hardening (+ opcijski remediacijski PR)."""

    model_config = ConfigDict(strict=True, extra="forbid")

    robot_id: StrictText
    system_prompt: str
    dry_run: bool = True


class ModelRecordRequest(BaseModel):
    """Eksplicitna registracija modela v provenance registry."""

    model_config = ConfigDict(strict=True, extra="forbid")

    device_id: StrictText
    model: ModelInfo
    pushed_by: str | None = None
    pushed_at: int | None = None
    repo_url: str | None = None


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
