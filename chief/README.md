# Chief of Staff — ROB System

CoS = agent, ki te pozna, se odloča, ima roke in ti poroča kot chief of staff
poroča šefu. **Faza 2 (2026-09-02):** Chief panel je na dashboardu
(`src/` je odprt v varovalki); Python jedro sistema ostaja zaklenjeno.

Zaprt učni krog:

    model tebe ─▶ dnevna aktivnost ─▶ poročilo ─▶ tvoj popravek ─▶ v model

## Kako deluje (deterministično, brez LLM v jedru)

- **`chief/model.yaml`** — model lastnika + `execution_lock` (dovoljene cone /
  zaklenjeno jedro). Urejaš TI. Prazna `next_action` polja = "čaka tvoj vnos"
  (chief nikoli ne izumlja cilja).
- **`python -m chief --report`** — sestavi dnevno poročilo iz dejanske aktivnosti
  (`.rob_ai/audit.jsonl`) + modela, zapiše v `.rob_ai/chief/<datum>.md` in
  `latest.md`, izpiše ga. Ob tem strne popravke v lekcije.
- **`python -m chief --correct "besedilo"`** — shrani tvoj popravek (učni signal)
  v `.rob_ai/chief/corrections/<datum>.md`; ob naslednjem `--report` postane lekcija.
- **`python -m chief --lessons` / `--history` / `--week`** — lekcije / zgodovina
  poročil / povzetek zadnjih 7 dni (meritev).
- **`python -m chief --guard <pot>`** — preveri varovalko (execution_lock).
- **`python -m chief --model`** — izpiše model.

## Dashboard — Chief panel

Command Center (`src/server.ts`, `src/web/`) ima zavihek **Chief**:

- `GET  /api/chief`           → digest (`latest.md`) + lekcije + zgodovina
- `POST /api/chief/correct`   → popravek → `append_correction` → lekcija
- Komponenta `src/web/components/chief.ts` (prikaz digesta + vnos popravka).
- Oba endpointa pod obstoječo `ROB_API_TOKEN` zaščito.

Po spremembi frontenda poženi: `bun build src/web/main.ts --outfile src/web/dist/bundle.js`

## Varovalka (`execution_lock` v model.yaml)

Dovoljene cone pisanja: `actions/`, `src/`, `tests/`, `docs/`, `chief/`.
Zaklenjeno (Python jedro): `core/daemon.py`, `core/orchestrator.py`,
`core/agenda.py`, `core/loopx_bridge.py`, `core/plan_context.py`,
`core/config.py`, `run_swarm.py`, `rob`, `fleet/`.

## Prvi korak zate

Odpri `chief/model.yaml` — izpolni `focus` / `next_action` za posle, ki so zdaj
pomembni. Potem zaženi `python -m chief --report` in poročilo popravi (ali kar
v Chief zavihku na dashboardu).
