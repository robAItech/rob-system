🤖 Rob AI Studio — Avtonomni AI Inženirski StrojRob AI Studio je vaš avtonomni delovni stroj. Je vaša osebna tovarna, ki ima delujoče možgane (LLM & Context Graph), roke (./rob Swarm Motor) in avtomatske varnostne zavore (RSI zanka + Pytest), da lahko samostojno in brezkompromisno rešuje kompleksne inženirske naloge za vaše stranke in naročnike.🎯 Vizija in Standard IzvedbeRob AI Studio ni zgolj orodje za generiranje izsekov kode — je avtonomni produkcijski agregat. Zgrajen je po načelu, da je z uporabo umetne inteligence mejni strošek popolnosti blizu ničle.Sistem deluje po nepopustljivem pravilu: "Boil the ocean. Do it right. Do it with tests. Do it with documentation." Naročnik ali uporabnik poda cilj visoke ravni, Rob AI Studio pa samostojno izvede analizo, zgenerira arhitekturo, izvede AST sintaktično preverjanje, poganja Pytest verifikacijo, se ob napaki samodejno sanira in dostavi 100-% delujoč izdelek.       ┌──────────────────────────────────────────────────────────┐
       │                NAROOČNIK / STRANKA (Prompt)               │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │             MOŽGANI: LLMBridge + Graphify + AST          │
       └────────────────────────────┬─────────────────────────────┘
                                    │
                                    ▼
       ┌──────────────────────────────────────────────────────────┐
       │              ROKE: ./rob Swarm Execution Engine          │
       └────────────────────────────┬─────────────────────────────┘
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
🏛️ Arhitekturni TrikotnikSystem temelji na treh integriranih stebrih:SteberKomponentaPrimarna VlogaMožganiLLMBridge / GBrain / ASTRazumevanje konteksta, detekcija funkcijskih tarč, izračun kompleksnosti in generiranje optimiziranih rešitev.Roke./rob CLI Swarm EngineAvtonomna gradnja modulov, upravljanje datotečnega sistema, izvajanje testnih matrik in orkestracija delotokov.Zavoraenterprise_rsi_engine + PytestNeprebojni zaščitni ščit (BehaviorGuard). Izvede AST validacijo, ujamet trace-back ob padcu in vrne sistem v varno stanje ob neuspehu.🚀 Ključne ZmogljivostiAvtonomno Izvajanje Nalog za Stranke: Sprejme kompleksno zahtevo naročnika ter samostojno ustvari razrede, API endpoint-e, validacijske sheme in pripadajoče unit/integracijske teste.Closed-Loop RSI Engine (Recursive Self-Improvement): Samostojno analizira kodo preko Python AST (Abstract Syntax Tree) parserja, poišče ozka grla ter jih optimizira.5-Stopenjsko Samozdravljenje (Self-Healing Loop): Če koda ne prestane preizkusa, engine zajame natančen STDOUT/STDERR traceback, ga posreduje LLM-u in v do 5 poskusih avtonomno odpravi napako.Zero-Downtime Rollback: Če koda po vseh poskusih ne doseže 100-% zelene verifikacije, sistem izvede samodejni rollback na izvirno kodo. Produkcijsko okolje nikoli ne ostane v porušenem stanju.Jedrnati CLI Ukazi: Brez mikromanagementa. Sistem se krmili s kratkimi, direktnimi ukazi.📁 Arhitektura Projektne StrukturePlaintextRob AI Studio/
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
│   │   └── test_enterprise_rsi_engine.py # Testni paket modula
│   └── [ostali produkcijski moduli]/ # Poslovna logika za stranke in aplikacije
└── tests/
    ├── test_architecture.py          # Preverjanje celovitosti strukture
    ├── test_integration.py           # Integracijski testi
    └── test_master_suite.py          # Celovita sistemska testna matrika
🛠️ Hitra Namestitev in Zagon1. Kloniranje repozitorija in priprava okoljaBashgit clone https://github.com/vash-org/rob-ai-studio.git
cd "rob-ai-studio"

# Ustvarjanje in aktivacija virtualnega okolja
python3 -m venv venv
source venv/bin/activate

# Namestitev odvisnosti
pip install -r requirements.txt
2. Konfiguracija okoljskih spremenljivkUstvarite datoteko .env v korenskem imeniku projekta:Code snippetDEEPSEEK_API_KEY=vaš_deepseek_api_ključ
OPENAI_API_KEY=vaš_openai_api_ključ
ENVIRONMENT=production
💻 Navodila za Uporabo CLI (./rob)Swarm motor ./rob omogoča popolno upravljanje sistema preko kratkih ukazov:1. Zagon celotne sistemske verifikacijePogani celotno testno matriko nad vsemi vgrajenimi moduli:Bash./rob test
2. Arhitekturni pregled in samo-diagnostikaIzvede analizo odvisnosti, preveri AST graf in vrne predloge za optimizacijo:Bash./rob review
3. Avtonomna gradnja modula za strankoPredajte nalogo motorju. Motor bo ustvaril celotno strukturo datotek, napisal logiko, generiral teste in zaklenil kodo le, če vsi testi minerejo s statusom 100 % green:Bash./rob build ime_modula "Natančen opis zahteve naročnika ali specifikacija funkcionalnosti"
Primer:Bash./rob build client_pdf_parser "Zgradi modul za ekstrakcijo podatkov iz PDF računov z FastAPI endpointom in Pydantic validacijo."
🛡️ Kako Deluje RSI Samozdravstvena ZankaGlavna varnostna komponenta projekta je RSISelfHealingEngine, ki izvede naslednji algoritem ob vsakem posegu v kodo:Baseline Check: Preveri, ali obstoječa koda prestane vse teste. Če je osnova porušena, se postopek ustavi.AST Parsing: Zgenerirano kodo preveri z Python ast.parse(). Sintaktične napake se zavrnejo pred izvajanjem.Izolirano Testiranje: Koda se začasno zapiše v ciljni modul, nato pa se v izoliranem procesu požene pytest.Feedback Loop: Ob padcu kateratorkoli testa engine ugame točen traceback, ga posreduje LLM-u kot striktno navodilo za popravek ter ponovi postopek (do 5 iteracij).Lock ali Rollback: Ob 100-% zelenih testih se koda zaklene. Ob neuspehu po 5 poskusih se sproži neposredni rollback na izvirnik.🧪 Testni StandardiV projektu velja pravilo Zero Flaky Tests. Koda ne velja za dokončano, dokler ne preteče celoten nabor testov.Za neposreden zagon testov posameznega modula:Bashpytest actions/enterprise_rsi_engine
Za zagon celotnega master suite-a:Bashpytest
📄 LicencaTa projekt je zaščiten in namenjen interni ter produkcijski uporabi v okviru Rob AI Studio okolja. Vse pravice pridržane.
