# Dashboard — pregled in predlog nadgradnje

Izdelal: Chief of Staff (interaktivno telo), prvi teden »roke« v mejah varovalke.
Vir: `src/server.ts` (2223 vrstic), `src/web/` (Command Center v2), `python -m actions.dashboard_review.pregled`.

## Kako deluje (povzetek)

```
 out/Dashboard.html (bundl iz src/web) ── fetch same-origin ──▶ src/server.ts (Bun)
                                                                     │
   /api/me (auth) · /api/metrics (KPI) · /api/fleet · /api/events (SSE)
   /api/agenda (+ mark/delete/files) · /api/artifacts|modules|agents|graph
   /api/build (async run_swarm → actions/) · /api/chat (task/research/chat)
   Google (drive/email/calendar, TTS prek curl) · gmail→agenda poll worker
                                                                     │
                       Python RSI jedro (agenda, daemon, actions/)
```

Frontend v2 je modularen: `src/web/main.ts` → komponente `fleet/feed/kpis/state/
chat/agenda/graph`, živi SSE tok, KPI polling na 15 s, 401-interceptor → login
(`ROB_API_TOKEN`). Strežnik je most na SQLite ledger (`.gstack-run.sqlite`) in na
agendo/artefakte/agente; izvedbo nalog prevzame P1 daemon (agenda → `run_swarm`).

## Najdeno (resnično, s potmi)

1. **`uptimePct: 99.98` je trdo kodiran** (`src/server.ts:283`) — prikazan kot
   KPI, a ni merjen. Lažen podatek na dashboardu.
2. **Rate-limit `RATE` raste brez čiščenja** (`src/server.ts:79-85`) — vnos per
   IP se nikoli ne odstrani → počasen pomnilniški leak ob daljšem teku.
3. **Monoliten strežnik**: ~38+ API poti v enem `server.ts` — težko enotno
   testirati; veliko poti frontend še ne uporablja (API-first rezerva).
4. **`/api/health` kliče LLM `/models`** (`server.ts:271`) ob vsakem KPI ticku
   — kadar ponudnik ni dosegljiv, je `llmOnline` napačno `false`/počasen.

## Predlog nadgradnje (glavni): »Chief« panel

Ker chief od danes generira dnevno poročilo (`.rob_ai/chief/latest.md`, lekcije,
zgodovina), dashboard dobi **Chief panel** — tako chief poroča šefu tam, kjer
šef že gleda:

1. **Prikaži dnevni digest** — bere novi `GET /api/chief` (vrne `latest.md` +
   `lessons` + `history`); prikaz: *zgodilo se je / posli / predlog za jutri /
   od tebe rabim / naučeno*.
2. **Vnosno polje za popravek** — `POST /api/chief/correct {text}` →
   `chief.append_correction` → lekcija; tako gre učenje skozi UI.
3. **Števec lekcij + 7-dnevna zgodovina** — iz `chief --week` (meritev prvega tedna).

**Izvedba = faza 2:** dodati 2 endpointa v `src/server.ts`, komponento
`src/web/components/chief.ts` + priklop v `main.ts`/panel. To je izven
first-week guarda (`src/` ni v dovoljenih conah) — pripravljeno, ko odpremo
`src/` ali izvedemo ročno. Test: TS komponenta (izven Python test suite).

## Manjši popravki (ob naslednjem dotiku dashboarda)

- `uptimePct`: meri realno (uptime procesa / št. restartov) ali odstrani KPI.
- `RATE`: občasno počisti stare vnose (ali TTL).
- Razmisli o razdelitvi `server.ts` na module (routes/), ko bo rasel.

## Zakaj to zdaj

Zapre učni krog chief-a v uporabniški vmesnik: *chief poroča → šef popravi →
lekcija → naslednje poročilo*. In dashboard dobi tisto, kar mu manjka pri
»avtonomno vodenem sistemu«: glas tistega, ki ga vodi.
