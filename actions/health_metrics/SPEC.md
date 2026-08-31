# Specifikacija modula `health_metrics`

## Namen

Ta dokument je specifikacija za izdelavo Python modula `health_metrics` v imeniku `actions/health_metrics/`. Modul zagotavlja opazljivost stanja avtonomnega sistema Rob AI Studio: prebere dogovorjeni stanje daemona in agende ter jih izpostavi kot strojno berljiv dict (prek funkcije `collect_metrics()`) in kot kratek človeku berljiv tekstovni povzetek (prek funkcije `summary()`).

## Cilj

Naredi Python modul `health_metrics` v `actions/health_metrics/`, ki:

- izpostavi funkcijo `collect_metrics()` — prebere `.rob_ai/daemon.json` (polji `state` in `heartbeat_ts`) ter `.rob_ai/agenda.json` (šteje naloge po statusih `pending` / `done` / `failed`) in vrne `dict`;
- izpostavi funkcijo `summary()` — vrne kratek tekstovni povzetek trenutnega stanja sistema;
- vključuje pytest datoteko `test_health_metrics.py` z vsaj 5 testi, ki pokrivajo normalne in robne pogoje.

## Funkcionalne zahteve

### 1. `collect_metrics() -> dict`

Vhodni viri:

- `.rob_ai/daemon.json` — JSON objekt z vsaj ključema `state` (npr. `"running"`, `"stopped"`, `"error"`) in `heartbeat_ts` (čas zadnjega srčnega utripa, npr. ISO 8601 niz ali unix timestamp).
- `.rob_ai/agenda.json` — JSON z zbirko nalog; vsaka naloga vsebuje polje `status` z vrednostjo `pending`, `done` ali `failed`.

Izhod: `dict` s strukturo, npr.:

```python
{
    "daemon": {"state": "running", "heartbeat_ts": "2025-01-01T00:00:00Z"},
    "agenda": {"pending": 3, "done": 12, "failed": 1},
    "healthy": True,
}
```

Pravila:

- Če `.rob_ai/daemon.json` ali `.rob_ai/agenda.json` ne obstaja ali ni veljaven JSON, funkcija ne sme pasti — vrne dict z eksplicitno oznako napake (npr. `"error"` ključ) oziroma prazne števce, glede na odločitev klicatelja.
- Štetje po statusih je izključujoče: vsaka naloga šteje natanko enkrat; neznani statusi se ne štejejo v `pending` / `done` / `failed`.
- `healthy` je logična vrednost, izpeljana iz stanja daemona in prisotnosti veljavnega heartbeata.

### 2. `summary() -> str`

- Vrne kratek, enovrstičen ali večvrstičen tekstovni povzetek, ki povzame stanje daemona, čas heartbeata in števce agende, npr.: `"Daemon: running (heartbeat 2025-01-01T00:00:00Z) — agenda: 3 pending, 12 done, 1 failed."`.
- Povzetek mora biti determinističen in brez neznanih vrednosti (`None` se nadomesti z jasno oznako, npr. `"unknown"`).

## Arhitektura in struktura datotek

```
actions/health_metrics/
├── __init__.py              # javni izvoz (collect_metrics, summary)
├── health_metrics.py        # čista domenska logika (branje datotek, štetje, povzetek)
├── schemas.py               # Pydantic V2 sheme s strogimi validatorji
├── main.py                  # FastAPI integracijski router (direct JSONResponse 4xx/5xx)
└── test_health_metrics.py   # pytest, vsaj 5 testov
```

Arhitekturne smernice:

- **sheme**: Pydantic V2 (`model_config = ConfigDict(strict=True)`) s strogimi validatorji za `DaemonState` in `AgendaCounts`.
- **logika**: čista, po možnosti async logika v `health_metrics.py`, ločena od FastAPI; branje datotek prek `pathlib.Path`, odporno na manjkajoče datoteke in poškodovan JSON.
- **API**: `main.py` izpostavi FastAPI router z npr. `GET /health/metrics` (vrne dict iz `collect_metrics()`) in `GET /health/summary` (vrne tekst); napake se vračajo kot `JSONResponse` s statusi 4xx/5xx, ne kot neulovljene izjeme.
- **testi**: pytest z vsaj 5 testi, ki pokrivajo: uspešno branje obeh datotek, manjkajoč daemon.json, manjkajočo agenda.json, poškodovan JSON, štetje z neznanimi statusi in format `summary()`.

## Načrt izvedbe

1. **Priprava** — preveri obstoječe stubs v `actions/health_metrics/` in dogovorjene formate `.rob_ai/daemon.json` ter `.rob_ai/agenda.json`.
2. **`schemas.py`** — definiraj Pydantic V2 modele `DaemonState` (polji `state`, `heartbeat_ts`) in `AgendaCounts` (polja `pending`, `done`, `failed` z nenegativnimi int) s strogimi validatorji.
3. **`health_metrics.py`** — implementiraj `collect_metrics()` (branje datotek, robustno parsanje, štetje po statusih, izračun `healthy`) in `summary()` (determinističen tekstovni povzetek).
4. **`main.py`** — poveži logiko v FastAPI router z `GET` endpointi in eksplicitnim `JSONResponse` 4xx/5xx handlingom.
5. **`__init__.py`** — izpostavi javni API (`collect_metrics`, `summary`) za preprost uvoz.
6. **Testi** — napiši `test_health_metrics.py` z vsaj 5 testi (normalni tok + robni pogoji) in preveri 100 % zelen izhod `pytest`.
7. **Verifikacija** — poženi `pytest` v `actions/health_metrics/`; cilj je 100 % zelenih testov ob nespremenjeni testni datoteki.

## Merila sprejemljivosti

- `collect_metrics()` vrne dict z daemon stanjem, števci agende in indikatorjem zdravja; ne pade ob manjkajočih/poškodovanih virih.
- `summary()` vrne kratek, determinističen, človeku berljiv povzetek.
- `test_health_metrics.py` vsebuje vsaj 5 testov in vsi preidejo.
- Testna datoteka se ne spreminja za dosego zelenega izhoda (Test-Locking).
