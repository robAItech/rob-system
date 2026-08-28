# 🛠️ Namestitev Rob AI Studio — korak po korak (svež računalnik)

Preverjena navodila za namestitev na svež računalnik (Windows 10/11, Linux, WSL).
Vsak korak vodi do preverljive točke — če se zatakne, glej [odpravljanje napak](#9-odpravljanje-napak).

---

## 0. Kaj sploh je treba namestiti (pomembno!)

**gbrain, gstack, graphify, hermes in loopx SE NE nameščajo ločeno.** To so
lastni, lahki Python paketi, ki so **že vključeni v rep v `repos/`**
(`repos/gbrain`, `repos/gstack`, `repos/graphify`, `repos/hermes-agent`,
`repos/loopx`, `repos/gbrain-evals`). Ob `git clone` jih dobiš zraven;
`pytest.ini` jih samodejno doda na Python pot. Nič `pip install gbrain`, nič
kloniranja — zunanjih paketov za to ni.

Sistem ima dve ločeni ravni, ki imata **različen** seznam zahtev:

| Raven | Kaj je | Resnične zunanje zahteve |
|---|---|---|
| **A. Core engine** | `./rob test` / `./rob build` / `./rob eval` — RSI zanka kliče DeepSeek **neposredno** (httpx) | Python 3.11+, `requirements-dev.txt`, `DEEPSEEK_API_KEY`. Docker je neobvezen. |
| **B. Dashboard + Claude-proxy** | `./dev` / `dev.bat` — LiteLLM proxy :4010 + Command-Center :8787 + poveže Claude | Node, Bun, `litellm`, **Claude Code CLI**, `bun install`. |

Core engine **ne potrebuje** Bun-a, LiteLLM-a, Node-a ali Claude CLI-ja. To so
zahteve samo za dashboard (`./dev`).

> ⚠️ **Windows**: ukaza `./rob` in `./dev` tečeta v **Git Bash** (ali WSL) —
> PowerShell/cmd ne izvaja datotek brez končnice. V cmd/PowerShell uporabi
> `dev.bat` (dashboard) oz. `bash rob <ukaz>` za ostalo.

---

## 1. Predpogoji — orodja

Namesti (vse, razen Dockerja, so obvezne za svojo raven):

| Orodje | Namestitev | Potrebno za | Obvezno? |
|---|---|---|---|
| **Python 3.11** | `winget install Python.Python.3.11` — **ne** najnovejši 3.14 (CI testira na 3.11; 3.14 ima težave z venv in nekaterimi paketi) | vse | ✅ |
| **git** | git-scm.com | klon | ✅ |
| **Claude Code CLI** | `npm i -g @anthropic-ai/claude-code` | `./dev` | za B |
| **Node.js + npm** | nodejs.org | Bun, TS | za B |
| **Bun** | `npm i -g bun` | dashboard | za B |
| **LiteLLM** | `pip install litellm` | proxy :4010 | za B |
| **Docker Desktop** | docker.com (Windows: po namestitvi **zaženi**) | RSI peskovnik | 🚫 neobvezen |
| **Playwright** | `pip install playwright` + `playwright install chromium` | vizualni QA | 🚫 neobvezen |
| **Tailscale** | tailscale.com | remote dostop | 🚫 neobvezen |

Preveri, da so orodja na PATH:

```bash
py -3 --version     # ← NAJPOMEMBNEJŠA preverba: mora izpisati 3.11.x
python --version    # 3.11+ (glej ⚠️ spodaj — MORA biti resničen Python)
git --version
# za raven B še:
node --version
bun --version
claude --version
litellm --version   # ali: python -m pip show litellm
```

> ⚠️ **Python mora biti RESNIČEN.** `C:\Windows\python.exe` je pogosto Microsoft
> **Store-stub** (odpre trgovino, kode ne poganja). Če `py -3 --version` vrne
> *"No installed Python found"*, ali `where python` kaže samo na
> `C:\Windows\python.exe` — sistemski Python ni registriran. Takrat:
> `winget install Python.Python.3.11` in **ponovi preverbo** pred nadaljevanjem.
> (Sistem zmore tudi portabilen Python, npr. `engine\python.exe`, ampak
> sistemski je priporočen — glej korak 3.)

---

## 2. Klon repozitorija

```bash
git clone https://github.com/robAItech/rob-system.git
cd rob-system
```

> Repo je nastavljen tako, da se vse datoteke (tudi `rob` skripta) ob klonu
> shranijo z LF konci vrstic — v Git Bash delujejo brez posebnega ukvarjanja.

---

## 3. Python okolje in odvisnosti

Najenostavneje: **v sistemski Python** (priporočeno na namenskem stroju — tako
deluje tudi avtomatski zagon daemona, ker `scripts/autostart.bat` kliče
sistemski `python`):

```bash
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install litellm          # samo za ./dev (raven B)
pip install playwright       # samo za vizualni QA (neobvezno)
playwright install chromium  # neobvezno
```

> 🔁 **Želiš venv?** Možno (npr. več projektov na istem stroju). `./rob` najde
> python sam — venv (`venv` ali `engine`, v `Scripts/` na Windows ali `bin/` na
> POSIX), portabilen Python v korenu (npr. `engine\python.exe`) ali sistemski
> Python. **Ničesar ni treba ročno aktivirati.** Tudi `scripts/autostart.bat`
> (daemon ob prijavi) razreši python na isti način.

---

## 4. Konfiguracija — `.env`

```bash
cp .env.example .env
```

Nato v `.env` **obvezno** vpiši pravi DeepSeek ključ. Brez njega RSI zanka,
daemon in eval ne delujejo (placeholder se obravnava kot "ni ključa"):

```
DEEPSEEK_API_KEY=sk-...tvoj_pravi_ključ
```

Opcijsko:

```
GEMINI_API_KEY=...     # semantični spomin (embeddingi) + TTS + spletno iskanje — https://aistudio.google.com/apikey
SERPER_API_KEY=...     # pravo Google iskanje — https://serper.dev
OPENROUTER_API_KEY=... # rezerva, če DeepSeek pade (sk-or-...)
```

`DEEPSEEK_BASE_URL`, `LLM_TOOL_USE`, `LLM_HEAL_*`, `LOOPX_ROLLBACK_ON_FAIL`,
`DAEMON_*` in ostalo — poln seznam s komentarji je v `.env.example`. Privzeti
model je `deepseek-v4-flash` (preslika tudi vse Claude modele).

---

## 5. Preverba core engine-a (raven A)

```bash
./rob test                  # celotna testna matrika (369 testov) — mora biti zelena
./rob eval --dry-run        # strukturna preverba eval lestvice (brez LLM)
```

- `./rob test` poganja `pytest tests/` (repos paketi pridejo na pot prek
  `pytest.ini` — nič posebej ne nastavljaš).
- Oba ukaza **ne kličeta LLM-ja** — delujeta tudi brez ključa (čeprav je
  `DEEPSEEK_API_KEY` priporočljivo že nastavljen).

**Prvi resničen smoke test** (kliče DeepSeek, zato mora biti ključ nastavljen):

```bash
./rob build testmod "Izdelaj Python modul testmod v actions/testmod/. Funkcija add(a,b) vrne a+b. Vsebuj pytest test, vsi testi 100% zeleni."
```

Uspeh = `✅ 100% VERIFIED GREEN & SHIPPED`. Rezultat živi v `actions/testmod/`.

---

## 6. Dashboard + Claude prek DeepSeek (raven B — `./dev`)

Dashboard in proxy so **ločena raven** od core engine-a. Zanj potrebuješ:
Node, Bun, LiteLLM in **Claude Code CLI** (zgoraj, korak 1).

```bash
bun install                 # TS odvisnosti (src/)
./dev --init                # dry-run preverba: config, ključ, porta 4010/8787, PATH
./dev                       # proxy :4010 + dashboard :8787 v ozadju + poveže claude
```

- `./dev` je skripta (Linux/WSL/Git Bash). Na Windows v cmd/PowerShell:
  `dev.bat` (enako).
- Proxy konfiguracija: `bridges/litellm_config.yaml` — vse modele preslika na
  `deepseek-v4-flash` prek `api.deepseek.com/anthropic`, ključ iz
  `DEEPSEEK_API_KEY`, master ključ proxyja je `sk-hermes-master-key`.
- Dashboard: **http://localhost:8787/command** (ob prvem obisku vneseš
  `ROB_API_TOKEN` iz `.env`).
- Druge možnosti: `./dev --proxy-only`, `./dev --dashboard-only`,
  `./dev --claude-only`, `./dev --dashboard-only --watch` (hot-reload).

**Daemon (P1, 24/7 master proces):**

```bash
./rob daemon --serve        # dvigne proxy+dashboard (idempotentno), izhod
./rob daemon --status       # heartbeat, tek. naloga, jobi
./rob daemon --stop         # graceful shutdown
```

**(Windows) avtomatski zagon ob prijavi:**

```powershell
pwsh -File scripts\register-autostart.ps1        # registrira
pwsh -File scripts\register-autostart.ps1 -Query # preveri
```

**Master–worker fleet (P9 — deljena agenda čez več strojev):**

```bash
# MASTER (stroj, ki obdrži agendo + dela; v .env):
#   ROB_FLEET_ROLE=master
#   ROB_FLEET_TOKEN=<skupna skrivnost>
./rob fleet serve            # dvigne /fleet/* na :8789 (samo Tailscale/zasebno!)
./rob daemon                 # master daemon dela + služi agendo workerjem

# WORKER (drugi stroj; v .env):
#   ROB_FLEET_ROLE=worker
#   ROB_FLEET_MASTER_URL=http://<master-tailscale-ip>:8789
#   ROB_FLEET_TOKEN=<ista skrivnost>
./rob daemon                 # worker: claim → run_swarm --item → result nazaj
./rob fleet status           # pregled flote (od masterja)
```

- Worker nikoli ne piše v master agendo neposredno: nalogo dobi prek
  `/fleet/claim`, izvede skozi isto RSI pot (`run_swarm.py --item`) in pošlje
  rezultat nazaj (`/fleet/result`).
- **Lease:** če worker umre sredi naloge, master po `ROB_FLEET_CLAIM_TTL_SECONDS`
  (privzeto 1800 s) nalogo spet sprosti drugemu workerju.
- **Varnost:** `/fleet/*` zahteva `ROB_FLEET_TOKEN` (fail-closed brez tokena).
  **NIKOLI javnega porta** — Tailscale ali zasebno omrežje.
- `ROB_FLEET_ROLE=standalone` (privzeto) = današnje vedenje, nič se ne spremeni.

**Faza 4 — deljen spomin (workerji se učijo skupaj):**

- Worker **pred** vsako nalogo potegne masterjev spomin (`GET /fleet/memory` →
  lokalni merge učnih tabel: `semantic_memories`, `run_reviews`,
  `blacklist_patterns`, `agent_memory_nodes`), **po** nalogi pošlje svoje nove
  lekcije nazaj (`POST /fleet/memory`, master združi z dedupom).
- Izklop: `ROB_FLEET_SYNC_MEMORY=false` (ostane le deljena agenda).
- `./rob fleet memory` — lokalni pregled (števila po tabelah).
- **Odpornost (master ni slepa ulica):** na masterju redno poženi
  `./rob fleet backup` — izvoz spomina + agende v `fleet/backup.json`,
  commit + push v git. Katerikoli stroj: `./rob fleet restore` (git pull →
  združi backup v lokalni spomin/agendo).

---

## 7. Docker RSI peskovnik (neobvezno, a priporočeno)

Izolirana pytest verifikacija v `--network none`. Brez njega RSI pade na host
pytest (oznaka `[NI IZOLIRANO]`) — deluje, a ni izolirano.

```bash
docker build -f Dockerfile.sandbox -t rob-sandbox .
```

Windows: Docker Desktop mora biti **zagnan** (ne le nameščen).

---

## 8. Opcijske integracije

- **GStack skilli (54) kot LLM orodje**: v `~/.claude/skills/` (privzeto) ali
  `GSTACK_SKILLS_DIR=...` v `.env`. Modul `core/skill_bridge.py` je robusten —
  če mapa ne obstaja, se feature tiho izpusti, nič ne pade. Skille dobaviš z
  namestitvijo gstack paketa Claude Code (glej gstack navodila).
- **Google OAuth** (Drive/Email/Calendar): `client_secret.json` + registracija
  redirect URI `http://localhost:8787/api/google/oauth2callback` v Google Console.
- **Vizualni QA** (`--visual-qa`): Ollama + Gemma 4 (`ollama pull gemma4`).
- **Remote dostop**: Tailscale (dashboard API ni avtenticiran, CORS `*` —
  **nikoli ne odpiraj javnega porta 8787/4010** na internet).

---

## 9. Odpravljanje napak

| Simptom | Vzrok | Rešitev |
|---|---|---|
| `./rob` / `./dev`: *command not found* | v PowerShell/cmd ni izvajanja brez končnice | uporabi **Git Bash**; ali `bash rob <ukaz>`; ali `dev.bat` |
| `ModuleNotFoundError: httpx` (ali pydantic, fastapi, dotenv…) | Python paketi niso instalirani | `pip install -r requirements-dev.txt` (v aktiviranem venv-u / sistemskem Pythonu) |
| venv kreacija pade (`Unable to copy venvlauncher.exe`) / `pip install -r requirements-dev.txt` pade (npr. playwright) | Python najnovejši (3.14) | uporabi **Python 3.11** (`winget install Python.Python.3.11`); venv ni potreben — sistemski Python |
| `py -3 --version` → *"No installed Python found"* | sistemski Python ni registriran (Store-stub `C:\Windows\python.exe` ne šteje) | `winget install Python.Python.3.11`, potem ponovi `py -3 --version` → 3.11.x |
| WSL `bash rob` uporabi Linux `python3` (npr. `/usr/bin/python3` brez pytest) | `bash` je WSL, ne Git Bash — Windows venv/engine python ni bil najden | `rob` najde python sam; preveri `venv\Scripts\python.exe` ali `engine\python.exe`, ali namesti sistemski Python 3.11 (korak 1) |
| `rob: line N: : command not found` | star bug v `rob` (scoping/CRLF), popravljen | `git pull` na zadnjo verzijo (≥ `705e979`) — `rob` sam poišče venv/engine python in ima CRLF self-heal |
| `ModuleNotFoundError: gbrain` / `gstack` / `graphify` | ob zagonu izven pytest-a, če koda klice repos paket | repos paketi so samo za pytest (jih doda `pytest.ini`); core engine jih ne rabi. Teci prek `./rob test` / `pytest`. |
| Build pade / eval preskočen, `DEEPSEEK_API_KEY secret ni nastavljen` | `.env` nima pravega ključa (ali ima placeholder `sk-your-deepseek-api-key-here`) | vpiši pravi `DEEPSEEK_API_KEY=sk-...` v `.env` in preveri s `python -c "from core.config import settings; print(settings.is_real_key_available())"` → `True` |
| `./dev`: *'claude' ni na PATH* | Claude Code CLI ni instaliran | `npm i -g @anthropic-ai/claude-code`; preveri `claude --version` |
| `./dev`: *'litellm' ni na PATH* | LiteLLM ni instaliran | `pip install litellm` |
| `./dev`: *'bun' ni na PATH* | Bun ni instaliran | `npm i -g bun` |
| `./dev --init` javi zaseden port 4010/8787 | že teče druga instanca | preveri z `./rob daemon --status`; ali `./rob daemon --stop` |
| RSI teče z `[NI IZOLIRANO]` | Docker ni zagnan / slika ne obstaja | zaženi Docker Desktop; `docker build -f Dockerfile.sandbox -t rob-sandbox .` |
| Dashboard 401/404 ob prvem vnosu | manjka `ROB_API_TOKEN` v `.env` | vpiši token v `.env` in ponovno zaženi `./dev` |
| Emoji/šumniki v izpisu pokvarjeni | cp1250 konzola na Windows | Git Bash / Windows Terminal; izhod je že forsiran v UTF-8 |

**Diagnostika na enem mestu:**

```bash
./rob test               # 369 testov zelenih?
./rob eval --dry-run     # eval lestvica strukturno OK?
./dev --init             # proxy+dashboard: vse pripravljeno?
```

Če `./rob test` ali `./dev --init` še vedno javi napako, prilepi izhod — vsak
korak ima deterministično rešitev iz zgornje tabele.
