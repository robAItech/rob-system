# Chief of Staff — faza 1 (prvi teden)

Nov podsistem ROB Systema. Namerno **zunaj `core/`**: v prvem tednu NI povezan
v daemon/orchestrator — jedro sistema je zaklenjeno.

## Ideja (dogovorjeno 2026-09-02)

CoS = agent, ki te pozna, se odloča, ima roke in ti poroča kot chief of staff
poroča šefu. Prvi teden **vadi na samem ROB Systemu** (varno, hitro učenje);
roke drugje pridejo kasneje.

Zaprt učni krog:

    model tebe ─▶ dnevna aktivnost ─▶ poročilo ─▶ tvoj popravek ─▶ v model

## Kako deluje (deterministično, brez LLM)

- **`chief/model.yaml`** — model lastnika (seed). Urejaš TI. Prazna `next_action`
  polja = "čaka tvoj vnos" (chief nikoli ne izumlja cilja).
- **`python -m chief --report`** — sestavi dnevno poročilo iz dejanske aktivnosti
  (`.rob_ai/audit.jsonl`) + modela, zapiše v `.rob_ai/chief/<datum>.md` in
  `latest.md`, izpiše ga.
- **`python -m chief --correct "besedilo"`** — shrani tvoj popravek (učni signal)
  v `.rob_ai/chief/corrections/<datum>.md`.
- **`python -m chief --guard core/daemon.py`** — preveri varovalko prvega tedna.
- **`python -m chief --model`** — izpiše model.

## Varovalka prvega tedna

Pisanje/izvedba samo na `actions/`, `tests/`, `docs/`, `chief/`. Jedro
(`core/daemon.py`, `core/orchestrator.py`, `core/agenda.py`, `core/loopx_bridge.py`,
`run_swarm.py`, `rob`, `fleet/`) je zaklenjeno, dokler chief ne dokaže, da se
odloča dobro.

## Prvi korak zate

Odpri `chief/model.yaml` in izpolni `focus` / `next_action` za posle, ki so zdaj
pomembni. Potem zaženi `python -m chief --report` in poročilo popravi.
