# 🤖 Rob AI Studio — Avtonomni AI Inženirski Stroj

Rob AI Studio je vaš avtonomni delovni stroj. Je vaša osebna tovarna,
ki ima delujoče možgane (LLM & Context Graph), roke (`./rob` Swarm Motor)
in avtomatske varnostne zavore (RSI zanka + Pytest), da lahko samostojno
in brezkompromisno rešuje kompleksne inženirske naloge za vaše stranke
in naročnike.

## 🎯 Vizija in standard izvedbe

Rob AI Studio ni zgolj orodje za generiranje izsekov kode — je avtonomni
produkcijski agregat. Zgrajen je po načelu, da je z uporabo umetne
inteligence mejni strošek popolnosti blizu ničle.

Sistem deluje po nepopustljivem pravilu:

> *"Boil the ocean. Do it right. Do it with tests. Do it with documentation."*

Naročnik ali uporabnik poda cilj visoke ravni, Rob AI Studio pa samostojno
izvede analizo, zgenerira arhitekturo, izvede AST sintaktično preverjanje,
poganja Pytest verifikacijo, se ob napaki samodejno sanira in dostavi
100-% delujoč izdelek.

## 🏛️ Arhitekturni trikotnik

Sistem temelji na treh integriranih stebrih:

| Steber | Komponenta | Primarna vloga |
|---|---|---|
| **Možgani** | DeepSeek (LLM) + GBrain (spomin) + Graphify (AST) | Razumevanje konteksta, trajni spomin, odvisnostni graf kode in generiranje rešitev. |
| **Roke** | `./rob` CLI + `run_swarm.py` (orchestrator) | Orkestracija gradnje: gbrain → graphify → gstack → hermes → loopx. |
| **Zavora** | `LoopXEngineBridge` + Pytest | RSI samozdravljenje: pytest → DeepSeek popravi → ≤5× → 100% zelen ali FAILED + blacklist. |

```
┌──────────────────────────────────────────────────────────┐
│                NAROČNIK / STRANKA (Prompt)               │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│         MOŽGANI: DeepSeek LLM + GBrain + Graphify        │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│       ROKE: ./rob CLI + run_swarm.py (orchestrator)      │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│            ZAVORA: LoopX (RSI) + Pytest                  │
└──────────────┬─────────────────────────────┬─────────────┘
               │                             │
     [❌ pytest pade / traceback]      [✅ 100% zelen]
               │                             │
               ▼                             ▼
┌──────────────────────────────┐  ┌────────────────────────┐
│ Samodejno Samozdravljenje    │  │ VERIFIED GREEN         │
│ (Do 5 iteracij s feedbackom) │  │ (100% zelen, shipped)  │
└──────────────────────────────┘  └────────────────────────┘
```

## 🚀 Ključne zmogljivosti

- **Avtonomno izvajanje nalog za stranke** — sprejme kompleksno zahtevo
  naročnika ter samostojno ustvari razrede, API endpoint-e, validacijske
  sheme in pripadajoče unit/integracijske teste.
- **Closed-Loop RSI Engine (Recursive Self-Improvement)** — samostojno
  analizira kodo preko Python AST (Abstract Syntax Tree) parserja, poišče
  ozka grla ter jih optimizira.
- **5-stopenjsko samozdravljenje (Self-Healing Loop)** — če koda ne
  prestane preizkusa, engine zajame natančen STDOUT/STDERR traceback,
  ga posreduje LLM-u in v do 5 poskusih avtonomno odpravi napako.
- **Fail-safe beleženje napak** — če koda po vseh poskusih ne doseže 100-%
  zelene verifikacije, se tek zaključi kot `FAILED` in napaka se zapiše v
  GBRAIN blacklist (učenje za prihodnje teke). Ob neuspelem buildu se modul avtomatsko povrne na pred-build stanje (snapshot v `.loopx/rollback/`; izklop: `LOOPX_ROLLBACK_ON_FAIL=false`).
- **Jedrnati CLI ukazi** — brez mikromanagementa. Sistem se krmili s
  kratkimi, direktnimi ukazi.

## 📁 Arhitektura projektne strukture

```
Rob AI Studio/
├── rob                               # CLI motor (rescue nadzor: rob dev / rob build / rob eval)
├── dev.bat                           # Windows launcher za rob dev
├── core/                             # Python jedro
│   ├── dev_cli.py                    # Orkestracija (proxy+dashboard+claude, --serve)
│   ├── daemon.py                     # P1 — avtonomni daemon (24/7 master proces)
│   ├── orchestrator.py               # RSI/GStack faza (gbrain→graphify→gstack→loopx)
│   ├── loopx_bridge.py               # RSI zanka (pytest→LLM→100% zelen) + test-lock
│   ├── run_review.py                 # Z2 — post-run presoja + fix-task enqueue
│   ├── meta_eval.py                  # Z4 — poštena metrika (iz run_reviews, ne task_history)
│   ├── embedder.py                   # Semantični embeddingi spomina (Gemini, korak 2)
│   ├── skill_bridge.py               # GStack skilli kot LLM orodje (korak 6)
│   ├── actions_runtime.py            # actions/ kot enotna runtime app (korak 5)
│   ├── actions_graph.py              # Realni odvisnostni robovi action modulov (korak 5)
│   ├── agenda.py                     # Čakalna vrsta naročil (več vhodov → vrsta)
│   ├── audit.py / business.py / visual_qa.py  # revizija / glavna knjiga / vizualni QA
├── src/                              # TypeScript Command-Center dashboard
│   └── server.ts                     # :8787 /api/* + Gmail polling (Faza 2)
├── actions/                          # Produkcijski moduli (RSI jih gradi/popravlja)
├── bridges/litellm_config.yaml       # DeepSeek proxy routing
├── scripts/                          # autostart.bat + register-autostart.ps1 (HKCU Run)
├── evaluate_autonomy.py              # P0 — SWE-bench stila samo-eval (rob eval)
├── .github/workflows/ci.yml          # CI: PR gate (pytest + eval dry-run) + nočni eval
└── tests/                            # Pytest suite (302 testov, CI zelen)
```

## 🛠️ Hitra namestitev in zagon

### 0. Predpogoji — orodja (nov računalnik)

Vse, kar sistem potrebuje na svežem računalniku, v enem povzetku:

**Orodja na PATH:**

| Orodje | Namestitev | Za kaj |
|---|---|---|
| **Python 3.11+** | python.org/downloads ali `winget install Python.Python.3.11` | jedro, RSI zanka, daemon |
| **git** | git-scm.com | klon + CI |
| **Node.js + npm** | nodejs.org | bun + TS odvisnosti |
| **Bun** | `npm i -g bun` | dashboard (`src/server.ts`), TS |
| **LiteLLM** | `pip install litellm` | proxy :4010 (DeepSeek routing) |
| **Docker Desktop** | docker.com (Windows: mora biti zagnan) | RSI peskovnik (`rob-sandbox`) |
| **Playwright + chromium** | `pip install playwright` + `playwright install chromium` | vizualni QA (HTML screenshot) — neobvezno |
| **Ruff** | v requirements-dev.txt | F821 pre-gate v RSI (če manjka, se preskoči) |
| **Tailscale** | tailscale.com — neobvezno | varen remote dostop do dashboarda |

**Python paketi** (edina zahtevana Python odvisnost):
```bash
pip install -r requirements-dev.txt
pip install litellm playwright        # playwright le za vizualni QA
playwright install chromium           # neobvezno (screenshot HTML)
```

**TS paketi (dashboard):**
```bash
bun install
```

**Docker RSI peskovnik** (Tier 1 — izolirana pytest verifikacija v `--network none`):
```bash
docker build -f Dockerfile.sandbox -t rob-sandbox .
```
> Brez Dockerja RSI pade na host pytest (oznaka `[NI IZOLIRANO]`) — deluje, a ni izolirano.

**Preverba namestitve (ključni ukazi):**
```bash
./rob test                  # celotna testna matrika (307 testov) — mora biti zelena
./rob eval --dry-run        # strukturna preverba eval lestvice (brez LLM)
./dev                       # dvigne proxy :4010 + dashboard :8787 (ročni/rescue)
./rob daemon --serve        # P1 daemon: proxy+dashboard v ozadju, 24/7
./rob daemon --status       # stanje daemona (heartbeat, tek. naloga, jobi)
```

Prvi resničen smoke test — preveri, da RSI/GStack zanka deluje od nule:
```bash
./rob build testmod "Izdelaj Python modul testmod v actions/testmod/. Funkcija add(a,b) vrne a+b. Vsebuj pytest test, vsi testi 100% zeleni."
```

**.env** — ustvari iz `.env.example`: **obvezen `DEEPSEEK_API_KEY`**; opcijsko
`GEMINI_API_KEY` (semantični spomin + TTS), `SERPER_API_KEY` (spletno iskanje).

**(Windows) avtomatski zagon ob prijavi (daemon 24/7):**
```powershell
pwsh -File scripts\register-autostart.ps1        # registrira daemon ob prijavi
pwsh -File scripts\register-autostart.ps1 -Query # preveri registracijo
```

### 1. Kloniranje repozitorija in priprava okolja

```bash
git clone https://github.com/robAItech/AI-podjetje-V5.git
cd "Rob system"
cd "C:\Rob system"
```

Zahtevana orodja na PATH so v **Predpogoji (0)** zgoraj — tukaj le ključna:
- **Python 3.11+** (glavni interpreter `python`)
- **bun** (`npm i -g bun`) — za dashboard (`bun run src/server.ts`)
- **litellm** (`python -m pip install litellm`) — za proxy :4010

### 2. Konfiguracija okoljskih spremenljivk

Ustvarite datoteko `.env` v korenskem imeniku projekta:

```
DEEPSEEK_API_KEY=vaš_deepseek_api_ključ
GEMINI_API_KEY=vaš_gemini_api_ključ    # TTS + spletno iskanje + semantični spomin (embeddingi) — https://aistudio.google.com/apikey
SERPER_API_KEY=vaš_serper_api_ključ    # (opcijsko) pravo Google iskanje — https://serper.dev
```

Poln seznam nastavitev — vklj. `LLM_TOOL_USE` (agentic tool-use), `MEMORY_EMBEDDINGS`,
`LLM_HEAL_PROMPT_CHARS`/`LLM_HEAL_SOURCES_CHARS` (kontekst), `LOOPX_ROLLBACK_ON_FAIL`
(avto-rollback) in `GSTACK_SKILLS_DIR` — je v `.env.example`.

### 3. Zagon Claude Code prek LiteLLM + DeepSeek (`./dev`)

`Claude Code` privzeto kliče Anthropic API. Da ne kurimo dragih Anthropic
tokenov, se projekt nasloni na enotno **Python orkestracijo** (`core/dev_cli.py`,
ukaz `rob dev`), ki dvigne [LiteLLM](https://www.litellm.ai/) proxy in preslika
zahtevke na **cenejši DeepSeek API** z vašim `DEEPSEEK_API_KEY`. Poleg proxyja
dvigne še **Command-Center dashboard**:

- **Proxy LiteLLM na :4010** (lasten, izoliran)
- **Command-Center dashboard** na **:8787 (HTTPS)** via `bun run src/server.ts`
  — futuristični temni UI z glasovnim pogovorom (voice + TTS), živim spletnim
  iskanjem, agendo, artefakti, agenti in sistemskim grafom

Vse v enem ukazu — `./dev` (dela na Windows, Linux in WSL):

```bash
./dev                       # proxy :4010 + dashboard :8787 v ozadju, poveže claude;
                            # po izhodu sam ugasne samo kar je zagnal. Port 4000 se ne dotakne.
./dev --init                # dry-run: preveri config, ključ, porta 4010/8787 in PATH.
./dev --proxy-only          # samo LiteLLM na 4010 v ospredju.
./dev --dashboard-only      # samo Command-Center (bun run src/server.ts) na 8787.
./dev --claude-only         # samo claude ob že obstoječem proxyju na 4010.
```

Vsi načini delegirajo na isti Python modul `core/dev_cli.py`.

#### Avtonomen zagon (PC kot centralni server) — brez terminala

Dashboard :8787 je spletni UI za **vnos nalog** in **ogled izida**
(GREEN/FAILED + stdout/stderr) — glavni način uporabe, ni terminala.
**P1 avtonomni daemon** (`core/daemon.py`) je edini 24/7 master proces: ob
prijavi idempotentno dvigne proxy+dashboard, **sam prazni agendo** skozi RSI,
**sam predlaga nove naloge** iz šibkosti sistema (goal autonomy, polna
avtonomija), teče periodične jobe (konsolidacija spomina, refleksija,
samorazvoj, meta-eval, eval) in piše heartbeat v `.rob_ai/daemon.json`:

```powershell
rob daemon --serve              # dvigne proxy+dashboard (idempotentno), izhod
rob daemon --once               # ena enota dela (smoke test), izhod
rob daemon --status             # stanje: heartbeat, tek. naloga, jobi
rob daemon --stop               # graceful shutdown tekočega daemona
pwsh -File scripts\register-autostart.ps1   # registrira autostart (ob prijavi)
pwsh -File scripts\register-autostart.ps1 -Query   # preveri
```

**Routing agentov (P5)** — daemon obdela nalogo z agentom po `kind` (v agendo prek
dashboarda ali `core.agenda.add(..., kind=...)`):
`python` (standardni RSI build) · `modify` (refaktor, zahteva spremembo) ·
`autonomous` (spec+implement) · `team` (multi-agent adversarial) · `fork`
(raziskovanje N pristopov → izvedi najboljšega) · `plan` (dekompozicija velikega
cilja → podnaloge v agendo).

**CLI/terminal ostaja kot varnostna (rescue) pot** — `rob dev` še vedno deluje
za ročni nadzor, stop/start/reset, ročni claude itd. Daemon in CLI sobivata
(`dev_cli.cmd_serve` je idempotenten — daemon ne podvaja že-tekočih storitev).
Ročni `dev_cli.py --serve` ostane delujoč za trenutni dvig storitev brez daemona.

**Tailscale** (varen remote dostop iz drugih naprav) je **ročni predpogoj**:
namesti Tailscale (`tailscale.com/download`), `tailscale login`, `tailscale up` —
potem dashboard dosegljiv tudi s Tailscale IP iz laptopa. **Varnostno**: dashboard
API ni avtenticiran (CORS `*`), zato **nikoli ne odpiraj javnega porta 8787/4010**
na internet — uporabi Tailscale/zaprti VPN, ne odprt port.

Konfiguracija proxyja živi v `bridges/litellm_config.yaml` — modeli so
preslikani na Anthropic-kompatibilen DeepSeek endpoint (`api.deepseek.com/anthropic`),
krovni ključ (`master_key`) in `drop_params: true` pa preprečujejo
401-avtentikacijske napake in zlom proxyja.

Orkestracija **nikoli** ne upravlja porta 4000 — ta ostane rezerviran za
uporabnikov obstoječi proxy in ni vpleten v nobeno preverjanje ali čiščenje.

## 🤖 Avtonomna orkestracija (RSI/GStack) — delovanje in roadmap F0–F6

Jedro avtonomije je **Python RSI/GStack orkestrator** (`./rob build` →
`core/orchestrator.py` → gbrain → graphify → gstack → hermes → **LoopX
self-heal**). LoopX poganja verifikacijsko in samoozdravitveno zanko:
pytest → DeepSeek popravi kodo → **100 % zelen** (do 5 poskusov).

Dashboard na **:8787** delegira avtonomni build na isto RSI zanko prek
`POST /api/build`, zato je izvedbeno jedro **eno** (ne dve).

Vsa avtonomna orkestracija prek CLI:

```bash
python run_swarm.py --target <modul> --directive "<navodilo>"        # RSI build (Python/Markdown/HTML)
python run_swarm.py --autonomous --target <m> --directive "<cikel>"  # F2: spec + implement
python run_swarm.py --process-agenda                                 # F3: obdela čakalno vrsto naročil
python run_swarm.py --item <id>                                     # P1: obdela ENO naročilo (daemon)
python run_swarm.py --business "<poslovna ideja>"                    # F6: predlog → glavna knjiga
rob daemon --status / --once / --stop                               # P1: upravljanje 24/7 daemona
python evaluate_autonomy.py --dry-run                               # P5: strukturna preverba eval-a (brez LLM)
python evaluate_autonomy.py --workers 4                             # P5: eval lestvica z vzporednimi case-i
python -m core.actions_runtime --port 8788                          # Korak 5: enotna runtime app vseh 18 modulov
python -m core.actions_graph                                        # Korak 5: realni odvisnostni robovi (JSON)
```

Dosežene faze:

| Faza | Zmogljivost |
|---|---|
| **F0** | Enotno izvedbeno jedro — `/api/build` delegira na RSI/GStack |
| **F1** | RSI za vse tipe izdelkov (Python → pytest, Markdown, HTML) |
| **F2** | Avtonomni delovnik — nalogo razdeli na spec + implement |
| **F3** | Agenda / čakalna vrsta naročil + med-run obdelava |
| **F4** | Trajni RSI spomin (samorazvoj / RDI) — LLM se uči iz napak |
| **F5** | Revizijski dnevnik + števec LLM-klicov (nadzor stroškov) |
| **F6** | Poslovni avtomat: ideja → predlog → glavna knjiga (prilivi/stranke) |
| **P0** | SWE-bench stila samo-eval avtonomnosti — eval lestvica (**14 case-ov**: 8 funkcijskih/Pydantic/FastAPI/avtonomnih + **6 realnih bugfix na zlatih modulih**), `evaluate_autonomy.py` meri prehod rate; **PR gate + nočni eval v CI** |
| **P1** | Avtonomni daemon (24/7 master proces): prazni agendo, sam predlaga naloge (goal autonomy), teče periodične jobe, heartbeat `.rob_ai/daemon.json` |
| **P2** | Zapri zanko neuspeha: fail-fast (ostri podpis), fix-task v agendo (konzumira `next_step`), poštena metrika iz `run_reviews` |
| **P3** | Surgical fix + diagnose-first: minimalen diff brez re-scaffolda, targeted verifikacija, dejanski vzrok iz pytest izhoda (ne glava) |
| **P4** | MODIFY false-green guard (`kind="modify"`): modifikacije morajo dejansko spremeniti modul — sicer neuspeh, ne tiho zelen |
| **P5** | **Routing agentov v daemonu**: naloga iz agende se obdela z agentom po `kind` — `team` (adversarial), `fork` (raziskovanje), `plan` (dekompozicija), `modify`, `autonomous`, `fix_loop`, `python` |
| **P6** | **P1 konsolidacija prek daemona**: String Core (`slugify`+`truncate_text`+`text_proc` → `string_ops`) + Config Core (`env_config`+`ini_config`+`config_manager` → `config_loader`) — 6 → 2 modulov, daemon zgradil z Test-Locked testi |

Command-Center dashboard ponuja poglede: **Command Center** (pregled + obsidian
graf), **Pogovor** (glasovni vnos + TTS odgovor, izbira glasu Charon/Orus/...),
**Agenda**, **Artefakti** (pregled dokumenta + prenos Word/PDF/HTML), **GBRAIN**
(54 gstack skillov) in **Agenti**. ROB razume razliko med pogovorom in nalogo:
nalogo zabeleži v agendo in izvede, pogovor odgovori z živim kontekstom
(datum/ura + vreme + splet). Google integracije (Drive/Email/Calendar) zahtevajo
autorizacijo (`client_secret.json`, redirect
`https://localhost:8787/api/google/oauth2callback`).

## 💻 Navodila za uporabo CLI (`./rob`)

Swarm motor `./rob` omogoča popolno upravljanje sistema preko kratkih ukazov:

### 1. Zagon celotne sistemske verifikacije

Pogani celotno testno matriko nad vsemi vgrajenimi moduli:

```bash
./rob test
```

### 2. Arhitekturni pregled in samo-diagnostika

Izvede analizo odvisnosti, preveri AST graf in vrne predloge za optimizacijo:

```bash
./rob review
```

### 3. Avtonomna gradnja modula za stranko

Predajte nalogo motorju. Motor bo ustvaril celotno strukturo datotek,
napisal logiko, generiral teste in zaklenil kodo le, če vsi testi
minejo s statusom 100 % green:

```bash
./rob build ime_modula "Natančen opis zahteve naročnika ali specifikacija funkcionalnosti"
```

Primer:

```bash
./rob build client_pdf_parser "Zgradi modul za ekstrakcijo podatkov iz PDF računov z FastAPI endpointom in Pydantic validacijo."
```

## 🛡️ Kako deluje RSI samozdravstvena zanka

Jedro avtonomne gradnje je `LoopXEngineBridge` (`core/loopx_bridge.py`).
RSI zanka (`_heal_loop`) deluje takole:

1. **Verifikacija** — po tipu izdelka (`_verify`): Python → pytest (sandbox)
   + ruff; Markdown/HTML → strukturna preverba.
2. **Zelen** — ob uspehu se v GBRAIN zapiše `VERIFIED GREEN` in zanka konča.
3. **Rdeč → heal** — traceback se posreduje DeepSeek-u (`_heal_once`), ki vrne
   popravke; ti se zapišejo v `actions/<mod>/` in verifikacija se ponovi.
4. **Ponavljanje** — do 5 poskusov (`max_attempts`); identična ponavljajoča se
   napaka (ostri podpis `tip + padel test`, ≥ 3×) zgodaj prekine zanko (fail-fast).
5. **Neuspeh** — tek se zaključi kot `FAILED`, napaka se zapiše v GBRAIN
   blacklist (učenje). Ob neuspelem buildu se modul avtomatsko povrne na pred-build stanje (snapshot v `.loopx/rollback/`; izklop: `LOOPX_ROLLBACK_ON_FAIL=false`).

Sočasni buildi istega modula se varujejo z atomic target-lockom. Ločena
`RSISelfHealingEngine` živi kot samostojen modul v
`actions/rsi_engine/`, ne kot jedro.

### 🔁 Zapri zanko neuspeha (fix-loop + surgical + diagnose-first)

Vsak padel build se zdaj **samodejno popravi** — ne le zapiše lekcije:

- **C1 — Fail-fast**: ponavljajoče napake se štejejo po **ostrem podpisu**
  (`tip + padel test`, `_error_signature`) — dve različni napaki istega tipa se
  ne seštejeta (napredek se ne prekine). `last_traceback` ohrani REALEN traceback
  za diagnozo; stale per-target locki se poberejo (`_pid_alive`).
- **C2 — Fix-task**: ob neuspehu `RunReviewer.maybe_enqueue_fix` vvrže v agendo
  **konkretno fix nalogo**, ki **konzumira `next_step`** (odločitev iz presoje),
  nosi padel test + napako + `CHANGE APPROACH` direktivo. Guarda: max 3/target,
  skip če pending.
- **C3 — Surgical fix**: fix naloga teče prek `run_surgical` — **minimalen diff
  brez re-scaffolda** (preskoči gstack manifest + hermes stube), **ciljna
  verifikacija** (`pytest -k <test>` med healom) + **poln no-regression gate** na
  koncu. 1-vrstični bug → zelen v 1 poskusu (prej: re-scaffold celega modula).
- **Diagnose-first**: `_verify` zdaj iz pytest izhoda izlušči **dejanski vzrok**
  (prvi FAILURES blok + short summary), ne 400-znakovne glave; `NoTestsCollected`
  klasifikacija za stub module; kadar vzrok ni jasen, LLM **najprej prebere vse
  datoteke in diagnosticira**, šele nato popravi.
- **Poštena metrika**: `meta_eval` bere `run_reviews` (čista tabela), **ne**
  `task_history` (onesnažen s `test_proj`) — realna uspešnost, ne več lažnih
  številk; snapshot verzijski gate prepreči lažno regresijo.
- **MODIFY — modifikacije dejansko delujejo** (`kind="modify"`): naloga
  "izboljšaj X"/refaktor mora DEJANSKO spremeniti modul. Dva mehanizma:
  (1) `LoopX._module_fingerprint` primerja modul pred/po — zelen brez spremembe
  → neuspeh; (2) če direktiva imenuje nov test file (npr. `test_truncate_start.py`),
  `_verify` vrne **rdeč**, dokler ga heal ne ustvari in ne implementira funkcije
  → zelen šele ko je sprememba res izvedena (živo: `truncate_start` dodan +
  31/31 testov zelenih).

**Dogfood (realno delo, avtonomno)** — več krogov:
- **Dogfood 1** (5 util modulov): uspešnost modulov **40 % → 80 %** (fix-zanka
  popravila 2/3 padle); metrika 28.6 % → 33.3 %; `env_config` (prej nepopravljiv
  stub) ozdravljen po diagnose-first.
- **Dogfood 2** (6 modulov): **100 % prva-build** (zero fix nalog) — diagnose-first
  je ključni diferencator (40 % → 100 %); metrika → 48.4 %.
- **Dogfood 3** (5 KOMPLEKSNIH nalog: multi-file, medmodulne odvisnosti, refaktor,
  dvoumna direktiva, reuse): **4/5 resnično zelenih** + **odkrit false-green pri
  refaktorju** → `kind="modify"` guard. Metrika → 55.6 %.

## 🔄 Deset zank (Zanke 1–10)

Poleg RSI samozdravljenja (ki popravlja MODULE `actions/*`) ima sistem štiri
samorazvojne zanke (spomin, presoja, orkestracija, meta-evalvacija), štiri
sposobnostne zanke (načrtovanje, koordinacija, napoved, raziskovanje), eno
zanko učenja uteži (RLAIF) in eno meta-zanko (avtonomija ciljev):

| Zanka | Modul | Kaj dela |
|---|---|---|
| **1 · spomin** | `core/memory_consolidation.py` | Konsolidacija: surove epizode (`task_history`) → semantične lekcije (`semantic_memories`). Lekcije se vbrizgajo v heal prompt (kumulativno učenje). |
| **2 · presoja** | `core/run_review.py` | Post-run samoevalvacija: klasificira VZROK izida na nivoju odločitve (`spec_mismatch`/`llm_error`/…), ne le testa; **ob neuspehu vvrže konkreten fix task v agendo** (`maybe_enqueue_fix`, konzumira `next_step`). |
| **3 · orkestracija** | `core/self_improve.py` + `core/prompt_registry.py` + `core/tuning.py` | RSI nase: samorazvoj **promptov** (guard + regresijski testi + rollback) in **parametrov** (`max_attempts`, `repeat_abort_after` — z mejami + rollback). |
| **4 · meta-evalvacija** | `core/meta_eval.py` | Meri, ali izboljšave dejansko pomagajo (uspešnost, povp. LLM klici); **poštena metrika iz `run_reviews`** (ne `task_history` — brez `test_proj` onesnaženja), verzijski gate; ob regresiji **avtomatsko povrne** prompt + parametre. |
| **5 · načrtovanje** | `core/task_planner.py` | Dolgoročno načrtovanje: LLM razbije kompleksen cilj na urejene podcilje in vsakega izvede skozi RSI (večkorakne naloge). **V daemonu**: `kind="plan"` → podnaloge v agendo. |
| **6 · koordinacija** | `core/team.py` | Multi-agent adversarial: planner → critic → builder → verifier; critic izzove načrt pred izvedbo. **V daemonu**: `kind="team"`. |
| **7 · napoved** | `core/world_model.py` | Svetovni model: iz lastnih trajektorij napove uspešnost, pričakovan LLM strošek in verjeten vzrok neuspeha. |
| **8 · raziskovanje** | `core/fork.py` | Paralelni sprint: razišče N pristopov, vsakega oceni (world model + critic), **izvede najboljšega** (explore_and_run). **V daemonu**: `kind="fork"`. |
| **9 · učenje uteži** | `core/rlaif.py` | RLAIF podatkovni cevovod: iz trajektorij izlušči (chosen, rejected) pare in izvozi JSONL (DPO) za fine-tuning. |
| **10 · avtonomija** | `core/goal_autonomy.py` | Avtonomija ciljev: sistem iz svojih šibkih točk predlaga naslednjo nalogo; varni reverzibilni koraki se izvedejo samodejno. |

```bash
./rob consolidate      # Zanka 1: strdi epizode → semantične lekcije
./rob improve          # Zanka 3: samorazvoj promptov (predlog → guard → test → promocija)
./rob tune             # Zanka 3: samorazvoj parametrov (max_attempts, repeat_abort_after)
./rob meta             # Zanka 4: trenutne metrike (uspešnost, povp. LLM klici)
./rob plan "cilj"      # Zanka 5: dekompozicija cilja na podcilje
./rob team "cilj"      # Zanka 6: multi-agent adversarial koordinacija
./rob predict "cilj"   # Zanka 7: napoved izida (uspešnost, LLM strošek, vzrok)
./rob fork "cilj"      # Zanka 8: paralelno raziskovanje pristopov
./rob rlaif            # Zanka 9: učenje preferenc (statistika / izvoz podatkov)
./rob goals            # Zanka 10: avtonomija ciljev (predlaga naslednje naloge)
```

Skupaj teh deset zank zapre "sistem izboljšuje lastno hitrost izboljševanja".

## 🔧 Nadgradnje — agentičnost, spomin, kontekst, paralelizem, runtime

- **Agentic tool-use v RSI zanki** (`core/loopx_bridge.py`): LLM v heal zanki kliče
  orodja `read_file`/`write_file`/`list_files`/`search_memory`/`skill` in iterira
  (OpenAI function-calling; `LLM_TOOL_USE`), namesto krhke `### FILE:` konvencije.
- **Semantični spomin** (`core/embedder.py` + `core/memory_consolidation.py`):
  lekcije se vektorizirajo prek Gemini `gemini-embedding-2`; `recall` uredi po
  kosinusni podobnosti (prag 0.20) z leksikalnim padcem ob izpadu
  (`MEMORY_EMBEDDINGS`, `--backfill-embeddings`).
- **Upravljanje konteksta** (`LLM_HEAL_*`): budget heal prompta, izločitev test
  datotek iz sources (~55 % manj tokenov), trim agentic messages, zajem `usage`.
- **GStack skilli kot LLM orodje** (`core/skill_bridge.py`): LLM lahko pokliče
  `skill("spec")` in dobi strnjen procesni vodič (cap 6k, brez boilerplate-a).
- **Paralelizem** (`core/fork.py`, `evaluate_autonomy.py`): vzporedno točkovanje
  variant in eval case-ov (`--workers`); atomski zapis `graph.json`; `DB_WRITE_LOCK`
  za sočasne pisalce.
- **actions/ kot pravi runtime** (`core/actions_runtime.py` + `core/actions_graph.py`):
  enotna FastAPI app, ki mount-a vseh 18 modulov pod `/api/<modul>/` z middleware
  verigo (auth → rate-limit → audit → deljeni EventBus); dashboard graf kaže
  REALNE odvisnosti (AST-sken importov), ne trdo-kodiranih.
- **Avto-rollback** (`LOOPX_ROLLBACK_ON_FAIL`): ob neuspelem buildu se modul povrne
  na pred-build stanje (snapshot v `.loopx/rollback/`).
- **CI** (`.github/workflows/ci.yml`): PR gate (pytest + eval dry-run) + nočni eval
  (poln eval z LLM + Docker, poročilo kot artifact).

## 🧪 Testni standardi

V projektu velja pravilo **Zero Flaky Tests**. Koda ne velja za
dokončano, dokler ne preteče celoten nabor testov.

Za neposreden zagon testov posameznega modula:

```bash
pytest actions/rsi_engine
```

Za zagon celotnega master suite-a:

```bash
pytest
```

## 📄 Licenca

Ta projekt je zaščiten in namenjen interni ter produkcijski uporabi
v okviru Rob AI Studio okolja. Vse pravice pridržane.
