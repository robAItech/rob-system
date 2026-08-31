# Specifikacija modula `fleet_status`

## Namen

Ta dokument je specifikacija za nov Python modul `fleet_status` v `actions/fleet_status/`.
Modul zagotavlja vpogled v stanje flote Rob AI Studio: bere podatke o daemonu in
workerjih iz diska ter jih izpostavlja v strojno berljivi (`collect_status()`) in
človeško berljivi (`summary()`) obliki. Namen je opazljivost (observability) — da
operator in avtomatizacija vedo, ali daemon teče, v kakšnem stanju je in kdaj so bili
workerji nazadnje aktivni.

## Kontekst

Sistem Rob AI Studio zapisuje operativno stanje v dve datoteki:

- `.rob_ai/daemon.json` — vsebuje `state` (npr. `running`, `idle`, `stopped`) in
  `heartbeat_ts` (Unix timestamp zadnjega srčnega utripa daemona).
- `.rob_ai/fleet_workers.json` — objekt, kjer je ključ ime workerja, vrednost pa
  objekt z `last_seen` (Unix timestamp zadnje aktivnosti workerja).

Modul `fleet_status` te datoteke prebere (če obstajajo), jih validira s Pydantic V2
shemami in vrne enoten pogled na floto. Če datoteke manjkajo ali so poškodovane,
se napaka javi na predvidljiv način (dvignjen `FileNotFoundError`/`ValidationError`),
ki ga FastAPI plast pretvori v ustrezen JSON odziv.

## Funkcionalne zahteve

### `collect_status() -> dict`

Prebere `.rob_ai/fleet_workers.json` (workerji z `last_seen`) in
`.rob_ai/daemon.json` (`state`, `heartbeat_ts`) ter vrne dict oblike: