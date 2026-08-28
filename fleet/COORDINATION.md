# 🤝 Fleet koordinacija — rob-system (master + worker)

Ta datoteka je **skupna resnica za VSE sesije** (Claude Code na masterju,
workerju, ali kjer koli), ki delajo na repozitoriju `robAItech/rob-system`.
Če si nov sistem/sesija na tem repoju, jo **najprej preberi in upoštevaj**:
pove ti, zakaj se dogajajo commit-i, ki jih ti nisi naredil — in da to NI napaka.

---

## Ključno dejstvo

Na tem repoju delata **DVA (ali več) računalnikov hkrati** v načinu
**P9 fleet** (deljena agenda + deljen spomin). Zato:

> **Commit-i, ki jih ti nisi naredil, SO NORMALNI.** Prihajajo z drugega
> stroja/sesije — bodisi drug sistem počisti svoje delo, bodisi avtomatski
> `rob fleet backup` (izvoz spomina+agende). **To NI napaka.** Ne vračaj jih,
> ne razveljavljaj, ne "popravljaj".

## Protokol (obvezen za vse sesije)

1. **Remote `master` je edina avtoritativna resnica.** Pred vsakim delom in
   pred vsakim `git push` naredi:
   ```bash
   git pull --rebase origin master
   ```
2. Če `git push` zavrne (non-fast-forward) → **to ni napaka, samo sinhronizacija**:
   ```bash
   git pull --rebase origin master
   git push
   ```
   **NIKOLI** `git push --force`, **NIKOLI** `git reset --hard` proti remote-u.

> ⚙️ **Avto `pull --rebase` pred pushom** (`hooks/pre-push`, nastavi ga `rob`):
> prvi `git push`, ko je remote naprej, sam naredi `pull --rebase` in javi
> **"rebase opravljen — zaženi git push še enkrat"**. To NI napaka — samo zaženi
> `git push` znova (drugi bo uspel). Ne prekini, ne --force, ne reset.
3. **`fleet/backup.json` je avtomatski izdelek** (`rob fleet backup`) — ne
   briši ga, ne vračaj njegovih sprememb, ne commitaj ga ročno.
4. **`fleet/COORDINATION.md`** (ta datoteka) naj ostane nespremenjena — je
   dogovor, ne koda.
5. Lokalne datoteke, ki **NISO deljene** in se ne commitajo: `.env`,
   `engine/`, `node_modules/`, `.rob_ai/` (razen izvozov v `fleet/`).
6. **Master je edina avtoriteta nad agendo** (`.rob_ai/agenda.json` na
   masterju). Workerji vanjo pišejo SAMO prek endpointov
   `/fleet/claim|result|heartbeat|memory` — nikoli neposredno.
7. Če naletiš na spremembo druge sesije, ki je ne razumeš: **pusti jo pri miru
   in vprašaj uporabnika** — ne razveljavljaj na slepo.
8. **Testi**: `./rob test` (375 testov) mora biti zelen pred commitom.

## Kaj se sinhronizira in kaj ne

| Stvar | Kako | Hitrost |
|---|---|---|
| **Agenda (naloge)** | worker → master prek HTTP `/fleet/claim` + `/fleet/result` | takoj (eventual) |
| **Spomin (učne tabele)** | worker potegne pred nalogo, pošlje po nalogi (`/fleet/memory`) | po nalogi |
| **Koda / docs** | git (`pull --rebase` / `push`) | ročno / po potrebi |
| **Workerjevi build-i (`actions/`)** | worker po uspešnem build-u commit+push (`fleet: worker build <mod>`); master jih dobi ob naslednjem pull-u | po build-u |
| **Backup spomina+agende+actions** | `rob fleet backup` → `fleet/backup.json` + `actions/` → git | ob zagonu / ročno |
| **Heartbeat workerjev** | `/fleet/heartbeat` → `rob fleet status` | ~30 s |

## Povezave med stroji (network promet) — KAJ JE NORMALNO

Worker ↔ master komunicirata **stalno** prek HTTP-ja (master :8789). To NI
napad, NI napaka in NE smeš tega blokirati ali "popravljati":

| Kdaj | Worker → master | Zakaj |
|---|---|---|
| ob vsaki nalogi | `POST /fleet/claim` | worker prosi za naslednjo nalogo |
| po vsaki nalogi | `POST /fleet/result` | javi izid (done/failed) |
| **1×/uro** (le ko je dosegljiv) | `GET/POST /fleet/memory` + `POST /fleet/heartbeat` | izmenja spomin + javi, da je živ |

Master → git: **vsako uro** `rob fleet backup` (commit `fleet backup ...` +
push `fleet/backup.json`). Master → dashboard: `/api/fleet` bere
`fleet_workers.json` (Command Center, poll 30 s).

**Backoff (worker):** ko master NI dosegljiv, worker ne "išče" povezave —
počaka `ROB_FLEET_BACKOFF_SECONDS` (privzeto 5 min), nato poskusi enkrat. Sync
in heartbeat potekata SAMO, ko je povezava dejansko živa.

Če torej vidiš:
- redne HTTP klice na `:8789` iz drugega stroja (ob nalogah ali 1×/uro) →
  **normalno** (fleet protokol; ob nedosegljivosti masterja jih NI — backoff),
- commit `fleet backup ...` vsako uro → **normalno** (avtomatski backup),
- spremembe `fleet/backup.json` → **normalno** (avtomatski izdelek),
- worker občasno "izgine" iz lokalne agende ob rebootu → **normalno** (master ga
  re-claim-a po lease TTL 30 min; zaščita pred podvajanjem).

## Napake, ki NISO napake

- `git push` → `[rejected] non-fast-forward` → samo pull --rebase + push.
- V remote-u se pojavijo commit-i "fleet backup ..." → avtomatsko, preskoči.
- `fleet/backup.json` se spreminja sam → normalno.
- Workerjeve naloge "izginejo" iz lokalne agende ob rebootu → master jih
  re-claim-a po lease TTL (30 min) — to je zaščita pred podvajanjem, ne napaka.

## Če je kaj spornega

Ne popravljaj na slepo. Napiši kratek povzetek uporabniku (kaj je naredila
druga sesija, zakaj misliš, da je sporno) in počakaj na odločitev.
