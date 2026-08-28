# 🤖 Rob System — Avtonomni AI Inženirski Stroj

Rob System je **avtonomni AI inženirski stroj**: podaš visokonivojski cilj, sistem
sam zgenerira specifikacijo, arhitekturo, kodo **in teste**, jih požene, ob napaki
**sam pozdravi** (RSI zanka) in dostavi delujoč izdelek — ali pa eksplicitno
`FAILED` s posnetkom napake in naučeno lekcijo.

Sistem je grajen iz dveh izvedbenih plasti, ki si delita **isto** Python RSI jedro:

| Plast | Kaj gradi | Primeri |
|---|---|---|
| **Python RSI / GStack** (`core/`) | Programske module: koda + pytest | `actions/<modul>/` — API storitve, validacija, domene |
| **TS Hermes** (`src/`) | Produkte: dokument, UI, skripta | `out/*` artefakti (rezultati teka) |

> **Ključno dejstvo:** dashboard (`POST /api/build`) in `./rob build` kličeta
> isto jedro (`run_swarm.py` → `core/orchestrator.py`).

---

## 🧭 Kako sistem deluje (flow)

```
        VHOD / NADZOR
   ./rob CLI · dashboard :8787 · daemon 24/7 · Gmail poll
                        │
                        ▼  naloga
   ┌────────────────────┴─────────────────────┐
   ▼                                          ▼
┌───────────────────────┐         ┌────────────────────────────┐
│ TS Hermes (produkti)  │         │ Python RSI (moduli)        │
│ planner→builder→qa    │         │ gbrain→graphify→gstack→    │
│ ledger-first (SQLite) │         │ hermes→loopx               │
└───────────┬───────────┘         └──────────────┬─────────────┘
            │                                    │
            ▼                                    ▼
     out/* produkti                     actions/<modul>/  (koda + testi)
                                        .rob_ai/  (spomin: memory.db, graph.json)
```

### RSI zanka (srce sistema) — `core/loopx_bridge.py`

```
pytest → ZELEN?  ────────────✅  VERIFIED GREEN (zapis v GBRAIN)
   │  RDEČ (traceback)
   ▼
DeepSeek LLM popravi kodo → ponovna verifikacija
   │
   └── ≤5 poskusov ──  uspeh: ✅ ZELEN
                      ──  neuspeh: ❌ FAILED + blacklist v GBRAIN (učenje)
                                    + avtomatski rollback na pred-build stanje
```

Vsak modul se gradi v zaporedju: **gbrain → graphify → gstack → hermes → loopx**
(`core/orchestrator.py`):

1. **GBRAIN** — trajni spomin (SQLite): prepovedani vzorci napak, zgodovina.
2. **GRAPHIFY** — AST sken kode → graf odvisnosti (`graph.json`) za kontekst.
3. **GSTACK** — arhitekturna specifikacija (manifest + `spec_hint` → LLM).
4. **HERMES** — ogrodje `actions/<mod>/` (stub-i).
5. **LOOPX** — verifikacijska in samoozdravitvena zanka (pytest → heal → ≤5×).

---

## 👥 Kdo dela (vloge)

| Vloga | Komponenta | Odgovornost |
|---|---|---|
| **Vhod** | `./rob` · dashboard · daemon | sprejme nalogo in jo vrže v orkestracijo |
| **Orkestrator (moduli)** | `RobAIOrchestrator` (`core/orchestrator.py`) | spelje gbrain → graphify → gstack → hermes → loopx |
| **Orkestrator (produkti)** | TS `Runner` (`src/`) | dogodek → `foldState` → reduktorji → `Command[]` → izvedi |
| **Spomin** | GBrain (`core/gbrain_bridge.py`) | blacklisti, zgodovina, semantične lekcije |
| **Graf kode** | Graphify (`core/graphify_bridge.py`) | AST sken → odvisnostni kontekst |
| **Arhitekt** | GStack (`core/gstack_bridge.py`) | manifest + spec_hint (blueprint za LLM) |
| **Ogrodje** | Hermes (`core/hermes_bridge.py`) | ustvari `actions/<mod>/` stub-e |
| **Verifikacija + zdravljenje** | LoopX (`core/loopx_bridge.py`) | pytest → DeepSeek popravi → ≤5× → zelen / FAILED |
| **LLM** | DeepSeek (`core/llm_client.py`, `deepseek-v4-flash`) | generira kodo in popravke |
| **24/7 avtonomija** | Daemon (`core/daemon.py`) | prazni agendo, sam predlaga naloge, teče vzdrževalne jobe, piše heartbeat |
| **Končni produkt** | 30 `actions/` modulov | delujoče API storitve s testi |

---

## 📦 Rezultati

- **`actions/<modul>/`** — delujoči moduli: koda + Pydantic sheme + FastAPI + pytest testi (vsi zeleni).
- **`out/*`** — produktni artefakti (dokumenti, UI, skripte) iz TS Hermes plasti.
- **`.rob_ai/`** — trajno stanje: `memory.db` (GBRAIN spomin), `graph.json` (graf), `daemon.json` (heartbeat), `agenda.json` (čakalna vrsta).
- **Enotna runtime app** (`core/actions_runtime.py`, port **:8788**) — **27 API modulov** pod eno verigo: `auth → rate-limit → audit → event-bus` (middleware). 3 moduli so knjižnice brez API-ja (`csv_parser`, `iso8601_util`, `retry_wrapper`).
- **Enterprise API moduli** (arhitekturna revizija, 2026): `webhook_dispatcher` (HMAC + retry + DLQ), `api_version_manager` (SemVer + canary + BC-break), `secret_rotation` (double-buffer + audit).

---

## 💡 Zakaj je uporabno

- **Naročnik poda cilj → dobi 100-% testiran modul.** Ni "tu je koda, pa srečno" —
  sistem sam napiše teste, jih požene in popravi, dokler niso zeleni.
- **Samozdravljenje (RSI):** napaka se avtomatsko popravi (do 5 poskusov), ne
  zahteva človeškega debuganja.
- **Učenje iz napak:** vsak neuspeh postane blacklist + semantična lekcija v GBRAIN,
  ki izboljša vse prihodnje teke.
- **24/7 avtonomija:** daemon sam prazni agendo, predlaga nove naloge iz šibkosti
  sistema in teče vzdrževalne jobe (konsolidacija spomina, eval).
- **Enterprise API pokritje:** 30 modulov od edge (gateway, rate-limit, auth) do
  domene (invoice, warehouse) in observability (metrike, audit, poročila).
- **Nadzor:** CLI (`./rob`) + Command-Center dashboard (:8787) + CI gate.

---

## 🚀 Hitra namestitev

> 📋 **Popolna, korak-po-korak preverjena navodila (vklj. odpravljanje napak):**
> [docs/INSTALL.md](docs/INSTALL.md)

**Predpogoji:** Python **3.11** (ne 3.14), `git`. Za dashboard še Node + Bun + LiteLLM + Claude Code CLI.

```bash
# 1. Klon in odvisnosti
git clone https://github.com/robAItech/rob-system.git
cd rob-system
python -m pip install -r requirements-dev.txt

# 2. Konfiguracija (obvezno pravi DeepSeek ključ)
cp .env.example .env
#   → v .env vpiši DEEPSEEK_API_KEY=sk-...

# 3. Preverba
./rob test          # 347 testov — mora biti 100% zeleno

# 4. Prvi resničen build (kliče DeepSeek)
./rob build testmod "Izdelaj Python modul testmod v actions/testmod/. Funkcija add(a,b) vrne a+b. Vsebuj pytest test, vsi testi 100% zeleni."
```

> ⚠️ **Windows:** `./rob` teče v **Git Bash** (ali WSL). V cmd/PowerShell uporabi
> `bash rob <ukaz>` (ali `dev.bat` za dashboard).

**Dashboard + proxy:**

```bash
bun install
./dev                # proxy :4010 + Command-Center :8787 + poveže Claude
# Dashboard: http://localhost:8787/command
```

---

## 🛠️ Ukazi (`./rob`)

| Ukaz | Kaj naredi |
|---|---|
| `./rob test` | Celotna testna matrika (347 testov) |
| `./rob review` | LLM arhitekturna revizija (pytest + telemetrija + predlogi) |
| `./rob build <mod> "<direktiva>"` | Avtonomno zgradi modul (RSI zanka) |
| `./rob eval` | SWE-bench stila samo-eval avtonomnosti (`--dry-run` brez LLM) |
| `./rob daemon` | Avtonomni daemon 24/7 (`--once/--status/--stop/--serve`) |
| `./rob dev` | Proxy + dashboard + claude (`--serve` = avtonomno v ozadju) |
| `./rob dashboard` | Live TUI dashboard |
| `./rob up` / `./rob down` | Docker ekosistem gor / dol |
| `./rob deploy` | Generira docker-compose + gateway rute + dvigne |
| `./rob visual-qa <pot\|url>` | Vizualni QA prek Ollama/Gemma |
| `./rob learn` / `./rob patterns` | Learning dashboard / prečni vzorci neuspehov |
| `./rob team` / `./rob plan` / `./rob fork` | Multi-agent koordinacija / dekompozicija / raziskovanje |
| `./rob meta` / `./rob tune` / `./rob improve` | Meta-eval / samouglašanje / samorazvoj |
| `./rob goals` / `./rob predict` / `./rob rlaif` | Avtonomija ciljev / svetovni model / preference |
| `./rob reflect` / `./rob consolidate` | Strateška refleksija / konsolidacija spomina |

---

## 🏛️ Arhitektura (struktura)

```
rob-system/
├── rob                     # CLI motor (test / build / eval / daemon / dev / ...)
├── core/                   # Python RSI jedro
│   ├── orchestrator.py     #   gbrain → graphify → gstack → hermes → loopx
│   ├── loopx_bridge.py     #   RSI zanka: pytest → DeepSeek heal → ≤5×
│   ├── daemon.py           #   avtonomni daemon 24/7 (P1)
│   ├── dev_cli.py          #   orkestracija proxy+dashboard+claude (P4)
│   ├── actions_runtime.py  #   27 API modulov kot enotna app (:8788)
│   ├── actions_graph.py    #   realni odvisnostni robovi modulov
│   ├── gbrain_bridge.py    #   trajni spomin (SQLite)
│   ├── graphify_bridge.py  #   AST graf kode
│   ├── gstack_bridge.py    #   arhitekturna specifikacija
│   ├── hermes_bridge.py    #   ogrodje actions/<mod>/
│   ├── llm_client.py       #   DeepSeek LLM
│   └── ...                 #   agenda, run_review, meta_eval, embedder, skill_bridge ...
├── actions/                # 30 produkcijskih modulov (koda + testi)
├── src/                    # TS Command-Center dashboard (server.ts, :8787)
├── bridges/litellm_config.yaml   # DeepSeek proxy routing (:4010)
├── scripts/                # autostart.bat + register-autostart.ps1 (daemon ob prijavi)
├── repos/                  # vključeni paketi: gbrain, gstack, graphify,
│                           # hermes-agent, loopx, gbrain-evals (nič ločenega pip install)
├── evaluate_autonomy.py    # P0 eval (./rob eval)
├── .github/workflows/ci.yml# CI: PR gate + tedenski eval (sob 03:23 UTC)
└── tests/                  # 37 test datotek, 347 testov
```

### 30 Action modulov

**Edge / varnost:** `api_gateway`, `auth_vault`, `rate_limiter`, `circuit_breaker`,
`feature_flag`, `api_version_manager`, `secret_rotation`
**Messaging / orkestracija:** `event_bus`, `task_queue`, `saga_orchestrator`, `webhook_dispatcher`
**Podatki / validacija:** `csv_parser`, `json_deep_merge`, `string_ops`, `iso8601_util`, `contract_schema_engine`
**Domena:** `currency_converter`, `invoice_calc`, `isbn_validator`, `warehouse_inventory`, `rsi_engine`
**Observability:** `observability_metrics`, `audit_trail`, `report_builder`, `mailer`
**Infra:** `config_loader`, `deployment_manager`, `nexus_command_deck`, `cache_layer`, `retry_wrapper`

---

## ✅ Testi in eval

- **Poln suite:** `347` testov / `37` datotek — vodi `./rob test` (`pytest tests/`).
- **Master suite** poleg tega požene pytest na vsakem tracked Action modulu.
- **CI** (`.github/workflows/ci.yml`): PR gate = pytest + eval dry-run; tedenski
  eval avtonomnosti (sobota 03:23 UTC).
- **Eval lestvica (P0, SWE-bench stil):** 14 case-ov (8 funkcijskih/Pydantic/FastAPI +
  6 realnih bugfix na zlatih modulih). Zadnji zabeležen rezultat: **14/14 (100 %)**
  (23. 8. 2026).
