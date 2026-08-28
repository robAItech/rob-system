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
| **Backup spomina+agende** | `rob fleet backup` → `fleet/backup.json` → git | ob zagonu / ročno |
| **Heartbeat workerjev** | `/fleet/heartbeat` → `rob fleet status` | ~30 s |

## Napake, ki NISO napake

- `git push` → `[rejected] non-fast-forward` → samo pull --rebase + push.
- V remote-u se pojavijo commit-i "fleet backup ..." → avtomatsko, preskoči.
- `fleet/backup.json` se spreminja sam → normalno.
- Workerjeve naloge "izginejo" iz lokalne agende ob rebootu → master jih
  re-claim-a po lease TTL (30 min) — to je zaščita pred podvajanjem, ne napaka.

## Če je kaj spornega

Ne popravljaj na slepo. Napiši kratek povzetek uporabniku (kaj je naredila
druga sesija, zakaj misliš, da je sporno) in počakaj na odločitev.
