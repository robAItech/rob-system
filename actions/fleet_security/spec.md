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
poročilni prozo · Phase 2 skin-a · Phase 3 moduli (embodied-AI red team,
model supply-chain verifikacija, threat intel feed).
