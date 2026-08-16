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
| **Možgani** | LLMBridge / GBrain / AST | Razumevanje konteksta, detekcija funkcijskih tarč, izračun kompleksnosti in generiranje optimiziranih rešitev. |
| **Roke** | `./rob` CLI Swarm Engine | Avtonomna gradnja modulov, upravljanje datotečnega sistema, izvajanje testnih matrik in orkestracija delotokov. |
| **Zavora** | `enterprise_rsi_engine` + Pytest | Neprebojni zaščitni ščit (BehaviorGuard). Izvede AST validacijo, ujame trace-back ob padcu in vrne sistem v varno stanje ob neuspehu. |

```
┌──────────────────────────────────────────────────────────┐
│                NAROČNIK / STRANKA (Prompt)               │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│             MOŽGANI: LLMBridge + Graphify + AST          │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│              ROKE: ./.rob Swarm Execution Engine         │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│     ZAVORA: RSI Closed-Loop + Pytest BehaviorGuard       │
└──────────────┬─────────────────────────────┬─────────────┘
               │                             │
     [❌ Pytest Pade / Traceback]      [✅ 100% ZELENO]
               │                             │
               ▼                             ▼
┌──────────────────────────────┐  ┌────────────────────────┐
│ Samodejno Samozdravljenje    │  │ Produkcijski Zaklep    │
│ (Do 5 iteracij s feedbackom) │  │ in Dostava Stranki     │
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
- **Zero-Downtime Rollback** — če koda po vseh poskusih ne doseže 100-%
  zelene verifikacije, sistem izvede samodejni rollback na izvirno kodo.
  Produkcijsko okolje nikoli ne ostane v porušenem stanju.
- **Jedrnati CLI ukazi** — brez mikromanagementa. Sistem se krmili s
  kratkimi, direktnimi ukazi.

## 📁 Arhitektura projektne strukture

```
Rob AI Studio/
├── rob                               # Glavni CLI izvršljivi motor (Swarm Engine)
├── pytest.ini                        # Konfiguracija za globalno testno mrežo
├── bridges/
│   └── llm_bridge.py                 # Enoviti vmesnik za LLM komunikacijo (DeepSeek/OpenAI)
├── actions/
│   ├── enterprise_rsi_engine/        # Avtonomni motor za samoizboljševanje in testiranje
│   │   ├── __init__.py
│   │   ├── schemas.py                # Pydantic contract modeli
│   │   ├── enterprise_rsi_engine.py  # AST Analyzer & Self-Healing Core
│   │   ├── main.py                   # FastAPI vmesnik za RSI storitve
│   │   └── test_enterprise_rsi_engine.py  # Testni paket modula
│   └── [ostali produkcijski moduli]/ # Poslovna logika za stranke in aplikacije
└── tests/
    ├── test_architecture.py          # Preverjanje celovitosti strukture
    ├── test_integration.py           # Integracijski testi
    └── test_master_suite.py          # Celovita sistemska testna matrika
```

## 🛠️ Hitra namestitev in zagon

### 1. Kloniranje repozitorija in priprava okolja

```bash
git clone https://github.com/vash-org/rob-ai-studio.git
cd "rob-ai-studio"

# Ustvarjanje in aktivacija virtualnega okolja
python3 -m venv venv
source venv/bin/activate

# Namestitev odvisnosti
pip install -r requirements.txt
```

### 2. Konfiguracija okoljskih spremenljivk

Ustvarite datoteko `.env` v korenskem imeniku projekta:

```
DEEPSEEK_API_KEY=vaš_deepseek_api_ključ
OPENAI_API_KEY=vaš_openai_api_ključ
ENVIRONMENT=production
```

### 3. Zagon Claude Code prek LiteLLM + DeepSeek (`rob dev`)

`Claude Code` privzeto kliče Anthropic API. Da ne kurimo dragih Anthropic
tokenov, se projekt nasloni na enotno **Python orkestracijo** (`core/dev_cli.py`,
launcher `dev.bat` / `rob dev`), ki dvigne [LiteLLM](https://www.litellm.ai/)
proxy in preslika zahtevke na **cenejši DeepSeek API** z vašim
`DEEPSEEK_API_KEY`. Poleg proxyja dvigne še **Command-Center dashboard**:

- **Proxy LiteLLM na :4010** (lasten, izoliran)
- **Command-Center dashboard** na **:8787** via `bun run src/server.ts`
  (`/api/health` · `/api/ledger` · `/api/runs` · `POST /api/run`)

Vse v enem ukazu (Windows `dev.bat`, Linux/WSL `./rob dev`):

```bash
dev.bat                     # proxy :4010 + dashboard :8787 v ozadju, poveže claude;
                            # po izhodu sam ugasne samo kar je zagnal. Port 4000 se ne dotakne.
dev.bat --init              # dry-run: preveri config, ključ, porta 4010/8787 in PATH.
dev.bat --proxy-only        # samo LiteLLM na 4010 v ospredju.
dev.bat --dashboard-only    # samo Command-Center (bun run src/server.ts) na 8787.
dev.bat --claude-only       # samo claude ob že obstoječem proxyju na 4010.
```

Na Linux/WSL uporabi `./rob dev [--init|--proxy-only|--dashboard-only|--claude-only]`,
ki delegira na isti Python modul.

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
python run_swarm.py --business "<poslovna ideja>"                    # F6: predlog → glavna knjiga
python evaluate_autonomy.py --dry-run                               # P5: strukturna preverba eval-a (brez LLM)
python evaluate_autonomy.py                                         # P5: SWE-bench stila samo-eval avtonomnosti
```

Dosežene faze (roadmap je v dashboardu na `/roadmap`):

| Faza | Zmogljivost |
|---|---|
| **F0** | Enotno izvedbeno jedro — `/api/build` delegira na RSI/GStack |
| **F1** | RSI za vse tipe izdelkov (Python → pytest, Markdown, HTML) |
| **F2** | Avtonomni delovnik — nalogo razdeli na spec + implement |
| **F3** | Agenda / čakalna vrsta naročil + med-run obdelava |
| **F4** | Trajni RSI spomin (samorazvoj / RDI) — LLM se uči iz napak |
| **F5** | Revizijski dnevnik + števec LLM-klicov (nadzor stroškov) |
| **F6** | Poslovni avtomat: ideja → predlog → glavna knjiga (prilivi/stranke) |
| **P5** | SWE-bench stila samo-eval avtonomnosti — `evaluate_autonomy.py` meri prehod rate (`rob eval`), ne blokira CI |

Dashboard poleg modulov in zgodovine izvedb ponuja še **Agenda** (dodaj
čakajoče naloge) in **Poslovanje** (glavna knjiga podjetja) v plošči
**Moduli / Naloge**, ter Google integracije (Drive/Email/Calendar) — ti
zahtevajo autorizacijo (`client_secret.json`, redirect
`http://localhost:8787/api/google/oauth2callback`).

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

Glavna varnostna komponenta projekta je `RSISelfHealingEngine`, ki izvede
naslednji algoritem ob vsakem posegu v kodo:

1. **Baseline Check** — preveri, ali obstoječa koda prestane vse teste.
   Če je osnova porušena, se postopek ustavi.
2. **AST Parsing** — zgenerirano kodo preveri z Python `ast.parse()`.
   Sintaktične napake se zavrnejo pred izvajanjem.
3. **Izolirano testiranje** — koda se začasno zapiše v ciljni modul, nato
   pa se v izoliranem procesu požene `pytest`.
4. **Feedback Loop** — ob padcu kateregakoli testa engine ujame točen
   traceback, ga posreduje LLM-u kot striktno navodilo za popravek ter
   ponovi postopek (do 5 iteracij).
5. **Lock ali Rollback** — ob 100-% zelenih testih se koda zaklene. Ob
   neuspehu po 5 poskusih se sproži neposredni rollback na izvirnik.

## 🧪 Testni standardi

V projektu velja pravilo **Zero Flaky Tests**. Koda ne velja za
dokončano, dokler ne preteče celoten nabor testov.

Za neposreden zagon testov posameznega modula:

```bash
pytest actions/enterprise_rsi_engine
```

Za zagon celotnega master suite-a:

```bash
pytest
```

## 📄 Licenca

Ta projekt je zaščiten in namenjen interni ter produkcijski uporabi
v okviru Rob AI Studio okolja. Vse pravice pridržane.
