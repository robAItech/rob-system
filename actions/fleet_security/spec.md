# fleet_security — Phase 1 passive core (robot fleet security)

**Niche (CEO review 2026-08-31):** Robot fleet security platform. EU Cyber
Resilience Act kot prodajni klin. Phase 1 = deljeno pasivno jedro, ki ga bosta
uporabila oba skin-a (operator monitor + OEM embed) v Phase 2.

## Trda pravila
1. **Pasivno-prvi.** Nobenega aktivnega skeniranja/probe-a. Jedro LE sprejema
   `HostInfo` snapshote (HTTP ingest ali status datoteke).
2. **Remediacija = config/network policy SAMO.** Firmware je report-only;
   fix gre skozi OEM. PR se nikoli ne auto-merge-a (human-in-the-loop).
3. **OT podatki on-prem.** DB/inventar/najdbe v `.rob_ai/` (gitignored).
4. **Zero silent failures.** Vsak ingest/scan/find/remediate piše audit event
   prek `core/audit.py`.

## Moduli
| modul | odgovornost |
|---|---|
| `schemas.py` | Pydantic V2 modeli (HostInfo/Device/Finding/Score/Baseline/...); strict inputi |
| `store.py` | SQLite (stdlib, WAL) — fs_devices/findings/scores/baselines/remediations |
| `discovery.py` | `collect_local_hostinfo` (stdlib fingerprint), `ingest_hostinfo`, `check_heartbeats` |
| `posture.py` | `assess_device` (čisto), `run_assessment`, `compute_score`, eskalacija, regression |
| `compliance.py` | CRA Annex I kurirana preslikava → Markdown/JSON report, PII redakcija |
| `remediation.py` | `generate_fix` (config/network), `open_remediation_pr` (gh/GitHub API) |
| `main.py` | FastAPI router + app (`/api/fleet-security/*`) |
| `cli.py` | `python -m actions.fleet_security.cli ingest|assess|report|remediate|pr` |

## Scoring
`score = max(0, 100 − Σ severity_weights nad OPEN najdbami)`; weights
critical=25/high=15/medium=8/low=3 (override: `FS_SEVERITY_WEIGHTS`); grade
A≥90/B≥80/C≥70/D≥60/F<60. Pod `FS_SCORE_ESCALATE_BELOW` (60) → eskalacija.

## Kategorije najdb
`os_version_drift`(high) · `firmware_drift`(high) · `firmware_unknown`(medium)
· `model_provenance`(medium) · `config_drift`(high; insecure default →
critical) · `stale_heartbeat`(high) · `missing_device`(critical).

## Config (core/config.py)
`FS_*` env: `FS_PASSIVE_ONLY`, `FS_DB_PATH`, `FS_BASELINES_DIR`,
`FS_HEARTBEAT_MAX_AGE_SECONDS`, `FS_SCORE_ESCALATE_BELOW`,
`FS_REGRESSION_DROP_POINTS`, `FS_SEVERITY_WEIGHTS`, `FS_PR_OWNER/REPO/BASE_BRANCH/TOKEN/AUTO_MERGE`,
`FS_DESIRED_STATE_DIR`.

## API
`POST /devices/ingest` · `GET /devices` · `GET /devices/{id}` · `POST /assess`
· `GET /posture/summary` · `GET /posture/devices/{id}` ·
`GET /compliance/report?fmt=markdown|json&redact=` · `POST /remediate/{id}` ·
`GET /health`.

## Meje (deferred)
K8s manifest (compose prek `./rob deploy`) · daemon periodic assess · LLM
poročilni prozo · Phase 3 moduli (embodied-AI red team, model supply-chain
verifikacija, threat intel feed).

---

# Phase 2 — Operator Monitor (Skin A) + OEM Embed SDK (Skin B)

Dva tanka skin-a na ENAM jedru (~80% deljeno). Vse monitor najdbe tečejo v
ISTI `fs_findings` tok → posture + CRA + eskalacija ostanejo eno.

## Nova najdbna kategorija
`telemetry_anomaly` (|z|>=3 medium, >=5 high) · `unknown_egress` (first-seen
dst, high) · `egress_anomaly` (>=5 unknown dst v oknu, medium).

## Monitor (`monitor.py`)
- `ingest_telemetry` / `ingest_network_observation` — pasivno, vsak zapis →
  audit.
- `detect_telemetry_anomalies` — z-score (signal_calc.z_score, populacijska
  varianca) zadnjega vzorca vs. rolling baseline; flat data → 0.0 → ni flag.
- `detect_egress_anomalies` — window-based first-seen (known_before iz
  fs_network_events) + allowlist (domene/IP/CIDR).
- `run_monitor_pass` — detekcija → `upsert_findings(..., resolve_categories=
  MONITOR_CATEGORIES)` (ne clobber-a posture) → prune retencije → audit.
- `monitor_summary`.

## Cross-category clobber fix
`store.upsert_findings(..., resolve_categories)` scopa-ta resolve na podane
kategorije. Posture pass uporablja `POSTURE_OWNED_CATEGORIES`, monitor
`MONITOR_CATEGORIES` — si ne brišeta najdb. Posture score šteje OPEN najdbe
po upsertu → monitor najdbe znižajo score.

## OEM SDK (`sdk.py`) — dependency-free (samo stdlib)
`fingerprint()` (točno strict HostInfo obliko) · `report_hostinfo` ·
`report_telemetry` · `report_network`. Transport `urllib.request`, nikoli ne
pade (`{"ok": False, "error": ...}`). `sdk_demo.py` = dogfood.

## API (main.py)
POST `/monitor/telemetry` · POST `/monitor/network` · POST `/monitor/run` ·
GET `/monitor/anomalies` · GET `/monitor/summary`.

## Config
`FS_MONITOR_HOURS` (daemon tick, 0=off) · `FS_TELEMETRY_WINDOW` (20) ·
`FS_ANOMALY_Z_THRESHOLD` (3.0) · `FS_ANOMALY_MIN_SAMPLES` (5) ·
`FS_EGRESS_ALLOWLIST` · `FS_TELEMETRY_RETENTION_HOURS` (24) ·
`FS_NETWORK_RETENTION_HOURS` (24).

## Daemon
`_tick_fleet_monitor`: `run_monitor_pass` → `run_assessment` (score svež).
Vklopljen samo če `FS_MONITOR_HOURS > 0`.

---

# Phase 3 — Premium moduli (SIMULACIJA / pasivno-only)

Trije moduli na ISTEM findings toku; vsak s svojim `*_CATEGORIES` scopom za
`resolve_categories` (ne clobber-ajo drug drugih).

## Nova najdbna kategorija
`redteam_injection` (red team) · `model_changed`/`model_unverified`
(supply chain) · `known_vulnerability` (threat intel). Severity postavi vsak
modul eksplicitno (`POSTURE_CATEGORY_SEVERITY` sentinel = `"informational"`).

## Embodied-AI Red Team (`redteam.py`) — SAMO simulacija
- `PAYLOAD_LIBRARY` — kurirani vektorji (direct/indirect injection, roleplay,
  encoding, DAN, cross-lingual, system-prompt extraction).
- `BrainTarget` (`simulated=True`) · `MockBrainTarget(secure)` · `LLMBrainTarget`
  (DeepSeek, NO-KEY → simuliran izhod).
- `run_red_team` — decide + judge (hevristika) → runs + `redteam_injection`
  findings. Guard `fs_redteam_sim_only` (fail-closed; nikoli živi robot).
- `harden_system_prompt` — deterministično (sandwich + boundaries +
  precedence + ignore-warning), BREZ LLM.
- `open_prompt_hardening_pr` — reuse remediacijskega gita/PR; piše
  `system_prompt.md`; nikoli auto-merge. On-demand (ni daemon tick).

## Model Supply-Chain (`supplychain.py`)
`fs_model_history` provenance registry. First-seen → baseline (brez findinga);
sha256/version drift → `model_changed` (high, stabilen detail); prazno sha256 →
`model_unverified` (medium). Resolve samo prek eksplicitne `record_model`.
Daemon tick `FS_SUPPLYCHAIN_HOURS` (0=off).

## Threat Intel (`threatintel.py`)
`data/threat_feed.json` seed (module-relative) → version→vuln mapiranje
(`compare_versions` numerični dot-segmenti; semver pre-release NI
implementiran). `known_vulnerability`, severity iz CVSS. Daemon tick
`FS_THREATINTEL_HOURS` (0=off).

## API / CLI
`POST /redteam/run|harden|harden/pr` · `GET /redteam/runs` ·
`POST /supplychain/record|check` · `GET /supplychain/history` ·
`POST /threatintel/check` · `GET /threatintel/feed`. CLI:
`redteam run/runs/harden` · `supplychain record/check/history` ·
`threatintel check/feed`.

## Config
`FS_REDTEAM_SIM_ONLY` (true) · `FS_SUPPLYCHAIN_HOURS` (0) ·
`FS_THREATINTEL_HOURS` (0) · `FS_THREAT_FEED_PATH` (override; prazno = seed).
