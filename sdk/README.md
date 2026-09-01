# fleet-security-sdk — OEM embed SDK

**Dependency-free** Python client (samo stdlib: `urllib`, `platform`, `socket`, `uuid`) —
namestiš ga v robot firmware/OEM software in poroča varnostne podatke na Fleet Security jedro.
**Ni pydantic, ni `core.*`, ni omrežnih dependency** — vgradi se lahko v katerikoli Python 3.9+ runtime.

## Namestitev

```bash
# kot paket (iz tega imenika)
pip install sdk/

# ali — skopiraj samo paket (samostojno, brez pip-a):
cp -r sdk/fleet_security_sdk /path/to/robot/firmware/
```

## Minimalna integracija

```python
from fleet_security_sdk import FleetSecurityClient

client = FleetSecurityClient(
    server_url="https://robot-cloud:8000",   # Fleet Security FastAPI service
    token="<API_KEY>",                       # opcijsko — API ključ / ROB_API_TOKEN
    timeout=5.0,
)

# 1 · Prijavi ta robot v inventar (fingerprint: os, firmware, model, config)
client.report_hostinfo()

# 2 · Telemetry (CPU, mem, ...) — redno
client.report_telemetry({"cpu_pct": 42.0, "mem_pct": 55.0})

# 3 · Omrežne opazke (egress — pasivno, iz logov/netstat)
client.report_network(dst_ip="10.0.0.9", dst_port=443, proto="tcp")

# 4 · Model provenance (za supply-chain verifikacijo, ob posodobitvi modela)
client.report_model("vision-model", "2.0", sha256="a"*64, provider="oem", pushed_by="factory-ci")
```

## Kaj poroča → kam

| Metoda | Endpoint | Namen |
|---|---|---|
| `report_hostinfo()` | `POST /api/fleet-security/devices/ingest` | inventar (os/firmware/model/config) |
| `report_telemetry(metrics)` | `POST /api/fleet-security/monitor/telemetry` | časovne vrste → anomalije |
| `report_network(...)` | `POST /api/fleet-security/monitor/network` | egress detekcija |
| `report_model(...)` | `POST /api/fleet-security/supplychain/record` | model provenance → supply-chain |

## Deployment target

SDK poroča na **Fleet Security FastAPI service** (modul `fleet_security`, npr.
`uvicorn actions.fleet_security.main:app` — ali za gatewayjem/run-time middleware).
Endpointi: `/api/fleet-security/devices/ingest`, `/monitor/telemetry`,
`/monitor/network`, `/supplychain/record`.

**Auth**: `token` se pošlje kot `X-API-Key` (run-time auth) **in** `Authorization:
Bearer` (dashboard/gateway) — SDK dela proti obema površinama. Brez tokena
(odprti / tailnet-only deployment) so klici še vedno delujoči.

## Načela

- **Pasivno-prvi**: SDK SAMO poroča (device-reported), nikoli ne skenira/probe-a.
- **Nikoli ne pade**: vsaka metoda vrne `{"ok": True, status, data}` ali `{"ok": False, "error"}` — ne dviguje izjem (embedded odpornost).
- **On-prem**: podatki gredo na tvoje jedro (tailnet/on-prem), ne v tuji cloud.
- **Device_id**: če ni podan, se izpelje iz MAC (`rob-<12hex>`).

## API

- `FleetSecurityClient(server_url, token=None, timeout=5.0, device_id=None)`
- `fingerprint(...)` → HostInfo-shaped dict (strict schema, nobenih extra ključev)
- module-level `report_hostinfo/report_telemetry/report_network/report_model(server_url, ...)`

Primer dogfood: `python sdk/example.py http://127.0.0.1:8000 --token X`
