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
