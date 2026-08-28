# Rob AI Studio — Arhitektura, vloge in GStack skilli

> Referenčni dokument: arhitektura, vloge, orkestracija, kje se uporabljajo
> prompti in GStack skilli, ter popoln spisek 54 GStack skillov.
> Stanje: 22. 8. 2026. Vir resnice: `SKILL.md` datoteke na disku, ne README.

---

## 1. Pregled arhitekture

Rob AI Studio je **dogodkovno-zanjen (ledger-first) avtonomni inženirski stroj**
z dvema izvedbenima plastema in vmesnikom:

```
┌────────────────────────────────────────────────────────────┐
│  VMESNIK / VHOD                                             │
│  ./rob CLI · dev_cli.py (proxy :4010 + dashboard :8787)     │
│  server.ts (Command-Center + Gmail poll) · GStack skills    │
└───────────────┬────────────────────────────────────────────┘
                │
   ┌────────────┴─────────────┐
   │ PLAST 1: TS Hermes       │  → produkti (dokument, UI, skripta)
   │ ledger-first, event-src. │
   │ 6 agentov · Runner       │
   └──────────────────────────┘
   │ PLAST 2: Python RSI/     │  → moduli (koda + pytest)
   │ GStack · 5 bridge-ov     │
   └──────────────────────────┘
                │
┌───────────────┴────────────────────────────────────────────┐
│  REZULTAT: out/* artefakti · actions/ (36 modulov)          │
└────────────────────────────────────────────────────────────┘
```

**Ključno:** dashboard (`POST /api/build`) in `./rob build` delita **isto**
Python RSI jedro (`run_swarm.py` → `orchestrator`). `POST /api/run` (Hermes)
je ločena pot za "produktne" naloge.

### 1.1 TS Hermes plast (`src/`)

Event-sourced produktni generator. `Ledger` (SQLite `.gstack-run.sqlite`) je
edini lastnik stanja; stanje teka se **izpelje** iz dnevnika s `foldState`
(`state.ts`), nikoli iz mutirane spremenljivke. `provenance()` sledi vzročni
verigi od naloge do artefakta.

### 1.2 Python RSI/GStack plast (`core/`)

Avtonomna gradnja modulov. `RobAIOrchestrator._phase` (`orchestrator.py`)
spelje zaporedje: **gbrain → graphify → gstack → hermes → loopx**.

**Nadgradnje (koraki 1–10):** agentic tool-use v RSI zanki (`loopx_bridge._heal_agentic`
— orodja read/write/list/search/skill, OpenAI function-calling), semantični spomin
(`core/embedder.py` — Gemini embeddingi, kosinusni priklic z leksikalnim padcem),
upravljanje konteksta (`LLM_HEAL_*` — budget prompta, trim messages), paralelizem
(fork + eval `--workers`), avto-rollback (`LOOPX_ROLLBACK_ON_FAIL`), actions/ kot
enotna runtime app (`core/actions_runtime.py` — 34 mountanih API modulov od 36,
2 sta knjižnici brez API-ja: csv_parser/retry_wrapper; + middleware
veriga auth→rate-limit→audit→event-bus) in realni odvisnostni graf
(`core/actions_graph.py`), ter CI (`.github/workflows/ci.yml`).

**Enterprise Actions (arhitekturna konsolidacija 2026):** `webhook_dispatcher`
(HMAC-SHA256, idempotency, eksponentni backoff, DLQ, health), `api_version_manager`
(SemVer, deprecation/Sunset, weighted routing, BC-break detekcija) in
`secret_rotation` (double-buffer, due scheduler, audit sled, auto-revoke). Tečejo
v runtime skupaj z ostalimi moduli.

---

## 2. Vloge — kdo vodi, kdo dela

| Plast | Vodi (orkestrator) | Dela (izvajalci) |
|---|---|---|
| **TS Hermes** | `Runner` — edini z zmožnostmi (disk, omrežje, `cmd.exec`). Zanka: dogodek → `foldState` → `reduce` agentov → `Command[]` → izvedi. | `planner` (plan), `builder` (piše datoteke), `qa` (verify), `screenshot` (vizualna namera) |
| **Python RSI** | `RobAIOrchestrator._phase` | `gbrain` (spomin), `graphify` (AST), `gstack` (spec), `hermes` (ogrodje), `loopx` (pytest + heal) |
| **LLM** | — | `DeepSeekLLMClient` (`deepseek-v4-flash`) — generira kodo/popravke |
| **Nad nivo** | `dev_cli.py` — orkestracija procesov | 30 `actions/` modulov — končni produkt (27 z API-jem) |

**Vodilni agent** v Python poti je en sam: `GSTACK-Architect` (privzeto iz
`run_swarm.py --agent`), ne jata agentov. `architect`/`engineer` v TS plasti
sta definirana (arhetip mejnika 1), a **nista** v aktivnem toku — aktivni so
`planner/builder/qa/screenshot` (`agentsFor('full')` = `[planner, builder, qa,
screenshot]`).

### TS agenti (čisti reduktorji)

| Vloga | Odgovornost | V toku |
|---|---|---|
| `planner` | odločitev + workplan + naroči LLM `@file` bloke | ✅ full+dashboard |
| `builder` | razreže `@file` → `fs.write`; fallback `out/RESULT.md`; sproži `qa.decide` | ✅ full+dashboard |
| `qa` | `cmd.exec` verify; exit 0 → complete, retry ≤ maxFixPasses → stuck | ✅ full+dashboard |
| `screenshot` | zabeleži *namero* posnetka ob spletnem artefaktu | ✅ samo full |
| `architect` | arhetip: odločitev + LLM → `out/RESULT.md` | ⬜ registriran, ni v toku |
| `engineer` | zadnji LLM odgovor → disk + `run.complete` | ⬜ registriran, ni v toku |

### Python RSI bridge-i

| Vozlišče | Datoteka | Vloga |
|---|---|---|
| **GBRAIN** | `gbrain_bridge.py` | trajni spomin SQLite (blacklisti, zgodovina, memory nodes) |
| **GRAPHIFY** | `graphify_bridge.py` | AST sken → `graph.json` + odvisnostni kontekst |
| **GSTACK** | `gstack_bridge.py` | manifest + `spec_hint` (blueprint → LLM) |
| **HERMES** | `hermes_bridge.py` | ogrodje `actions/<mod>/` (stub-i) |
| **LOOPX** | `loopx_bridge.py` | pytest → DeepSeek heal (agentic tool-use) → ≤5× → zelen ali FAILED |

---

## 3. Orkestracija (potek)

```
Naloga (človek)
  │  produkt? ───────► TS Hermes:  planner → builder → qa → out/*
  │  modul/koda? ────► Python RSI: gbrain → graphify → gstack → hermes → loopx
  │                            └── loopx: pytest → DeepSeek popravi (≤5×) → zelen/FAILED
  │  iz Gmaila ──────► server.ts poll → agenda (pending) → človek potrdi → /api/build
```

### RSI samozdravstvena zanka (`LoopXEngineBridge._heal_loop`)

1. **Verifikacija** — po tipu izdelka: Python → pytest (sandbox) + ruff; Markdown/HTML → strukturna preverba.
2. **Zelen** — `VERIFIED GREEN` se zapiše v GBRAIN; zanka konča.
3. **Rdeč → heal** — traceback → DeepSeek (`_heal_once`) → popravki → `actions/<mod>/` → ponovna verifikacija.
4. **Ponavljanje** — do 5 poskusov; enaka ponavljajoča se napaka (≥ 3×, `REPEAT_ABORT_AFTER`) zgodaj prekine.
5. **Neuspeh** — `FAILED` + blacklist v GBRAIN (učenje). Modul se avtomatsko povrne na pred-build stanje (snapshot v `.loopx/rollback/`; izklop: `LOOPX_ROLLBACK_ON_FAIL=false`).

Sočasni buildi istega modula se varujejo z atomic target-lockom.

---

## 4. Kje se uporabljajo prompti in GStack skilli

**GStack skilli (54)** so **zunanji framework** (`~/.claude/skills/gstack/`) —
specialistične vloge, ki tečejo *nad* Rob sistemom. Kličejo se prek `Skill`
orodja, usmerja pa jih `## Skill routing` v `CLAUDE.md`. **Od koraka 6** jih
Rob-ova lastna koda poleg tega izpostavi kot LLM orodje: `core/skill_bridge.py`
prebere `SKILL.md` in v RSI heal zanki lahko LLM pokliče `skill("spec")`, da dobi
strnjen procesni vodič (cap 6k, brez ponavljajočega boilerplate-a). Za človeka
v terminalu ostajajo dostopni kot prej — oba načina sobivata.

**Prompti** so na štirih mestih v Rob kodi:
1. `src/agents/planner.ts` → `SYSTEM_PROMPT` ("Si orkestrator programerskega podjetja… @file bloke").
2. `src/agents/architect.ts` → `SYSTEM_PROMPT` (arhetip).
3. `core/gstack_bridge.py` → `render_spec_hint()` — blueprint + blacklisti se vbrizgajo v LLM prompt kot arhitekturna usmeritev.
4. `core/llm_client.py` → `generate_completion(prompt, system_prompt, use_coder_model)` — sem pride `spec_hint` + direktiva.

---

## 5. GStack skilli (54) — spisek z role

Vir resnice: `SKILL.md` na disku. Vsi klicljivi prek `/skill-name`.

### Router (1)
| Skill | Rola |
|---|---|
| `gstack` | Router — usmeri zahtevek na pravi skill |

### Plan / pregledi (9)
| Skill | Rola |
|---|---|
| `office-hours` | YC Office Hours — reframira idejo pred kodo |
| `plan-ceo-review` | CEO/founder pregled načrta |
| `plan-eng-review` | Eng-manager pregled (arhitektura, tok, testi) |
| `plan-design-review` | Designer pregled (dimenzije 0–10) |
| `plan-devex-review` | DX pregled načrta |
| `plan-tune` | Samo-uglaševanje vprašanj + psihografija |
| `autoplan` | Avto-review cevovod (CEO→design→eng→DX) |
| `design-consultation` | Celoten design sistem iz nič |
| `spec` | Nejasna namera → izvršljiv spec (5 faz) |

### Implementacija + review (11)
| Skill | Rola |
|---|---|
| `review` | Pre-landing PR pregled |
| `codex` | OpenAI Codex CLI (3 načini) |
| `investigate` | Root-cause debugiranje |
| `design-review` | Designer's-eye QA + popravek |
| `design-shotgun` | AI design variante + primerjava |
| `design-html` | Produkcijski HTML/CSS |
| `devex-review` | Živi DX audit |
| `qa` | QA + popravek bug-ov |
| `qa-only` | QA samo-poročilo |
| `scrape` | Poberi podatke s spleta |
| `skillify` | Codify scrape → browser-skill |

### Release + deploy (8)
| Skill | Rola |
|---|---|
| `ship` | Merge/test/review/PR |
| `land-and-deploy` | Merge + CI + verify prod |
| `canary` | Post-deploy monitoring |
| `landing-report` | Read-only queue dashboard |
| `document-release` | Posodobi dokumentacijo |
| `document-generate` | Generira manjkajoče doc |
| `setup-deploy` | Deploy konfiguracija |
| `gstack-upgrade` | Nadgradi gstack |

### Operativa + spomin (10)
| Skill | Rola |
|---|---|
| `context-save` | Shrani kontekst |
| `context-restore` | Obnovi kontekst |
| `learn` | Upravljaj učenja |
| `retro` | Tedenski retro |
| `health` | Code-quality dashboard |
| `benchmark` | Perf regresije |
| `benchmark-models` | Cross-model benchmark |
| `cso` | Varnostni audit (OWASP/STRIDE) |
| `setup-gbrain` | Nastavi gbrain |
| `sync-gbrain` | Uskladi gbrain |

### Brskalnik + agenti (4)
| Skill | Rola |
|---|---|
| `browse` | Headless brskalnik |
| `open-gstack-browser` | GStack Browser |
| `setup-browser-cookies` | Uvozi piškotke |
| `pair-agent` | Seznani agent z brskalnikom |

### iOS QA (5)
| Skill | Rola |
|---|---|
| `ios-qa` | Live-device iOS QA |
| `ios-fix` | iOS bug fixer |
| `ios-design-review` | iOS design audit |
| `ios-clean` | Odstrani DebugBridge |
| `ios-sync` | Regenerira iOS bridge |

### Varnost + obseg (6)
| Skill | Rola |
|---|---|
| `careful` | Opozori pred destruktivnimi ukazi |
| `freeze` | Zakleni urejanje na direktorij |
| `guard` | careful + freeze |
| `unfreeze` | Odstrani freeze |
| `make-pdf` | Markdown → PDF |
| `diagram` | Opis → diagram (mermaid/excalidraw) |

**Skupaj: 54** (1 + 9 + 11 + 8 + 10 + 4 + 5 + 6).

---

## 6. Skill routing (CLAUDE.md)

Routing tabela v `CLAUDE.md` (`## Skill routing`) pokriva vseh 54 skillov in
vsakemu dodeli sprožilno besedo. Glej `CLAUDE.md` za polno tabelo.
