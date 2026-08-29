/**
 * src/server.ts — Live Hermes Command Center.
 *
 * Dashboard (`out/Dashboard.html`) je statična front-end UI. Brskalnik prek
 * `file://` ne more brati SQLite baze, zato ta strežnik deluje kot most med
 * dashboardom in dejanskim ledgerjem (.gstack-run.sqlite):
 *
 *   GET  /            → servira out/Dashboard.html
 *   GET  /api/health  → { llmOnline, events, runs, budgetMicros } (KPI)
 *   GET  /api/ledger  → zadnji dogodki (razčlenjeni payload)
 *   GET  /api/runs    → statistika tekov (status, spend)
 *   POST /api/run     → izvede novo nalogo v Hermes runner in vrne rezultat
 *
 * Dashboard dohaja podatke prek fetch na isti origin (same-origin).
 * CORS je dodan za varno mrežo, če bi dashboard odprli z drugega mesta.
 *
 * Zagon:  bun run src/server.ts    (privzeto http://localhost:8787)
 */

import { planner } from './agents/planner.ts';
import { builder } from './agents/builder.ts';
import { qa } from './agents/qa.ts';
import { screenshot } from './agents/screenshot.ts';
import { Ledger } from './hermes/ledger.ts';
import { Runner, type FsLike } from './hermes/runner.ts';
import type { Agent, MemoryStore } from './hermes/types.ts';
import { OpenAICompatibleProvider } from './bridges/openai-compatible.ts';
import { LLMCache } from './bridges/cache.ts';
import { resolveProvider } from './bridges/provider.ts';
import { SqliteMemoryStore } from './memory/sqlite-store.ts';
import { BunExec } from './bridges/exec.ts';
import { mkdirSync, writeFileSync, unlinkSync } from 'node:fs';

// Pretvorba in prikaz artefaktov (Word / PDF / Markdown-ogled)
import {
  Document as DocxDocument, Packer, Paragraph, TextRun, HeadingLevel,
  AlignmentType, convertInchesToTwip,
} from 'docx';
import { PDFDocument, StandardFonts, rgb } from 'pdf-lib';
import { marked } from 'marked';
import ExcelJS from 'exceljs';

const DB_PATH = process.env.LEDGER_DB ?? '.gstack-run.sqlite';
const PORT = Number(process.env.PORT ?? 8787);
const OUT_ROOT = process.env.OUT_ROOT ?? '.';

// =====================================================================
//  Zaščita API-ja — ROB_API_TOKEN (env). Če je nastavljen, vsi /api/*
//  (razen /api/auth in /api/health) zahtevajo veljavno session piškotko.
//  Brez tokena → dashboard dela brez zaščite (lokalni dev, nazaj-kompatibilno).
// =====================================================================
const API_TOKEN = process.env.ROB_API_TOKEN || '';
const SESSIONS = new Set<string>();

function authCookie(req: Request): string {
  try {
    const c = req.headers.get('cookie') || '';
    for (const part of c.split(';')) {
      const [k, ...v] = part.trim().split('=');
      if (k === 'rob_session') return v.join('=');
    }
  } catch { /* */ }
  return '';
}
function isAuthed(req: Request): boolean {
  if (!API_TOKEN) return true;                      // zaščita ni konfigurirana
  return SESSIONS.has(authCookie(req));
}
function unauthorized(): Response {
  return json({ ok: false, error: 'unauthorized' }, 401);
}

// ── Rate limit (zaščita stroškov LLM): 10 LLM klicev/min na IP ──
const RATE_MAX = 10;
const RATE_WINDOW_MS = 60_000;
const RATE: Record<string, number[]> = {};
function rateLimited(ip: string): boolean {
  const now = Date.now();
  const arr = (RATE[ip] || []).filter((t) => now - t < RATE_WINDOW_MS);
  if (arr.length >= RATE_MAX) { RATE[ip] = arr; return true; }
  arr.push(now); RATE[ip] = arr; return false;
}

// =====================================================================
//  Google OAuth + API (Drive / Gmail / Calendar)
// =====================================================================
const GOOGLE_SECRET_FILE = `${OUT_ROOT}/client_secret.json`;
const GOOGLE_TOKEN_FILE = `${OUT_ROOT}/.gtoken.json`;
// Redirect URI mora biti registriran v Google Console. Server je HTTP po defaultu
// (Google ima http registriran) → privzeto http. Za HTTPS/DASH_HTTPS=1 nastavi
// GOOGLE_REDIRECT=https://localhost:<PORT>/api/google/oauth2callback.
const G_REDIRECT = process.env.GOOGLE_REDIRECT || `http://localhost:${PORT}/api/google/oauth2callback`;
const G_SCOPES = ['https://www.googleapis.com/auth/drive.readonly',
  'https://www.googleapis.com/auth/gmail.readonly',
  'https://www.googleapis.com/auth/calendar.readonly'];

/** Prebere OAuth kredentials iz client_secret.json. */
async function googleCreds(): Promise<{ client_id: string; client_secret: string } | null> {
  try {
    const f = Bun.file(GOOGLE_SECRET_FILE);
    if (!(await f.exists())) return null;
    const j = JSON.parse(await f.text());
    const w = j.web || {};
    if (!w.client_id || !w.client_secret) return null;
    return { client_id: w.client_id, client_secret: w.client_secret };
  } catch { return null; }
}

/** Prebere shranjeni access/refresh token (če obstaja). */
async function googleToken(): Promise<{ access_token: string; refresh_token?: string; expires_at?: number } | null> {
  try {
    const f = Bun.file(GOOGLE_TOKEN_FILE);
    if (!(await f.exists())) return null;
    return JSON.parse(await f.text());
  } catch { return null; }
}
async function saveGoogleToken(t: unknown): Promise<void> {
  await Bun.write(GOOGLE_TOKEN_FILE, JSON.stringify(t));
}

/** Aquire access token, po potrebi osveži z refresh tokenom. */
async function googleAccessToken(): Promise<string | null> {
  const t = await googleToken();
  if (!t) return null;
  if (t.expires_at && t.expires_at > Date.now()) return t.access_token;   // še veljaven
  if (!t.refresh_token) return null;
  const c = await googleCreds();
  if (!c) return null;
  try {
    const r = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `client_id=${encodeURIComponent(c.client_id)}&client_secret=${encodeURIComponent(c.client_secret)}&refresh_token=${encodeURIComponent(t.refresh_token)}&grant_type=refresh_token`,
    });
    const j = await r.json() as { access_token?: string; expires_in?: number };
    if (!j.access_token) return null;
    await saveGoogleToken({ ...t, access_token: j.access_token, expires_at: Date.now() + (j.expires_in ?? 3600) * 1000 });
    return j.access_token;
  } catch { return null; }
}

/** Sestavi avtorizacijski URL za Google OAuth. */
async function googleAuthUrl(scopes: string[]): Promise<string | null> {
  const c = await googleCreds();
  if (!c) return null;
  const params = new URLSearchParams({
    client_id: c.client_id,
    redirect_uri: G_REDIRECT,
    response_type: 'code',
    access_type: 'offline',
    prompt: 'consent',
    scope: scopes.join(' '),
  });
  return 'https://accounts.google.com/o/oauth2/v2/auth?' + params.toString();
}

/** Izmenja authorization code → tokens. */
async function googleExchangeCode(code: string): Promise<boolean> {
  const c = await googleCreds();
  if (!c) return false;
  try {
    const r = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `code=${encodeURIComponent(code)}&client_id=${encodeURIComponent(c.client_id)}&client_secret=${encodeURIComponent(c.client_secret)}&redirect_uri=${encodeURIComponent(G_REDIRECT)}&grant_type=authorization_code`,
    });
    const j = await r.json() as { access_token?: string; refresh_token?: string; expires_in?: number; error?: string; error_description?: string };
    if (!j.access_token) {
      console.error('[google] izmenjava kode NAPAKA:', JSON.stringify({ error: j.error, description: j.error_description, redirect: G_REDIRECT }));
      return false;
    }
    await saveGoogleToken({ access_token: j.access_token, refresh_token: j.refresh_token ?? null, expires_at: Date.now() + (j.expires_in ?? 3600) * 1000 });
    return true;
  } catch (e) { console.error('[google] izmenjava kode izjema:', e); return false; }
}

/** Splošni GET proti Google API s tokenom. */
async function googleGet(path: string): Promise<unknown | null> {
  const at = await googleAccessToken();
  if (!at) return null;
  try {
    const r = await fetch('https://www.googleapis.com' + path, { headers: { Authorization: 'Bearer ' + at } });
    return r.ok ? (await r.json()) : null;
  } catch { return null; }
}

/** Resnični disk. */
class Disk implements FsLike {
  constructor(private readonly root: string) {}
  async write(path: string, content: string): Promise<Uint8Array> {
    const abs = `${this.root}/${path}`;
    await Bun.write(abs, content, { createPath: true });
    const buf = await Bun.file(abs).arrayBuffer();
    return new Uint8Array(buf);
  }
  async read(path: string): Promise<Uint8Array> {
    const buf = await Bun.file(`${this.root}/${path}`).arrayBuffer();
    return new Uint8Array(buf);
  }
}

/** Vrne agente glede na nabor. */
function agentsFor(kind: 'full' | 'dashboard'): Agent[] {
  return kind === 'dashboard' ? [planner, builder, qa] : [planner, builder, qa, screenshot];
}

// =====================================================================
//  Podatki iz baze (vse read-only)
// =====================================================================

function withLedger<T>(fn: (l: Ledger) => T): T {
  const l = new Ledger(DB_PATH);
  try { return fn(l); } finally { l.close(); }
}

/** Vse dogodke vseh zadnjih tekov, razčlenjene, urejene po runSeq. */
function readEvents(limit = 500): Record<string, unknown>[] {
  return withLedger((l) => {
    const runIds = l.db
      .query('SELECT run_id FROM runs ORDER BY created_at DESC')
      .all()
      .map((r) => (r as { run_id: string }).run_id);
    const out: Record<string, unknown>[] = [];
    for (const rid of runIds) {
      for (const e of l.read(rid)) {
        out.push({
          runId: rid, runSeq: e.runSeq, kind: e.kind, actor: e.actor,
          causedByRunSeq: e.causedByRunSeq, ts: e.ts, payload: e.payload,
        });
      }
    }
    return out.slice(0, limit);
  });
}

/** Statistika tekov od vseh tekov (status + poraba). */
function readRuns(): Record<string, unknown>[] {
  return withLedger((l) =>
    l.db
      .query('SELECT run_id, status, steps_used, spend_micros, forked_from FROM runs ORDER BY created_at DESC LIMIT 200')
      .all()
      .map((r) => {
        const x = r as Record<string, unknown>;
        return {
          id: x.run_id, status: x.status, steps: x.steps_used,
          spendMicros: x.spend_micros, forkedFrom: x.forked_from,
        };
      }),
  );
}

function countEvents(): number {
  return withLedger((l) => (l.db.query('SELECT count(*) c FROM events').get() as { c: number }).c);
}

/** Zdravje / KPI. Preveri tudi, ali je LLM most (Ollama privzeto) dosegljiv. */
async function health(): Promise<Record<string, unknown>> {
  const runs = readRuns();
  let llmOnline = false;
  let provider = '—';
  try {
    const p = resolveProvider(process.env);
    provider = p.name;
    // Health preverba mora iti do /models z identiteto, ki jo uporabljamo za
    // prave klike. Ponudniki na ključ (deepseek, openai) vmejo 401 brez
    // `Authorization`, pa čeprav je ključ veljaven — zato ga dodamo kadar je
    // zahtevan. Ollama ključa ne potrebuje, header pa ji ne škodi.
    const headers: Record<string, string> = {};
    if (p.apiKey) headers.Authorization = `Bearer ${p.apiKey}`;
    const r = await fetch(`${p.baseUrl}/models`, {
      headers,
      signal: AbortSignal.timeout(2500),
    });
    llmOnline = r.ok;
  } catch { /* offline */ }
  return {
    llmOnline,
    provider,
    eventCount: countEvents(),
    runCount: runs.length,
    budgetMicros: runs.reduce((s, r) => s + (r.spendMicros as number), 0),
    uptimePct: 99.98,
  };
}

/** Live tehnične novice (poberemo iz interneta). Vrne največ ~5 naslovov. */
async function getNews(): Promise<{ title: string; source: string }[]> {
  const fallback: { title: string; source: string }[] = [
    { title: 'AI agenti prevzemajo avtomatizacijo razvojnih tokov', source: 'tech' },
    { title: 'Novi modeli pospešujejo generativno kodiranje', source: 'tech' },
  ];
  // Google News RSS s tehnično iskalno poizvedbo — odprt vir, brez ključa.
  const url =
    'https://news.google.com/rss/search?q=technology+AI&hl=en-US&gl=US&ceid=US:en';
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
    if (!res.ok) return fallback;
    const xml = await res.text();
    const items = [...xml.matchAll(/<item>([\s\S]*?)<\/item>/g)].slice(0, 5);
    const out: { title: string; source: string }[] = [];
    for (const [, block] of items) {
      const t = block.match(/<title>(.*?)<\/title>/)?.[1] ?? '';
      if (!t) continue;
      const s = block.match(/<source[^>]*>(.*?)<\/source>/)?.[1] ?? 'tech';
      out.push({ title: t.replace(/<!\[CDATA\[|\]\]>/g, '').trim(), source: s.trim() });
    }
    return out.length ? out : fallback;
  } catch {
    return fallback;  // offline → rezervni statični naslovi
  }
}

// =====================================================================
//  Produkcirani moduli → seznam + ogled + prenos (Word/PDF/Markdown)
// =====================================================================

/** Prevede relativno arhivsko pot v absolutno, varno znotraj korena. */
function resolveArtefact(rel: string): string {
  const safe = rel.replace(/^\/+/, '').replace(/\.\./g, '');
  return `${OUT_ROOT}/${safe}`;
}

/** Seznam datotek iz `out/` (le prepoznane oblike izdelkov). */
async function listModules(): Promise<Record<string, unknown>[]> {
  const dir = `${OUT_ROOT}/out`;
  const out: Record<string, unknown>[] = [];
  try {
    const glob = new Bun.Glob('*.{md,html,htm,py,json,css,js,pdf,txt,csv}');
    for await (const entry of glob.scan({ cwd: dir, onlyFiles: true })) {
      if (entry.toLowerCase() === 'dashboard.html') continue;
      const abs = `${dir}/${entry}`;
      const f = Bun.file(abs);
      const sizeBytes = (await f.exists()) ? f.size : 0;
      out.push({
        name: entry, path: `out/${entry}`,
        ext: (entry.split('.').pop() || '').toLowerCase(),
        sizeBytes,
      });
    }
  } catch { /* out/ morda ne obstaja */ }
  return out.sort((a, b) => String(b.name).localeCompare(String(a.name)));
}

/** "Popravi to" — seznam RSI modulov (actions/<name>/), ki jih uporabnik lahko uredi. */
async function listEditable(): Promise<Record<string, unknown>[]> {
  const base = `${OUT_ROOT}/actions`;
  const out: Record<string, unknown>[] = [];
  try {
    const glob = new Bun.Glob('*/');
    for await (const dir of glob.scan({ cwd: base, onlyFiles: false })) {
      const name = dir.replace(/\/$/, '');
      if (!name || name.startsWith('.')) continue;
      if (name === '__pycache__' || name === '.pytest_cache') continue;   // ne modul
      // Glavni artefakt: .py/.html/.md/.pyc iz actions/<name>/ (preskoči test_).
      let type = 'python';
      let artefact = '';
      const fglob = new Bun.Glob('*.{py,html,htm,md}');
      for await (const f of fglob.scan({ cwd: `${base}/${name}`, onlyFiles: true })) {
        if (f.startsWith('test_')) continue;
        if (artefact === '' && f !== '__init__.py') artefact = f;
        if (f.endsWith('.html') || f.endsWith('.htm')) type = 'html';
        else if (type === 'python' && (f.endsWith('.md'))) type = 'markdown';
      }
      out.push({ name, type, artefact: artefact || type });
    }
  } catch { /* actions/ morda ne obstaja */ }
  return out.sort((a, b) => String(a.name).localeCompare(String(b.name)));
}

/** Sistemske metrike iz GBRAIN (memory.db) + GRAPHIFY (graph.json) + actions/. */
async function systemMetrics(): Promise<Record<string, unknown>> {
  const script = `
import sqlite3, json, os
from pathlib import Path
root = os.environ.get('OUT_ROOT') or '.'
db = Path(root) / '.rob_ai' / 'memory.db'
tasks = errors = 0
if db.exists():
    try:
        conn = sqlite3.connect(db)
        tasks = conn.execute('SELECT COUNT(*) FROM task_history').fetchone()[0]
        errors = conn.execute('SELECT COUNT(*) FROM blacklist_patterns').fetchone()[0]
        conn.close()
    except Exception: pass
graph = Path(root) / '.rob_ai' / 'graph.json'
nodes = 0
if graph.exists():
    try: nodes = len(json.loads(graph.read_text(encoding='utf-8')).get('nodes', {}))
    except Exception: pass
mods = []
actions = Path(root) / 'actions'
if actions.exists():
    mods = sorted(d.name for d in actions.iterdir() if d.is_dir() and not d.name.startswith('.') and not d.name.startswith('__'))
print(json.dumps({'tasks': tasks, 'errors': errors, 'nodes': nodes, 'modules': len(mods), 'module_names': mods}))
`;
  try {
    const proc = Bun.spawn({
      cmd: ['python', '-c', script],
      cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
    const out = await new Response(proc.stdout).text();
    await proc.exited;
    return JSON.parse(out.trim() || '{}');
  } catch {
    return { tasks: 0, errors: 0, nodes: 0, modules: 0, module_names: [] };
  }
}

/** Opisi agentov/bridge-ov (prikažejo se na dashboardu). */
const AGENT_DESCS: Record<string, { group: string; desc: string }> = {
  planner:    { group: 'agent',  desc: 'Orkestrator: zapiše odločitev, workplan, @file bloke.' },
  builder:    { group: 'agent',  desc: 'Razreže @file na poti, piše na disk, sproži qa.verify.' },
  qa:         { group: 'agent',  desc: 'Poganja cmd.exec verify; retry do maxFixPasses.' },
  screenshot: { group: 'agent',  desc: 'Ob spletnem artefaktu zabeleži namero posnetka.' },
  architect:  { group: 'agent',  desc: 'Arhetip mejnika: odločitev + en LLM odgovor.' },
  engineer:   { group: 'agent',  desc: 'Zadnji LLM odgovor zapiše na disk, zaključi tek.' },
  gbrain:   { group: 'bridge', desc: 'Trajni spomin SQLite — uči se iz napak.' },
  graphify: { group: 'bridge', desc: 'AST sken → graph.json + kontekst.' },
  gstack:   { group: 'bridge', desc: 'Arhitekturna spec → manifest + spec_hint.' },
  hermes:   { group: 'bridge', desc: 'Ustvari ogrodje actions/<mod>/.' },
  loopx:    { group: 'bridge', desc: 'Verifikacija + samozdravljenje do 100% zelen.' },
};

/** Agenti (src/agents/*.ts) + bridge-i (core/*_bridge.py) — iz datotečnega sistema. */
async function listAgents(): Promise<Record<string, unknown>[]> {
  const out: Record<string, unknown>[] = [];
  try {
    const glob = new Bun.Glob('*.ts');
    for await (const f of glob.scan({ cwd: `${OUT_ROOT}/src/agents`, onlyFiles: true })) {
      const name = f.replace(/\.ts$/, '');
      const d = AGENT_DESCS[name] || { group: 'agent', desc: '' };
      out.push({ id: name, role: name, label: name, file: `${name}.ts`, group: d.group, desc: d.desc });
    }
  } catch { /* src/agents morda ne obstaja */ }
  try {
    const glob = new Bun.Glob('*_bridge.py');
    for await (const f of glob.scan({ cwd: `${OUT_ROOT}/core`, onlyFiles: true })) {
      const name = f.replace(/_bridge\.py$/, '');
      const d = AGENT_DESCS[name] || { group: 'bridge', desc: '' };
      out.push({ id: name, role: name.toUpperCase(), label: name.toUpperCase(), file: f, group: d.group, desc: d.desc });
    }
  } catch { /* core morda ne obstaja */ }
  return out;
}

/** Povezave med agenti (TS) in bridge-i (core/) — action moduli imajo realne robove iz core/actions_graph.py. */
const AGENT_EDGES: [string, string][] = [
  ['planner','builder'],['builder','qa'],['qa','screenshot'],['qa','loopx'],
  ['gbrain','graphify'],['graphify','gstack'],['gstack','hermes'],['hermes','loopx'],
  ['planner','gbrain'],
];

/** Realni robovi action modulov (core/actions_graph.py) — TTL 30 s. */
let actionEdgesCache: { ts: number; edges: [string, string][] } | null = null;
async function actionEdges(): Promise<[string, string][]> {
  const now = Date.now();
  if (actionEdgesCache && now - actionEdgesCache.ts < 30_000) return actionEdgesCache.edges;
  const script = `
import sys, os, json
sys.path.insert(0, os.environ.get('OUT_ROOT') or '.')
from core.actions_graph import all_edges
print(json.dumps(all_edges(), ensure_ascii=False))
`;
  try {
    const proc = Bun.spawn({
      cmd: ['python', '-c', script],
      cwd: OUT_ROOT,
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
    const out = await new Response(proc.stdout).text();
    await proc.exited;
    const edges = (JSON.parse(out.trim() || '[]') as { source: string; target: string }[])
      .map((e) => [e.source, e.target] as [string, string]);
    actionEdgesCache = { ts: now, edges };
    return edges;
  } catch {
    actionEdgesCache = { ts: now, edges: [] };
    return [];
  }
}

/** Sistemski graf: moduli (actions/) + agenti (src/agents/) + bridge-i (core/). */
async function systemGraph(): Promise<Record<string, unknown>> {
  const modules = await listEditable();
  const agents = await listAgents();
  const nodes = [
    ...modules.map((m) => ({ id: m.name, label: m.name, group: 'm' })),
    ...agents.map((a) => ({ id: a.id, label: a.label, group: a.group === 'bridge' ? 'b' : 'a' })),
  ];
  const edges = [...(await actionEdges()), ...AGENT_EDGES];
  return { nodes, edges };
}

/** Združen seznam artefaktov: moduli (actions/) + izdelki (out/), vsak s potjo za prenos. */
async function listArtifacts(): Promise<Record<string, unknown>[]> {
  const editable = await listEditable();
  const mods = await listModules();
  const actions = editable.map((m) => ({
    name: m.name, kind: 'modul', type: m.type,
    path: `actions/${m.name}/${m.artefact || m.type}`,
  }));
  const outs = mods.map((m) => ({ name: m.name, kind: 'izdelek', type: m.ext, path: m.path }));
  return [...actions, ...outs];
}

/** Trenutni datum/čas v slovenščini (živo, lokalni čas strežnika). */
function nowContext(): string {
  const d = new Date();
  const days = ['nedelja', 'ponedeljek', 'torek', 'sreda', 'četrtek', 'petek', 'sobota'];
  const months = ['januar', 'februar', 'marec', 'april', 'maj', 'junij', 'julij', 'avgust', 'september', 'oktober', 'november', 'december'];
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${days[d.getDay()]}, ${d.getDate()}. ${months[d.getMonth()]} ${d.getFullYear()} ob ${hh}:${mm}`;
}

/** WMO vremenski kod → slovenski opis. */
function weatherCode(n: number): string {
  if (n === 0) return 'jasno';
  if (n <= 2) return 'delno oblačno';
  if (n === 3) return 'oblačno';
  if (n <= 48) return 'megla';
  if (n <= 57) return 'rosenje';
  if (n <= 67) return 'dež';
  if (n <= 77) return 'sneg';
  if (n <= 82) return 'plohe';
  if (n <= 86) return 'snežne plohe';
  if (n <= 95) return 'nevihta';
  return 'močna nevihta';
}

/** Živo vreme iz Open-Meteo (brez API ključa). */
async function weatherFor(lat: number, lon: number): Promise<string | null> {
  try {
    const url = `https://api.open-meteo.com/v1/forecast?latitude=${lat}&longitude=${lon}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&hourly=temperature_2m,precipitation_probability,weather_code&forecast_days=2&timezone=Europe%2FLjubljana`;
    const r = await fetch(url, { signal: AbortSignal.timeout(6000) });
    if (!r.ok) return null;
    const j = await r.json() as Record<string, any>;
    const c = j.current ?? {};
    let s = `Trenutno ${Math.round(c.temperature_2m ?? 0)}°C, ${weatherCode(c.weather_code ?? 0)}, veter ${Math.round(c.wind_speed_10m ?? 0)} km/h, vlaga ${c.relative_humidity_2m}%.`;
    const t = (j.hourly?.time ?? []) as string[];
    const tmp = (j.hourly?.temperature_2m ?? []) as number[];
    const prec = (j.hourly?.precipitation_probability ?? []) as number[];
    const codes = (j.hourly?.weather_code ?? []) as number[];
    s += ' Napoved po 3h:';
    for (let i = 0; i < t.length && i < 27; i += 3) {
      s += ` ${t[i].slice(11, 16)} ${Math.round(tmp[i] ?? 0)}°C/${prec[i] ?? 0}% ${weatherCode(codes[i] ?? 0)};`;
    }
    return s;
  } catch { return null; }
}

/** Razpozna mesto iz sporočila (privzeto Vrhnika). */
function cityCoords(msg: string): { lat: number; lon: number; label: string } {
  const m = msg.toLowerCase();
  const cities: Record<string, [number, number]> = {
    'ljubljan': [46.056, 14.506], 'maribor': [46.555, 15.646], 'kranj': [46.239, 14.356],
    'celje': [46.231, 15.260], 'koper': [45.548, 13.730], 'novo mesto': [45.804, 15.169],
    'postojn': [45.774, 14.215], 'logatec': [45.918, 14.229], 'idrij': [46.002, 14.027],
  };
  for (const [k, c] of Object.entries(cities)) {
    if (m.includes(k)) return { lat: c[0], lon: c[1], label: k };
  }
  return { lat: 45.967, lon: 14.296, label: 'Vrhnika' };
}

/** Google Gemini TTS → base64 avdio. Poskusi pro model, nato flash fallback. */
async function geminiTts(text: string, voice: string): Promise<{ mime: string; base64: string } | null> {
  const key = process.env.GEMINI_API_KEY;
  if (!key) return null;
  const models = ['gemini-2.5-pro-preview-tts', 'gemini-3.1-flash-tts-preview'];
  for (const model of models) {
    try {
      const body = {
        contents: [{ parts: [{ text }] }],
        generationConfig: {
          responseModalities: ['AUDIO'],
          speechConfig: { voiceConfig: { prebuiltVoiceConfig: { voiceName: voice } } },
        },
      };
      const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(30000),
      });
      if (!r.ok) continue;
      const j = await r.json() as Record<string, any>;
      const part = (j.candidates?.[0]?.content?.parts ?? []).find((p: any) => p?.inlineData?.data);
      if (!part?.inlineData?.data) continue;
      return { mime: part.inlineData.mimeType || 'audio/wav', base64: part.inlineData.data };
    } catch { /* poskusi naslednji model */ }
  }
  return null;
}

/** Iskanje po Wikipediji (brezplačno, brez ključa) — fallback. */
async function wikiSearch(query: string): Promise<{ title: string; url: string; snippet: string }[]> {
  try {
    const url = `https://sl.wikipedia.org/w/api.php?action=query&list=search&srsearch=${encodeURIComponent(query)}&format=json&srlimit=8&srprop=snippet`;
    const r = await fetch(url, { signal: AbortSignal.timeout(7000) });
    if (!r.ok) return [];
    const j = await r.json() as Record<string, any>;
    const hits = j.query?.search ?? [];
    return (hits as any[]).map((h: any) => ({
      title: h.title,
      url: `https://sl.wikipedia.org/wiki/${encodeURIComponent(String(h.title).replace(/ /g, '_'))}`,
      snippet: String(h.snippet || '').replace(/<[^>]+>/g, '').slice(0, 200),
    }));
  } catch { return []; }
}

/** Pravo Google iskanje prek Serper.dev (potrebuje SERPER_API_KEY). */
async function serperSearch(query: string): Promise<{ title: string; url: string; snippet: string }[]> {
  const key = process.env.SERPER_API_KEY;
  if (!key) return [];
  try {
    const r = await fetch('https://google.serper.dev/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-API-KEY': key },
      body: JSON.stringify({ q: query, gl: 'si', hl: 'sl', num: 8 }),
      signal: AbortSignal.timeout(10000),
    });
    if (!r.ok) return [];
    const j = await r.json() as Record<string, any>;
    return ((j.organic ?? []) as any[]).slice(0, 8).map((o: any) => ({
      title: o.title || '',
      url: o.link || '',
      snippet: (o.snippet || '').slice(0, 220),
    }));
  } catch { return []; }
}

/** Spletno iskanje: Serper (Google) → Gemini grounding → Wikipedia. */
async function webSearch(query: string): Promise<{ title: string; url: string; snippet: string }[]> {
  const serper = await serperSearch(query);
  if (serper.length) return serper;
  const key = process.env.GEMINI_API_KEY;
  if (key) {
    try {
      const r = await fetch('https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'x-goog-api-key': key },
        body: JSON.stringify({ contents: [{ parts: [{ text: query }] }], tools: [{ googleSearch: {} }] }),
        signal: AbortSignal.timeout(15000),
      });
      if (r.ok) {
        const j = await r.json() as Record<string, any>;
        const meta = j.candidates?.[0]?.groundingMetadata;
        if (meta) {
          const chunks = (meta.groundingChunks ?? []) as any[];
          const supports = (meta.groundingSupports ?? []) as any[];
          const out = chunks.slice(0, 8).map((c, i) => {
            const sup = supports.find((s: any) => (s.groundingChunkIndices || []).includes(i));
            return { title: c.web?.title || '', url: c.web?.uri || '', snippet: (sup?.segment?.text || '').slice(0, 220) };
          }).filter((x) => x.title || x.snippet);
          if (out.length) return out;
        }
      }
    } catch { /* fallback na Wikipedijo */ }
  }
  return wikiSearch(query);
}

/** Odstrani diakritike (š→s, č→c, ž→z), da se regex ujema ne glede na encoding. */
function normalize(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '');
}

/** Ali je sporočilo NALOGA (izvedi), RAZISKAVA (globinsko preglej) ali POGOVOR. */
function classifyMessage(message: string): 'task' | 'research' | 'chat' {
  const m = normalize(message.toLowerCase());
  if (/(naloga|poslusaj|zelim da|zelim,|naredi|zgradi|ustvari|izvedi|deploy|build|zazeni|zapisi|pripravi|generiraj|ukaz|izdelaj)/.test(m)) return 'task';
  if (/(preglej|analiziraj|razisci|raziskuj|poglej|preveri|razlozi|primerjaj|oceni|preuci|sintetiziraj)/.test(m)) return 'research';
  return 'chat';
}

/** Zabeleži nalogo v agendo. Izvedbo prevzame P1 daemon (core/daemon.py). */
async function handleTask(message: string, kindOverride?: string): Promise<string> {
  const KINDS = ['python', 'markdown', 'html', 'autonomous', 'modify', 'team', 'fork', 'plan', 'fix_loop'];
  const kind = (kindOverride && KINDS.includes(kindOverride)) ? kindOverride : detectKind(message);
  try {
    const proc = Bun.spawn({
      cmd: ['python', '-c', `from core.agenda import add; import json; print(json.dumps(add(${JSON.stringify(message)}, kind=${JSON.stringify(kind)}, source='voice')))`],
      cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
    const out = await new Response(proc.stdout).text();
    await proc.exited;
    let item: Record<string, unknown> = {};
    try { item = JSON.parse(out.trim() || '{}'); } catch { /* */ }
    const target = String(item.target || '');
    // Izvedba ni tukaj — P1 daemon (core/daemon.py) je edini drainer agende.
    return `Naloga zabeležena (target: ${target || 'v pripravi'}, tip: ${kind}). Daemon jo bo obdelal. Spremljaj napredek v pogledu Agenda.`;
  } catch (e) {
    return `Naloga ni zabeležena: ${String(e instanceof Error ? e.message : e)}`;
  }
}

/** Odstrani HTML oznake in vrne čist tekst. */
function stripHtml(html: string): string {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style[\s\S]*?<\/style>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/** Prebere spletno stran in vrne izluščen tekst (best-effort). */
async function fetchPage(url: string): Promise<string> {
  try {
    const r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)' }, signal: AbortSignal.timeout(8000) });
    if (!r.ok) return '';
    const ct = r.headers.get('content-type') || '';
    if (!/(text|json|xml|javascript)/i.test(ct)) return '';
    return stripHtml(await r.text()).slice(0, 3500);
  } catch { return ''; }
}

/** Pretvori tekst v URL-varen slug (brez šumnikov). */
function slugify(text: string): string {
  return text.toLowerCase()
    .replace(/č/g, 'c').replace(/š/g, 's').replace(/ž/g, 'z')
    .replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '').slice(0, 48) || 'raziskava';
}

/** Shrani raziskovalno poročilo (s citati) v arhiv. Vrne relativno pot. */
async function saveResearch(query: string, report: string, sources: { title: string; url: string; snippet: string }[]): Promise<string> {
  const dir = `${OUT_ROOT}/.rob_ai/research`;
  const stamp = new Date().toISOString().slice(0, 16).replace(/[T:]/g, '-');
  const name = `${stamp}_${slugify(query)}.md`;
  const md = `# ${query}\n\n_Datum: ${new Date().toLocaleString('sl-SI')}_\n\n${report}\n\n---\n\n## Viri\n\n${sources.map((s, i) => `${i + 1}. [${s.title}](${s.url})`).join('\n')}\n`;
  mkdirSync(dir, { recursive: true });
  writeFileSync(`${dir}/${name}`, md, 'utf-8');
  return `.rob_ai/research/${name}`;
}

/** Seznam arhiviranih raziskav. */
async function listResearch(): Promise<Record<string, unknown>[]> {
  const dir = `${OUT_ROOT}/.rob_ai/research`;
  const out: Record<string, unknown>[] = [];
  try {
    const glob = new Bun.Glob('*.md');
    for await (const f of glob.scan({ cwd: dir, onlyFiles: true })) {
      const txt = await Bun.file(`${dir}/${f}`).text().catch(() => '');
      const title = (txt.match(/^# (.+)$/m)?.[1] || f.replace(/\.md$/, '')).slice(0, 90);
      out.push({ name: f, path: `.rob_ai/research/${f}`, title, sizeBytes: txt.length });
    }
  } catch { /* arhiv morda še ne obstaja */ }
  return out.sort((a, b) => String(b.name).localeCompare(String(a.name)));
}

/** Raziskovalni način: spletno iskanje + branje virov + sintetizirano poročilo s citati. */
async function handleResearch(message: string): Promise<string> {
  const query = message.replace(/(preglej|analiziraj|razišči|raziskuj|poglej|preveri|razloži|primerjaj|oceni|preuči|sintetiziraj)/gi, '').trim() || message;
  const results = await webSearch(query);
  if (!results.length) return 'Nisem našel spletnih virov za to temo. Poskusi z drugim vprašanjem.';
  // Preberi vsebino prvih 5 virov (best-effort).
  const sources = [];
  for (let i = 0; i < Math.min(results.length, 5); i++) {
    const r = results[i];
    const content = await fetchPage(r.url);
    sources.push({ title: r.title, url: r.url, snippet: r.snippet, content });
  }
  const srcTxt = sources.map((s, i) => `[${i + 1}] ${s.title}\n${s.url}\n${s.snippet}${s.content ? '\n' + s.content : ''}`).join('\n\n');

  const p = resolveProvider(process.env);
  const ledger = new Ledger(DB_PATH);
  try {
    const cache = new LLMCache(ledger.db);
    const llm = new OpenAICompatibleProvider(p.name, { baseUrl: p.baseUrl, apiKey: p.apiKey, cache });
    const res = await llm.complete({
      provider: p.name, model: p.model, attempt: 0,
      messages: [
        { role: 'system', content: 'Ti si raziskovalni agent ROB. Na podlagi podanih spletnih virov napiši jedrnato raziskovalno poročilo v slovenščini. Ključne trditve citiraj z [1], [2], ... Na koncu dodaj sekcijo "Viri:" s seznamom URL-jev. Uporabi SAMO podane vire — ničesar ne izmišljuj.' },
        { role: 'user', content: `Tema: ${query}\n\nViri:\n${srcTxt}` },
      ],
      temperature: 0.2, maxTokens: 8000,
    });
    const report = res.text;
    await saveResearch(query, report, sources); // arhiv s citati
    return report;
  } finally { ledger.close(); }
}

/** Neposredni pogovor z LLM (ROB) — z živim datumom/uro in (po potrebi) vremenom. */
async function chat(message: string, kindOverride?: string): Promise<string> {
  // Naloga → zabeleži + izvedi; raziskava → globinsko poročilo; pogovor → odgovori.
  const kind = classifyMessage(message);
  if (kind === 'task') return handleTask(message, kindOverride);
  if (kind === 'research') return handleResearch(message);
  const p = resolveProvider(process.env);
  const ledger = new Ledger(DB_PATH);
  try {
    const cache = new LLMCache(ledger.db);
    const llm = new OpenAICompatibleProvider(p.name, { baseUrl: p.baseUrl, apiKey: p.apiKey, cache });

    let live = `Danes je ${nowContext()} (živi lokalni čas strežnika).`;
    const wantsWeather = /(vreme|dež|napoved|temperatura|stopinje|sneg|sonce|veter|nevih|mraz|toplo|oblač|°c|°)/i.test(message);
    if (wantsWeather) {
      const c = cityCoords(message);
      const w = await weatherFor(c.lat, c.lon);
      live += w
        ? `\n\nŽIVI vremenski podatki za ${c.label} (vir Open-Meteo):\n${w}`
        : '\n\n(Vreme trenutno ni dosegljivo — povej, da je vir nedosegljiv.)';
    }

    // Spletno iskanje (živo) — vedno, da lahko ROB utemelji odgovor v spletu.
    const results = await webSearch(message);
    if (results.length) {
      live += `\n\nŽIVI spletni zadetki za vprašanje:\n` + results.map((r, i) => `${i + 1}. ${r.title} — ${r.url}\n   ${r.snippet}`).join('\n');
    }

    const res = await llm.complete({
      provider: p.name, model: p.model, attempt: 0,
      messages: [
        { role: 'system', content: 'Ti si ROB, avtonomni inženirski stroj za Rob AI Studio. Odgovarjaj kratko in tehnično, v slovenščini. Uporabljaj SAMO podane žive podatke (datum/ura/vreme) — ničesar ne izmišljuj.' },
        { role: 'user', content: `${live}\n\nVprašanje uporabnika: ${message}` },
      ],
      temperature: 0.2, maxTokens: 4000,
    });
    return res.text;
  } finally {
    ledger.close();
  }
}

/** Skromen razčlenjevalnik Markdown → odstavki Worda (naslovi, kulice, navaden tekst). */
async function toDocxBuffer(md: string): Promise<Uint8Array> {
  const lines = md.replace(/\r/g, '').split('\n');
  const children = [];
  let inList = false;
  const flushList = () => { if (inList) { /* potrošimo z zadnjo kulico spodaj */ inList = false; } };
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { if (inList) inList = false; continue; }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushList();
      const lvl = Math.min(h[1].length, 6) as HeadingLevel;
      children.push(new Paragraph({ text: h[2], heading: lvl }));
      continue;
    }
    const bullet = line.match(/^\s*[-*+]\s+(.*)$/);
    if (bullet) {
      children.push(new Paragraph({ text: bullet[1].replace(/\*\*(.+?)\*\*/g, '$1'), bullet: { level: 0 } }));
      inList = true; continue;
    }
    const num = line.match(/^\s*\d+[.)]\s+(.*)$/);
    if (num) {
      children.push(new Paragraph({ text: num[1].replace(/\*\*(.+?)\*\*/g, '$1'), bullet: { level: 0 } }));
      inList = true; continue;
    }
    flushList();
    // poudarjeno besedilo: **x** in *x* z minimaliziranjem (pustimo kot tekst)
    const b = line.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\*([^*]+)\*/g, '$1');
    children.push(new Paragraph({ children: [new TextRun(b)] }));
  }
  const doc = new DocxDocument({
    sections: [{ properties: { page: { margin: { top: convertInchesToTwip(1), bottom: convertInchesToTwip(1), left: convertInchesToTwip(1), right: convertInchesToTwip(1) } } }, children }],
  });
  return new Uint8Array(await Packer.toBuffer(doc));
}

/**
 * Normalizira slovenske šumnike in druge diakritike v WinAnsi-kompatibilno
 * (Helvetica v pdf-lib podpira le WinAnsi; č in š bi vrgla napako).
 */
function toWinAnsi(s: string): string {
  return s
    .replace(/č|ć|Č|Ć/g, 'c')
    .replace(/š|Š/g, 's')
    .replace(/ž|Ž/g, 'z')
    .replace(/đ|Đ/g, 'd')
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '');
}

/** Preprosta pretvorba Markdown → PDF (Helvetica, brez zunanjih fontov). */
async function toPdfBuffer(md: string): Promise<Uint8Array> {
  const pdf = await PDFDocument.create();
  const font = await pdf.embedFont(StandardFonts.Helvetica);
  const bold = await pdf.embedFont(StandardFonts.HelveticaBold);
  const page = pdf.addPage([595, 842]); // A4
  const { width } = page.getSize();
  const ml = 46; const sizeW = width - ml * 2;
  let y = 820;
  const lines = md.replace(/\r/g, '').split('\n');
  for (const raw of lines) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { y -= 10; if (y < 40) { y = 820; page.drawText('', { x: ml, y }); pdf.addPage([595, 842]); }  continue; }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    let content = line; let f = font; let sz = 11; let lead = 16;
    if (h) {
      content = h[2];
      const lvl = h[1].length;
      if (lvl <= 1) { f = bold; sz = 20; lead = 26; }
      else if (lvl === 2) { f = bold; sz = 16; lead = 22; }
      else { f = bold; sz = 13; lead = 19; }
    } else if (/^\s*>/.test(line)) { content = line.replace(/^\s*>/, ''); f = font; sz = 10; lead = 15; }
    else { content = line.replace(/^\s*[-*+]\s+/, '• ').replace(/^\s*\d+[.)]\s+/,''); }
    content = content.replace(/\*\*(.+?)\*\*/g, '$1').replace(/\[(.+?)\]\((.+?)\)/g, '$1');
    content = toWinAnsi(content);   // Helvetica ne zmore č/š → prenormalizacija
    // Wrap na sirino (byte-based; helvetica close enough)
    const words = content.split(' ');
    let cur = '';
    for (const w of words) {
      const test = (cur ? cur + ' ' : '') + w;
      if (f.widthOfTextAtSize(test, sz) <= sizeW) { cur = test; }
      else {
        page.drawText(cur, { x: ml, y, size: sz, font: f, color: rgb(0.08, 0.08, 0.1) });
        y -= lead; cur = w;
        if (y < 40) { y = 820 - lead; pdf.addPage([595, 842]); }
      }
    }
    if (cur) {
      page.drawText(cur, { x: ml, y, size: sz, font: f, color: rgb(0.08, 0.08, 0.1) });
      y -= lead;
      if (y < 40) { y = 820 - lead; pdf.addPage([595, 842]); }
    }
  }
  return new Uint8Array(await pdf.save());
}

/** Markdown → Excel (.xlsx). Markdown tabele | a | b | → Excel preglednice
 *  (ena preglednica na izvorni del), ostalo kot odstavki v prvi koloni. */
async function toXlsxBuffer(md: string): Promise<Uint8Array> {
  const wb = new ExcelJS.Workbook();
  wb.creator = 'Rob AI'; wb.created = new Date();
  const lines = md.replace(/\r/g, '').split('\n');
  let ws = wb.addWorksheet('Vsebina');
  ws.views = [{ state: 'normal' }];
  const rows: string[][] = [];
  let inTable = false; let tableRows: string[][] = [];
  const pushTable = () => {
    if (tableRows.length) {
      const name = 'Tabela' + wb.worksheets.length;
      const t = wb.addWorksheet(name);
      tableRows.forEach(r => t.addRow(r));
      t.getRow(1).font = { bold: true };
      t.columns.forEach(c => { if (c) c.width = 24; });
    }
    tableRows = [];
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { inTable = false; continue; }
    if (/^\|.*\|$/.test(line)) {
      inTable = true;
      const cells = line.replace(/^\||\|$/g, '').split('|').map(s => s.trim().replace(/\*\*/g, ''));
      if (!/^:?-{2,}:?$/.test(cells.join('').replace(/[:\-]/g, ''))) {
        tableRows.push(cells);
      }
      continue;
    }
    if (inTable) { pushTable(); inTable = false; }
    // naslov → prvi stolpec, poudarjeno
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    rows.push([h ? h[2] : line.replace(/^\s*[-*+]\s+/, '').replace(/\*\*(.+?)\*\*/g, '$1')]);
  }
  pushTable();
  // nespecificirano besedilo v glavno preglednico "Vsebina"
  rows.forEach(r => ws.addRow(r));
  ws.getColumn(1).width = 60;
  if (JSON.stringify(rows) === '[]' && wb.worksheets.length === 1) ws.addRow(['Sistem ni zaznal strukturiranih podatkov.']);
  const buf = await wb.xlsx.writeBuffer();
  return new Uint8Array(buf);
}

/** Markdown → HTML (spremeni vsebino v okrašeno HTML, za ogled). */
async function mdToHtml(rel: string): Promise<{ html: string; isHtml: boolean } | null> {
  const abs = resolveArtefact(rel);
  const f = Bun.file(abs);
  if (!(await f.exists())) return null;
  const ext = (rel.split('.').pop() || '').toLowerCase();
  if (ext === 'html' || ext === 'htm') {
    return { html: await f.text(), isHtml: true };
  }
  const md = await f.text();
  const body = marked.parse(md) as string;
  const html = `<!DOCTYPE html><html lang="sl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Artefakt</title>
<style>body{font:15px/1.6 system-ui,sans-serif;margin:0 auto;max-width:760px;padding:28px;color:#0d1420}
h1,h2,h3{margin:1.2em 0 .4em;line-height:1.25;color:#061020}code{background:#eef2f7;border-radius:4px;padding:1px 5px}
pre{background:#0a1628;color:#eaf3ff;padding:14px;border-radius:10px;overflow:auto}
blockquote{border-left:3px solid #4fc3ff;margin:.6em 0;padding:.2em 1em;color:#406a96}
table{border-collapse:collapse;width:100%}td,th{border:1px solid #d4dee8;padding:6px 10px}th{background:#eef2f7}
a{color:#1e6fd0}</style></head><body>${body}</body></html>`;
  return { html, isHtml: false };
}

// =====================================================================
//  Izvedba nove naloge
// =====================================================================

/** Požene novo nalogo skozi Hermes. Vrne runId + rezultat. */
async function runTask(task: string, kind: 'full' | 'dashboard'): Promise<Record<string, unknown>> {
  const p = resolveProvider(process.env);
  const ledger = new Ledger(DB_PATH);
  const cache = new LLMCache(ledger.db);
  const llm = new OpenAICompatibleProvider(p.name, { baseUrl: p.baseUrl, apiKey: p.apiKey, cache });
  const memory: MemoryStore = new SqliteMemoryStore(ledger.db);
  const runId = ledger.createRun({ note: `preko command center (${kind})` });
  const runner = Runner.forRun(runId, {
    ledger,
    agents: agentsFor(kind),
    llm,
    provider: p.name,
    model: p.model,
    memory,
    fs: new Disk(OUT_ROOT),
    exec: new BunExec(),
    execCwdRoot: OUT_ROOT,
  });
  try {
    const out = await runner.run(task);
    return { task, ...out };
  } finally {
    ledger.close();
  }
}

/**
 * Faza 0 — avtonomno izvedbeno jedro = Python RSI/GStack orkestrator.
 * Spožene `python run_swarm.py --target <modul> --directive <navodilo>` v
 * podprocesu (ista pot kot `./rob build`). LoopX samozdravitvena zanka
 * (pytest → LLM popravi → 100% zelen) je notranje v RSI jedru.
 *
 * ASINHRONO: `startBuild` vrne build_id TAKOJ (ne blokira requesta); build
 * teče v ozadju, status se polni v `BUILDS` in bere prek /api/build/status.
 */
const BUILDS = new Map<string, Record<string, unknown>>();

function buildStatus(buildId: string): Record<string, unknown> | null {
  const b = BUILDS.get(buildId);
  return b ? { ...b, stdout: String(b.stdout || '').slice(0, 4000), stderr: String(b.stderr || '').slice(0, 2000) } : null;
}

function startBuild(target: string, directive: string, maxRetries = 5, timeoutMs = 600000): Record<string, unknown> {
  const pythonCmd = process.env.PYTHON_BIN ?? 'python';
  const buildId = crypto.randomUUID();
  const build: Record<string, unknown> = {
    buildId, target, status: 'running', started: Date.now(), seconds: 0,
    exitCode: null, timedOut: false, moduleDir: `actions/${target}`, stdout: '', stderr: '',
  };
  BUILDS.set(buildId, build);
  // Počisti stare build-e (drži mapo omejeno).
  if (BUILDS.size > 20) { for (const [k, v] of BUILDS) { if (String(v.status) !== 'running') BUILDS.delete(k); if (BUILDS.size <= 20) break; } }
  (async () => {
    let exitCode = -1;
    let timedOut = false;
    let sout = '';
    let serr = '';
    try {
      const proc = Bun.spawn({
        cmd: [pythonCmd, 'run_swarm.py', '--target', target, '--directive', directive,
          '--agent', 'GSTACK-Architect', '--max-retries', String(maxRetries)],
        cwd: OUT_ROOT,
        stdio: ['ignore', 'pipe', 'pipe'],
        // cp1250 pipe → emoji (🤖) v run_swarm.py print_banner bi podrl izvajanje;
        // UTF-8 reši (enako kot pri LiteLLM).
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      });
      const timer = setTimeout(() => { timedOut = true; try { proc.kill(); } catch { /* */ } }, timeoutMs);
      try {
        sout = await new Response(proc.stdout).text();
        serr = await new Response(proc.stderr).text();
        exitCode = await proc.exited;
      } finally {
        clearTimeout(timer);
      }
    } catch (err) {
      serr += '\n' + String(err instanceof Error ? err.message : err);
    }
    if (timedOut) serr += `\n[timeout] build prekinjen po ${Math.round(timeoutMs / 1000)} s.`;
    build.stdout = sout;
    build.stderr = serr;
    build.exitCode = exitCode;
    build.timedOut = timedOut;
    build.seconds = Math.round((Date.now() - (build.started as number)) / 100) / 10;
    build.status = (exitCode === 0 && !timedOut) ? 'done' : 'failed';
  })();
  return {
    ok: true,
    buildId,
    target,
    status: 'running',
    moduleDir: `actions/${target}`,
  };
}

function runRsiBuild(target: string, directive: string, maxRetries = 5, timeoutMs = 600000): Record<string, unknown> {
  return startBuild(target, directive, maxRetries, timeoutMs);
}

// =====================================================================
//  HTTP strežnik
// =====================================================================

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      // Brez CORS * — dashboard je same-origin (varno; brez avtentikacijskega
      // pretočnega kanala za cross-origin).
    },
  });
}

/** Content-Type glede na koncnico datoteke (za renderiran ogled artefakta). */
function contentTypeFor(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? '';
  switch (ext) {
    case 'html': case 'htm': return 'text/html; charset=utf-8';
    case 'md': case 'markdown': return 'text/markdown; charset=utf-8';
    case 'json': return 'application/json; charset=utf-8';
    case 'css': return 'text/css; charset=utf-8';
    case 'js': case 'mjs': return 'application/javascript; charset=utf-8';
    case 'py': return 'text/x-python; charset=utf-8';
    case 'txt': case 'log': return 'text/plain; charset=utf-8';
    case 'png': return 'image/png';
    case 'jpg': case 'jpeg': return 'image/jpeg';
    case 'svg': return 'image/svg+xml';
    case 'pdf': return 'application/pdf';
    default: return 'application/octet-stream';
  }
}

// =====================================================================
//  Faza 2 — Gmail → agendi (čaka na potrditev). LLM-free polling worker.
// =====================================================================
const GMAIL_CURSOR_FILE = `${OUT_ROOT}/.rob_ai/gmail_cursor.json`;

/** Razpozna vrsto obdelave iz cilja (Auto). Uporabniku NI treba izbirati. */
function detectKind(goal: string): string {
  const g = (goal || '').toLowerCase();
  if (/(razdeli|dekompozicij|podnalog|celoten sistem|razdeljeno|povezanih modulov|več modulov|\d+ modulov)/.test(g)) return 'plan';
  if (/(adversarial|kritika|critique|multi-agent|pregled kode|sodnik|oponent)/.test(g)) return 'team';
  if (/(pristop|variant|\d+ pristop|alternativ|načinov)/.test(g)) return 'fork';
  if (/(spremeni|dodaj funkcijo|izboljšaj|nadgradi|refaktor)/.test(g) && /(modul|actions\/)/.test(g)) return 'modify';
  if (/(spetna|dashboard|html|\.html|<html)/.test(g)) return 'html';
  if (/(markdown|predlog|poročilo|dokument|\.md|specifikacij|poslovni predlog)/.test(g)) return 'markdown';
  return 'python';
}

/** Prebere cursor (Set<string> že-obdelanih mail id). */
function readGmailCursor(): Set<string> {
  try {
    const txt = Bun.file(GMAIL_CURSOR_FILE).textSync?.() ?? '';
    const arr = JSON.parse(txt || '[]') as string[];
    return new Set(Array.isArray(arr) ? arr : []);
  } catch { return new Set(); }
}

async function writeGmailCursor(ids: Set<string>): Promise<void> {
  try {
    // Bun.write je asinhrone; BEZ await se cursor ne zapiše zanesljivo pred
    // naslednjim pollom → poll ponovi iste mail-e (duplicate). Await je nujen.
    await Bun.write(GMAIL_CURSOR_FILE, JSON.stringify([...ids], null, 0));
  } catch { /* ignore */ }
}

/** Preves Snippet/From/Subject iz Gmail metadata odziva. */
function gmailMeta(d: unknown): { from: string; subject: string } {
  let from = ''; let subject = '';
  const headers = ((d as { payload?: { headers?: { name?: string; value?: string }[] } }).payload?.headers) ?? [];
  for (const h of headers) {
    if (h.name === 'From') from = h.value ?? '';
    if (h.name === 'Subject') subject = h.value ?? '';
  }
  return { from, subject };
}

/** Doda mail kot naloga v agendo (source=gmail), ostane pending (čaka potrditev).
    DEDUP: če agenda že vsebuje nalogo z istim goal (iz istega maila), ne doda.
    Vrne true, če je bila dodana; false, če je že obstajala (podvojeno). */
async function agendaAddGmail(goal: string, kind: string): Promise<boolean> {
  // Preveri, ali že obstaja (ne glede na status) — robustno pred cursorjevo krha.
  const chk = Bun.spawn({
    cmd: ['python', '-c',
      `from core.agenda import all_; import json; print(json.dumps([ (i.get('goal') or '')[:120] for i in all_() ]))`],
    cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  });
  const chkOut = await new Response(chk.stdout).text();
  await chk.exited;
  let existGoals: string[] = [];
  try { const p = JSON.parse(chkOut.trim() || '[]'); existGoals = Array.isArray(p) ? p : []; } catch { existGoals = []; }
  const g = (goal || '').slice(0, 120);
  if (existGoals.includes(g)) return false;   // že v agendi → ne podvajaj

  const proc = Bun.spawn({
    cmd: ['python', '-c',
      `from core.agenda import add; import json; print(json.dumps(add(${JSON.stringify(goal)}, kind=${JSON.stringify(kind)}, source='gmail')))`],
    cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
  });
  await proc.exited;
  return true;
}

/** Preskoči očitna sistemska sporočila/obvestila (ne prava povpraševanja).
    Širši vzorci: angleška obvestila (announcement/billing/notification…),
    slovenska varnostna opozorila (opozorilo/varnostn/geslo…) in notification
    pošiljatelji (no-reply, accounts.google, sc.mail.deepseek…). Brez tega bi
    P1 daemon obvestila avtomatsko izvajal kot kodne naloge (strošek/junk). */
function isSystemNotice(text: string): boolean {
  return /(delili|deljenje|obvestilo|opozorilo|varnostn|gesl|security|verifikac|byteplus|recovery|newsletter|novost.*google|račun.*delili|dostop.blokiran|google.*obvesti|povezavo\|podatek.*delil|sprememba.*gesla|two.?factor|announcement|billing|notification|unusual|suspicious|no.?reply|noreply|accounts\.google|sc\.mail\.deepseek|peak.?off.?peak|welcome|alert)/i.test(text);
}

/**
 * Gmail polling worker: prebere zadnja neprebrana sporočila, doda nova (ki
 * še niso v cursorju) v agendo kot `pending` (source=gmail). NE avtomatsko
 * obdela — uporabnik pregleda na dashboardu. Ne kuriti LLM (samo Gmail API).
 */
async function gmailToAgenda(): Promise<{ added: number }> {
  let added = 0;
  const at = await googleAccessToken();
  if (!at) return { added };               // ni avtorizacije → skip
  const list = await googleGet('/gmail/v1/users/me/messages?maxResults=12&q=is:unread');
  if (!list) return { added };
  const messages = (list as { messages?: { id?: string }[] }).messages ?? [];
  const cursor = readGmailCursor();
  for (const m of messages) {
    const id = m.id; if (!id || cursor.has(id)) continue;
    const md = await googleGet(`/gmail/v1/users/me/messages/${id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject`);
    if (!md) continue;
    const { from, subject } = gmailMeta(md);
    const snippet = (md as { snippet?: string }).snippet ?? '';
    // Goal: Subject + izvor kontekst (snippet skrajšan). Raw — brez LLM limanje.
    const goal = subject.trim() ? subject.trim() : (snippet.trim() || 'Povpraševanje iz emaila');
    // Filter: preskoči očitna sistemska sporočila/obvestila (ne povpraševanja),
    // da ne zamašimo agende z Google obvestili npr. "S storitvijo byteplus ste delili…".
    if (isSystemNotice(goal + ' ' + snippet + ' ' + from)) {
      console.log(`[gmail-poll] preskočeno (obvestilo): ${id} «${subject.slice(0, 60)}»`);
      continue;
    }
    const kind = detectKind(goal + ' ' + snippet);
    const didAdd = await agendaAddGmail(`${goal} (od: ${from})`, kind);
    cursor.add(id);     // oznaci obdeleno → ne ponovi
    if (didAdd) added++;   // štej samo res dodane (dedup že obstajajoče skippa)
  }
  await writeGmailCursor(cursor);
  return { added };
}

// HTTPS (self-signed) za glasovni vnos prek LAN. Če certa ni → pade nazaj na HTTP.
const TLS_KEY = `${OUT_ROOT}/certs/key.pem`;
const TLS_CERT = `${OUT_ROOT}/certs/cert.pem`;
async function tlsOptions(): Promise<Record<string, unknown>> {
  // HTTP po defaultu (Google OAuth ima registriran http redirect → tok mora
  // pristati na http://localhost:8787). Za HTTPS nastavi DASH_HTTPS=1 (certi
  // v certs/), npr. za glasovni vnos prek LAN-a.
  if (process.env.DASH_HTTPS !== '1') return {};
  const k = Bun.file(TLS_KEY), c = Bun.file(TLS_CERT);
  if (await k.exists() && await c.exists()) {
    return { tls: { key: await k.text(), cert: await c.text() } };
  }
  return {};
}

/** Trigger ključne besede za vsak gstack skill (progressive disclosure). */
const SKILL_KEYWORDS: Record<string, string[]> = {
  'office-hours': ['ideja', 'brainstorm', 'produkt', 'pitch'],
  'plan-ceo-review': ['strategija', 'ceo', 'obseg', 'vizija'],
  'plan-eng-review': ['arhitektura', 'inženir', 'načrt'],
  'plan-design-review': ['dizajn', 'oblikovanje', 'ui', 'ux'],
  'plan-devex-review': ['dx', 'razvijalec'],
  'autoplan': ['celoten pregled', 'avtoplan', 'revizija'],
  'design-consultation': ['design sistem', 'barve', 'tipografija'],
  'plan-tune': ['uglaševanje', 'tune', 'parametri'],
  'spec': ['specifikacija', 'spec', 'issue'],
  'review': ['preglej kodo', 'code review', 'diff'],
  'codex': ['drugo mnenje', 'codex', 'openai'],
  'investigate': ['bug', 'napaka', 'debug', 'odpravljanje'],
  'design-review': ['vizualni pregled', 'politura', 'visual'],
  'design-shotgun': ['variante dizajna', 'različice', 'shotgun'],
  'design-html': ['produkcijski html', 'css', 'stran'],
  'devex-review': ['developer experience'],
  'qa': ['qa', 'testiraj', 'testiranje'],
  'qa-only': ['qa poročilo', 'samo testiranje'],
  'scrape': ['pobriši podatke', 'scrape', 'web scraping'],
  'skillify': ['kodificiraj', 'skillify'],
  'ship': ['ship', 'deploy', 'objavi', 'združi'],
  'land-and-deploy': ['land', 'deploy', 'pr'],
  'canary': ['canary', 'monitoring po deployu'],
  'landing-report': ['dashboard čakalne vrste', 'landing'],
  'document-release': ['posodobi dokumentacijo', 'release docs'],
  'document-generate': ['generiraj dokumentacijo', 'docs'],
  'setup-deploy': ['nastavi deploy'],
  'gstack-upgrade': ['nadgradi gstack', 'upgrade'],
  'context-save': ['shrani kontekst', 'save'],
  'context-restore': ['obnovi kontekst', 'restore'],
  'learn': ['upravljaj znanja', 'learnings'],
  'retro': ['retrospektiva', 'tedenski pregled'],
  'health': ['kakovost kode', 'health dashboard'],
  'benchmark': ['benchmark', 'zmogljivost'],
  'benchmark-models': ['primerjava modelov', 'cross-model'],
  'cso': ['varnostni pregled', 'security', 'cso'],
  'setup-gbrain': ['nastavi gbrain', 'memory setup'],
  'sync-gbrain': ['sinhroniziraj gbrain', 'sync memory'],
  'browse': ['brskaj', 'browse', 'splet'],
  'open-gstack-browser': ['odpri brskalnik', 'browser'],
  'setup-browser-cookies': ['uvoz piškotkov', 'cookies'],
  'pair-agent': ['seznani agenta', 'pair'],
  'ios-qa': ['ios qa', 'iphone test'],
  'ios-fix': ['ios popravi', 'ios bug'],
  'ios-design-review': ['ios dizajn', 'iphone ui'],
  'ios-clean': ['ios cleanup', 'odstrani debug'],
  'ios-sync': ['ios bridge', 'resync'],
  'careful': ['nevarni ukaz', 'careful', 'varovanje'],
  'freeze': ['omeji urejanje', 'freeze', 'zamrzni'],
  'guard': ['varnostni način', 'guard'],
  'unfreeze': ['odkleni urejanje', 'unfreeze'],
  'make-pdf': ['pdf', 'markdown v pdf'],
  'diagram': ['diagram', 'flowchart'],
  'gstack': ['router', 'kateri skill', 'gstack'],
};

// ── Google OAuth + API (Drive / Gmail / Calendar) — izpostavljeno iz fetch handlerja ──
async function handleGoogleApi(req: Request, url: URL): Promise<Response> {
  if (req.method === 'GET' && url.pathname === '/api/google/auth') {
    const u = await googleAuthUrl(G_SCOPES);
    if (!u) return json({ ok: false, error: 'client_secret.json manjka ali ni veljaven' }, 500);
    return Response.redirect(u, 302);
  }
  if (req.method === 'GET' && url.pathname === '/api/google/oauth2callback') {
    const code = url.searchParams.get('code') || '';
    const gerr = url.searchParams.get('error') || '';
    console.log(`[google] callback code_len=${code.length} error=${gerr || '—'}`);
    const okCall = await googleExchangeCode(code);
    const html = okCall
      ? '<html><body style="font:15px system-ui;background:#061020;color:#eef;"><div style="max-width:420px;margin:10vh auto;padding:30px;border:1px solid #333;border-radius:14px;background:#0a1628"><h2 style="color:#ffd166">✅ Povezano z Googlom</h2><p>Token je shranjen. Vrni se na dashboard in klikni Drive / Email / Calendar.</p><p><a href="/" style="color:#4fc3ff">Nazaj na dashboard</a></p></div></body></html>'
      : '<html><body style="font:15px system-ui;background:#061020;color:#eef"><div style="max-width:420px;margin:10vh auto;padding:30px;border:1px solid #333;border-radius:14px;background:#301010"><h2 style="color:#ff5c7a">Napaka</h2><p>Google avtorizacija ni uspela. Poskusi znova.</p></div></body></html>';
    return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
  }
  if (req.method === 'GET' && url.pathname === '/api/google/drive') {
    const q = url.searchParams.get('q') || '';
    const d = await googleGet(`/drive/v3/files?pageSize=12&fields=files(id,name,mimeType,modifiedTime)&orderBy=modifiedTime desc&q=${encodeURIComponent("'" + q + "' in parents or trashed=false")}`);
    return d ? json({ ok: true, files: (d as { files?: unknown[] }).files || [] }) : json({ ok: false, error: 'ni avtorizacije / napaka', authorized: false }, 401);
  }
  if (req.method === 'GET' && url.pathname === '/api/google/email') {
    const d = await googleGet('/gmail/v1/users/me/messages?maxResults=10');
    if (!d) return json({ ok: false, error: 'ni avtorizacije / napaka', authorized: false }, 401);
    const list = (d as { messages?: { id?: string }[] }).messages || [];
    const out: { id: string; snippet: string }[] = [];
    for (const m of list.slice(0, 10)) {
      const md = await googleGet(`/gmail/v1/users/me/messages/${m.id}?format=metadata&metadataHeaders=From&metadataHeaders=Subject`);
      const x = md as { snippet?: string } | null;
      out.push({ id: m.id || '?', snippet: x?.snippet || '' });
    }
    return json({ ok: true, messages: out });
  }
  if (req.method === 'GET' && url.pathname === '/api/google/calendar') {
    const mY = new Date().toISOString();
    const d = await googleGet(`/calendar/v3/calendars/primary/events?maxResults=8&singleEvents=true&orderBy=startTime&timeMin=${encodeURIComponent(mY)}&fields=items(summary,start)`);
    return d ? json({ ok: true, events: (d as { items?: unknown[] }).items || [] }) : json({ ok: false, error: 'ni avtorizacije / napaka', authorized: false }, 401);
  }
  if (req.method === 'GET' && url.pathname === '/api/google/status') {
    const tok = await googleToken();
    if (!tok) return json({ ok: true, connected: false });
    return json({
      ok: true,
      connected: true,
      expired: !!tok.expires_at && Date.now() > (tok.expires_at as number),
      expires_at: tok.expires_at ?? null,
      has_refresh: !!tok.refresh_token,
    });
  }
  if (req.method === 'POST' && url.pathname === '/api/google/poll') {
    const r = await gmailToAgenda();
    return json({ ok: true, added: r.added });
  }
  return json({ ok: false, error: '404 · neznana google pot: ' + url.pathname }, 404);
}

const tls = await tlsOptions();
const server = Bun.serve({
  port: PORT,
  ...tls,
  async fetch(req) {
    const url = new URL(req.url);
    const t0 = Date.now();
    // Request log — za lažjo diagnostiko (npr. "empty reply": vidimo, da zahtevek
    // pride, pa ni odziva). Izpišemo ob začetku in ob zaključku (status).
    console.log(`[req] ${new Date().toLocaleTimeString('sl-SI')} ${req.method} ${url.pathname}`);

    // CORS preflight
    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204 });
    }

    // Zaščita API-ja: /api/* (razen /api/auth, /api/health in Google OAuth
    // callbacka) zahteva veljavno rob_session piškotko, ko je ROB_API_TOKEN
    // nastavljen. Callback je izvzet: Google preusmeri cross-site (SameSite
    // cookie se ne pošlje), OAuth code pa je sam po sebi avtorizacija.
    const API_PUBLIC = ['/api/auth', '/api/health', '/api/google/oauth2callback'];
    if (url.pathname.startsWith('/api/') && !API_PUBLIC.includes(url.pathname)) {
      if (!isAuthed(req)) return unauthorized();
    }

    // Prijava: potrdi ROB_API_TOKEN → nastavi HttpOnly session piškotko.
    if (req.method === 'POST' && url.pathname === '/api/auth') {
      const raw = await req.text().catch(() => '');
      let body: { token?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      if (!API_TOKEN) return json({ ok: true });                       // zaščita off
      if (String(body.token || '') !== API_TOKEN) return json({ ok: false, error: 'napačen token' }, 401);
      const sid = crypto.randomUUID();
      SESSIONS.add(sid);
      return new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json',
                   'Set-Cookie': `rob_session=${sid}; HttpOnly; Path=/; SameSite=Lax; Max-Age=86400` },
      });
    }

    // Edini dashboard je Command Center (/command); / → preusmeritev
    // (odpravljen duplikat z out/Dashboard.html).
    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      return new Response(null, { status: 302, headers: { 'Location': '/command' } });
    }

    // Novi Command Center (futuristični) — servira command-center-mockup.html.
    if (req.method === 'GET' && url.pathname === '/command') {
      const html = await Bun.file(`${OUT_ROOT}/command-center-mockup.html`).text().catch(() => null)
        ?? await Bun.file('command-center-mockup.html').text();
      return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }

    // API: health / ledger / runs / news
    if (req.method === 'GET' && url.pathname === '/api/health') return json(await health());
    if (req.method === 'GET' && url.pathname === '/api/ledger') return json({ events: readEvents() });
    if (req.method === 'GET' && url.pathname === '/api/runs') return json({ runs: readRuns() });
    if (req.method === 'GET' && url.pathname === '/api/news') return json({ news: await getNews() });

    // API: seznam produciranih modulov (iz out/)
    if (req.method === 'GET' && url.pathname === '/api/modules') {
      return json({ modules: await listModules() });
    }
    // "Popravi to" — RSI module (actions/<name>/), ki jih uporabnik lahko uredi.
    if (req.method === 'GET' && url.pathname === '/api/editable') {
      return json({ editable: await listEditable() });
    }
    // Rešitev naloge — vse datoteke modula actions/<name>/ (za kartico rezultata).
    if (req.method === 'GET' && url.pathname === '/api/module') {
      const name = (url.searchParams.get('name') || '').replace(/[^a-zA-Z0-9_-]/g, '');
      if (!name) return json({ ok: false, error: 'name manjka' });
      const dir = `${OUT_ROOT}/actions/${name}`;
      const files: { name: string; path: string; content: string; size: number }[] = [];
      try {
        const glob = new Bun.Glob('*.{py,md,html,htm,txt,json,yml,yaml,ini,cfg,env}');
        for await (const f of glob.scan({ cwd: dir, onlyFiles: true })) {
          const content = await Bun.file(`${dir}/${f}`).text().catch(() => '');
          files.push({ name: f, path: `actions/${name}/${f}`, content, size: content.length });
        }
      } catch { /* actions/<name> morda ne obstaja */ }
      files.sort((a, b) => a.name.localeCompare(b.name));
      return json({ ok: true, name, files });
    }
    // Sistemske metrike (GBRAIN tasks/blacklist + GRAPHIFY nodes + moduli).
    if (req.method === 'GET' && url.pathname === '/api/metrics') {
      return json(await systemMetrics());
    }
    // Živi dogodki (zadnji realni dogodki iz audit.jsonl — dashboard feed).
    if (req.method === 'GET' && url.pathname === '/api/events') {
      const f = Bun.file(`${OUT_ROOT}/.rob_ai/audit.jsonl`);
      const events: { t: string; s: string; c: string; m: string }[] = [];
      try {
        if (await f.exists()) {
          const text = await f.text();
          const lines = text.trim().split('\n').slice(-10);
          for (const line of lines) {
            try {
              const d = JSON.parse(line);
              const ts = new Date(d.ts * 1000);
              const p = (n: number) => String(n).padStart(2, '0');
              const t = `${p(ts.getHours())}:${p(ts.getMinutes())}:${p(ts.getSeconds())}`;
              const ev = String(d.event || '');
              let s = (ev === 'daemon-task' ? 'TASK' : ev === 'rsi-run' ? 'RSI' : ev === 'build' ? 'BUILD' : ev === 'agent' ? 'AGENT' : ev.toUpperCase().slice(0, 6));
              let c = 's-run';
              const st = String(d.status || '');
              if (st === 'ok' || st === 'done' || st === 'success' || st === 'VERIFIED GREEN') c = 's-ok';
              if (st === 'failed' || st === 'FAILED') c = 's-crit';
              const m = `${d.project || ''} ${String(d.detail || '').slice(0, 60)}`.trim();
              events.push({ t, s, c, m });
            } catch { /* neveljavna vrstica JSON — preskoči */ }
          }
        }
      } catch { /* audit morda ne obstaja */ }
      return json({ ok: true, events });
    }
    // SSE — živi tok dogodkov iz audit.jsonl (live dashboard, brez pollinga).
    if (req.method === 'GET' && url.pathname === '/api/stream') {
      const encoder = new TextEncoder();
      let offset = 0;
      const stream = new ReadableStream<Uint8Array>({
        async start(controller) {
          const send = (obj: Record<string, unknown>) => {
            try { controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`)); } catch { /* */ }
          };
          send({ type: 'connected', ts: Date.now() });
          const f = Bun.file(`${OUT_ROOT}/.rob_ai/audit.jsonl`);
          try { const st = await f.stat(); offset = st.size; } catch { /* */ }
          const tick = async () => {
            try {
              const st = await f.stat();
              if (st.size > offset) {
                const buf = await f.slice(offset, st.size).arrayBuffer();
                offset = st.size;
                const lines = new TextDecoder().decode(buf).split('\n');
                for (const line of lines) {
                  if (!line.trim()) continue;
                  try {
                    const d = JSON.parse(line);
                    const ts = new Date(d.ts * 1000);
                    const p2 = (n: number) => String(n).padStart(2, '0');
                    const t = `${p2(ts.getHours())}:${p2(ts.getMinutes())}:${p2(ts.getSeconds())}`;
                    const ev = String(d.event || '');
                    const s = (ev === 'daemon-task' ? 'TASK' : ev === 'rsi-run' ? 'RSI' : ev === 'build' ? 'BUILD' : ev === 'agent' ? 'AGENT' : ev.toUpperCase().slice(0, 6));
                    let c = 's-run';
                    const stt = String(d.status || '');
                    if (stt === 'ok' || stt === 'done' || stt === 'success' || stt === 'VERIFIED GREEN') c = 's-ok';
                    if (stt === 'failed' || stt === 'FAILED') c = 's-crit';
                    const m = `${d.project || ''} ${String(d.detail || '').slice(0, 60)}`.trim();
                    send({ type: 'event', event: { t, s, c, m } });
                  } catch { /* neveljavna vrstica JSON */ }
                }
              }
            } catch { /* */ }
          };
          const evTimer = setInterval(tick, 3000);
          const hbTimer = setInterval(() => send({ type: 'heartbeat', ts: Date.now() }), 5000);
          req.signal.addEventListener('abort', () => { clearInterval(evTimer); clearInterval(hbTimer); });
        },
      });
      return new Response(stream, { headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive' } });
    }
    // Agenti + bridge-i (iz src/agents/ in core/).
    if (req.method === 'GET' && url.pathname === '/api/agents') {
      return json({ agents: await listAgents() });
    }
    // Sistemski graf (vozlišča + povezave).
    if (req.method === 'GET' && url.pathname === '/api/graph') {
      return json(await systemGraph());
    }
    // Združeni artefakti (moduli + izdelki) s potmi za prenos.
    if (req.method === 'GET' && url.pathname === '/api/artifacts') {
      return json({ artifacts: await listArtifacts() });
    }
    // Pogovor z ROB (neposredni LLM).
    if (req.method === 'POST' && url.pathname === '/api/chat') {
      if (rateLimited(server.requestIP(req)?.address || 'local')) return json({ ok: false, error: 'rate limit: preveč zahtevkov (10/min)' }, 429);
      const raw = await req.text().catch(() => '');
      let body: { message?: unknown; kind?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const message = String(body.message || '').trim();
      if (!message) return json({ ok: false, error: 'sporočilo je prazno' }, 400);
      try {
        const reply = await chat(message, String(body.kind || ''));
        return json({ ok: true, reply });
      } catch (e) {
        return json({ ok: false, error: String(e instanceof Error ? e.message : e) }, 500);
      }
    }
    // Google Gemini TTS (naravni glas → base64 avdio).
    if (req.method === 'POST' && url.pathname === '/api/tts') {
      const raw = await req.text().catch(() => '');
      let body: { text?: unknown; voice?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const text = String(body.text || '').trim();
      const voice = String(body.voice || 'Charon').trim();
      if (!text) return json({ ok: false, error: 'text je prazen' }, 400);
      const tts = await geminiTts(text, voice);
      if (!tts) return json({ ok: false, error: 'TTS ni na voljo (GEMINI_API_KEY manjka?)' }, 500);
      return json({ ok: true, voice, ...tts });
    }
    // Spletno iskanje (DuckDuckGo, brez ključa).
    if (req.method === 'GET' && url.pathname === '/api/search') {
      const q = (url.searchParams.get('q') || '').trim();
      if (!q) return json({ ok: false, error: 'q je prazen' }, 400);
      return json({ ok: true, results: await webSearch(q) });
    }
    // Arhiv raziskav (seznam .md poročil).
    if (req.method === 'GET' && url.pathname === '/api/research') {
      return json({ research: await listResearch() });
    }
    // Izbriši raziskovalno poročilo iz arhiva (gumb Delete v pogledu Raziskovanje).
    if (req.method === 'POST' && url.pathname === '/api/research/delete') {
      const raw = await req.text().catch(() => '');
      let body: { name?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const name = String(body.name || '').replace(/[\\/]/g, '');   // samo basename — brez traversal
      if (!name) return json({ ok: false, error: 'name je obvezen' }, 400);
      const dir = `${OUT_ROOT}/.rob_ai/research/${name}`;
      try {
        if (await Bun.file(dir).exists()) { unlinkSync(dir); }
      } catch { /* napaka pri brisanju */ }
      return json({ ok: true, name });
    }
    // Progressive disclosure: ujemi sporočilo z relevantnimi gstack skilli.
    if (req.method === 'GET' && url.pathname === '/api/skills/match') {
      const q = normalize((url.searchParams.get('q') || '').toLowerCase());
      const skills: string[] = [];
      for (const [name, kws] of Object.entries(SKILL_KEYWORDS)) {
        if (kws.some((k) => q.includes(k))) skills.push(name);
      }
      return json({ ok: true, skills: skills.slice(0, 5) });
    }
    // Zagon gstack skill-a (prek claude CLI, headless).
    if (req.method === 'POST' && url.pathname === '/api/skill') {
      const raw = await req.text().catch(() => '');
      let body: { skill?: unknown; prompt?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const skill = String(body.skill || '').trim().replace(/^\/+/, '');
      const prompt = String(body.prompt || '').trim();
      if (!skill) return json({ ok: false, error: 'skill je prazen' }, 400);
      try {
        const proc = Bun.spawn({
          cmd: ['claude', '-p', '/' + skill, ...(prompt ? [prompt] : []), '--print'],
          cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
          env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
        });
        const out = await new Response(proc.stdout).text();
        const err = await new Response(proc.stderr).text();
        const code = await proc.exited;
        return json({ ok: code === 0, skill, exit: code, log: (out + err).slice(0, 4000) });
      } catch (e) {
        return json({ ok: false, skill, error: String(e instanceof Error ? e.message : e) }, 500);
      }
    }

    // API: ogled vsebine modula (Markdown → HTML ali surov HTML)
    if (req.method === 'GET' && url.pathname === '/api/view') {
      const rel = url.searchParams.get('path') || '';
      const v = await mdToHtml(rel);
      if (!v) return json({ ok: false, error: 'modul ne obstaja: ' + rel }, 404);
      return new Response(v.html, {
        headers: {
          'Content-Type': 'text/html; charset=utf-8',
        },
      });
    }

    // API: prenos-na-zahtevo v Word (.docx) ali PDF (.pdf) iz Markdown
    if (req.method === 'GET' && url.pathname === '/api/export') {
      const rel = url.searchParams.get('path') || '';
      const format = (url.searchParams.get('format') || 'md').toLowerCase();
      const abs = resolveArtefact(rel);
      const f = Bun.file(abs);
      if (!(await f.exists())) return json({ ok: false, error: 'modul ne obstaja: ' + rel }, 404);
      const base = (rel.split('/').pop() || 'modul').replace(/\.[^.]+$/, '');
      if (format === 'docx' || format === 'pdf' || format === 'xlsx') {
        const md = await f.text();
        let buf: Uint8Array; let mime: string; let ext: string;
        if (format === 'docx') { buf = await toDocxBuffer(md); mime = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'; ext = 'docx'; }
        else if (format === 'pdf') { buf = await toPdfBuffer(md); mime = 'application/pdf'; ext = 'pdf'; }
        else { buf = await toXlsxBuffer(md); mime = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'; ext = 'xlsx'; }
        return new Response(buf, {
          headers: { 'Content-Type': mime, 'Content-Disposition': `attachment; filename="${encodeURIComponent(base)}.${ext}"` },
        });
      }
      // else: surov download izvirnika (MD/HTML/PY/JSON...)
      const raw = Bun.file(abs);
      const nm = rel.split('/').pop() || 'modul';
      const buf = await raw.arrayBuffer();
      return new Response(buf, {
        headers: { 'Content-Type': contentTypeFor(nm), 'Content-Disposition': `attachment; filename="${encodeURIComponent(nm)}"` },
      });
    }

    // API: prenesi/preglej dejanski artefakt (npr. out/presentation.html).
    // GET /api/artifact?path=out/presentation.html
    //    → attach download (raw) za tekst.
    // GET /api/artifact?path=out/presentation.html&view=1
    //    → vrne artefakt s PRAVIM Content-Type, da se v brskalniku renderira (odpre).
    if (req.method === 'GET' && url.pathname === '/api/artifact') {
      const rel = (url.searchParams.get('path') || '').replace(/^\/+/, '');
      const view = url.searchParams.get('view') === '1';
      const abs = `${OUT_ROOT}/${rel}`;
      const file = Bun.file(abs);
      const exists = await file.exists();
      if (!exists) return json({ ok: false, error: 'artefakt ne obstaja: ' + rel }, 404);
      const name = rel.split('/').pop() || 'artefakt';
      const buf = await file.arrayBuffer();
      const headers: Record<string, string> = {};
      if (view) {
        headers['Content-Type'] = contentTypeFor(name);
        // Onako, da ni attachment → brskalnik pokaže stran renderirano.
      } else {
        headers['Content-Type'] = 'application/octet-stream';
        headers['Content-Disposition'] = `attachment; filename="${name}"`;
      }
      return new Response(buf, { headers });
    }

    // API: poženi novo nalogo
    if (req.method === 'POST' && url.pathname === '/api/run') {
      if (rateLimited(server.requestIP(req)?.address || 'local')) return json({ ok: false, error: 'rate limit: preveč zahtevkov (10/min)' }, 429);
      const raw = await req.text().catch(() => '');
      let body: { task?: unknown; kind?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const task = String(body.task || '').trim();
      if (!task) return json({ ok: false, error: 'naloga je prazna' }, 400);
      const kind = body.kind === 'dashboard' ? 'dashboard' : 'full';
      try {
        const res = await runTask(task, kind);
        return json({ ok: true, task, ...res });
      } catch (err) {
        return json({ ok: false, error: String(err instanceof Error ? err.message : err) }, 500);
      }
    }

    // Faza 0: Avtonomni build prek RSI/GStack jedra (Python orkestrator).
    // Dashboard in `./rob build` zdaj delita isto zanko (LoopX self-heal).
    if (req.method === 'POST' && url.pathname === '/api/build') {
      if (rateLimited(server.requestIP(req)?.address || 'local')) return json({ ok: false, error: 'rate limit: preveč zahtevkov (10/min)' }, 429);
      const raw = await req.text().catch(() => '');
      let body: { target?: unknown; directive?: unknown; max_retries?: unknown; timeout_seconds?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const target = String(body.target || '').trim().replace(/[^a-zA-Z0-9_-]/g, '_');
      const directive = String(body.directive || '').trim();
      if (!target) return json({ ok: false, error: 'target je prazen' }, 400);
      if (!directive) return json({ ok: false, error: 'directive je prazen' }, 400);
      const maxRetries = Math.min(Number(body.max_retries) || 5, 10);
      // Privzeti timeout 10 min; klient ga lahko skrajša (npr. 60 s za hitre preizkuse).
      const timeoutMs = Math.min(Math.max(Number(body.timeout_seconds) || 600, 15), 3600) * 1000;
      // Asinhrono: vrne buildId TAKOJ; klient polni prek /api/build/status?buildId=...
      try {
        const res = runRsiBuild(target, directive, maxRetries, timeoutMs);
        return json({ ok: true, ...res });
      } catch (err) {
        return json({ ok: false, error: String(err instanceof Error ? err.message : err) }, 500);
      }
    }
    // Command Palette — varni whitelisted CLI ukazi (nobenih poljubnih ukazov).
    const CLI_WHITELIST: Record<string, string[]> = {
      'rob test': ['python', '-m', 'pytest', 'tests/', '-q'],
      'rob eval --dry-run': ['python', 'evaluate_autonomy.py', '--dry-run'],
    };
    if (req.method === 'POST' && url.pathname === '/api/cli') {
      const raw = await req.text().catch(() => '');
      let body: { command?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const cmd = String(body.command || '').trim();
      const argv = CLI_WHITELIST[cmd];
      if (!argv) return json({ ok: false, error: 'neznan ukaz: ' + cmd }, 400);
      const started = Date.now();
      try {
        const proc = Bun.spawn({ cmd: argv, cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
          env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } });
        const out = await Promise.race([
          (async () => { const o = await new Response(proc.stdout).text(); const e = await new Response(proc.stderr).text(); await proc.exited; return o + '\n' + e; })(),
          new Promise<string>((res) => setTimeout(() => { try { proc.kill(); } catch { /* */ } res('⏱ TIMEOUT (120 s)'); }, 120000)),
        ]);
        return json({ ok: true, command: cmd, output: String(out).slice(-2500), seconds: Math.round((Date.now() - started) / 100) / 10 });
      } catch (err) { return json({ ok: false, error: String(err instanceof Error ? err.message : err) }, 500); }
    }

    // Status asinhronega builda (polling).
    if (req.method === 'GET' && url.pathname === '/api/build/status') {
      const buildId = String(url.searchParams.get('buildId') || '').trim();
      if (!buildId) return json({ ok: false, error: 'buildId manjka' }, 400);
      const b = buildStatus(buildId);
      if (!b) return json({ ok: false, error: 'build ne obstaja' }, 404);
      return json({ ok: true, ...b });
    }

    // Faza 3: agenda (čakalna vrsta naročil) — branje in dodajanje.
    // Datoteka je .rob_ai/agenda.json, jo ureja core/agenda.py (Python).
    if (req.method === 'GET' && url.pathname === '/api/agenda') {
      const f = Bun.file(`${OUT_ROOT}/.rob_ai/agenda.json`);
      let items: Record<string, unknown>[] = [];
      if (await f.exists()) { try { items = JSON.parse(await f.text()) as Record<string, unknown>[]; } catch { /* */ } }
      return json({ ok: true, items });
    }
    // P1 — daemon status: heartbeat iz .rob_ai/daemon.json (stanje, tek. naloga, jobi).
    if (req.method === 'GET' && url.pathname === '/api/daemon') {
      const f = Bun.file(`${OUT_ROOT}/.rob_ai/daemon.json`);
      let d: Record<string, unknown> = {};
      if (await f.exists()) { try { d = JSON.parse(await f.text()) as Record<string, unknown>; } catch { /* */ } }
      return json({ ok: true, ...d });
    }
    // P9 — fleet status: workerji, agenda, daemon, spomin (živi pregled flote).
    if (req.method === 'GET' && url.pathname === '/api/fleet') {
      const wf = Bun.file(`${OUT_ROOT}/.rob_ai/fleet_workers.json`);
      let workers: Record<string, unknown> = {};
      if (await wf.exists()) { try { workers = JSON.parse(await wf.text()); } catch { /* */ } }
      const af = Bun.file(`${OUT_ROOT}/.rob_ai/agenda.json`);
      let items: Array<Record<string, unknown>> = [];
      if (await af.exists()) { try { items = JSON.parse(await af.text()); } catch { /* */ } }
      const ag: Record<string, number> = { pending: 0, running: 0, done: 0, failed: 0, total: items.length };
      for (const it of items) {
        const s = String(it?.status || '');
        if (s !== 'total' && s in ag) ag[s]++;
      }
      const df = Bun.file(`${OUT_ROOT}/.rob_ai/daemon.json`);
      let daemon: Record<string, unknown> = {};
      if (await df.exists()) { try { daemon = JSON.parse(await df.text()); } catch { /* */ } }
      let memory: Record<string, number> = {};
      try {
        const mp = Bun.spawn({
          cmd: ['python', '-c', 'from core.memory_sync import count_memory; import json; print(json.dumps(count_memory()))'],
          cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
          env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
        });
        const mo = await new Response(mp.stdout).text();
        await mp.exited;
        memory = JSON.parse(mo.trim() || '{}');
      } catch { /* brez pythona → spomin ni na voljo */ }
      return json({ ok: true, workers, agenda: ag, memory, daemon: {
        state: daemon.state || null, heartbeat_ts: daemon.heartbeat_ts || null,
        current_tasks: daemon.current_tasks || null,
      } });
    }
    if (req.method === 'POST' && url.pathname === '/api/agenda') {
      const raw = await req.text().catch(() => '');
      let body: { goal?: unknown; kind?: unknown; repeat?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const goal = String(body.goal || '').trim();
      if (!goal) return json({ ok: false, error: 'goal je prazen' }, 400);
      const kind = ['python', 'markdown', 'html', 'autonomous', 'modify', 'team', 'fork', 'plan'].includes(String(body.kind)) ? String(body.kind) : 'python';
      // Dodamo prek Python agenda (poohranja isti format kot CLI).
      const proc = Bun.spawn({
        cmd: ['python', '-c', `from core.agenda import add; import json; print(json.dumps(add(${JSON.stringify(goal)}, kind=${JSON.stringify(kind)})))`],
        cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      });
      const out = await new Response(proc.stdout).text();
      const code = await proc.exited;
      let item: Record<string, unknown> = {};
      if (code === 0) { try { item = JSON.parse(out); } catch { /* */ } }
      return json({ ok: code === 0, item });
    }
    // Oznaka statusa agenda naloge (npr. done po obdelavi prek trajne agende).
    if (req.method === 'POST' && url.pathname === '/api/agenda/mark') {
      const raw = await req.text().catch(() => '');
      let body: { id?: unknown; status?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const id = String(body.id || '').trim();
      const status = String(body.status || '').trim();
      if (!id || !status) return json({ ok: false, error: 'id in status sta obvezna' }, 400);
      const proc = Bun.spawn({
        cmd: ['python', '-c', `from core.agenda import mark; mark(${JSON.stringify(id)}, ${JSON.stringify(status)})`],
        cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      });
      await proc.exited;
      return json({ ok: true, id, status });
    }
    // Izbriši ENO nalogo iz agende (gumb Delete v pogledu Agenda).
    if (req.method === 'POST' && url.pathname === '/api/agenda/delete') {
      const raw = await req.text().catch(() => '');
      let body: { id?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const id = String(body.id || '').trim();
      if (!id) return json({ ok: false, error: 'id je obvezen' }, 400);
      const proc = Bun.spawn({
        cmd: ['python', '-c', `from core.agenda import delete_item; import json; print(json.dumps(delete_item(${JSON.stringify(id)})))`],
        cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      });
      const out = await new Response(proc.stdout).text();
      await proc.exited;
      let removed = false;
      try { removed = JSON.parse(out.trim() || 'false'); } catch { /* */ }
      return json({ ok: true, removed });
    }

    // Faza 6: poslovna knjiga (glavna knjiga podjetja) — branje in nov delovnik.
    if (req.method === 'GET' && url.pathname === '/api/business') {
      const f = Bun.file(`${OUT_ROOT}/.rob_ai/business_ledger.json`);
      let items: Record<string, unknown>[] = [];
      let revenue = 0;
      if (await f.exists()) { try { items = JSON.parse(await f.text()) as Record<string, unknown>[]; revenue = items.reduce((s, i) => s + Number(i.revenue || 0), 0); } catch { /* */ } }
      return json({ ok: true, items, revenue });
    }
    if (req.method === 'POST' && url.pathname === '/api/business') {
      const raw = await req.text().catch(() => '');
      let body: { idea?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const idea = String(body.idea || '').trim();
      if (!idea) return json({ ok: false, error: 'ideja je prazna' }, 400);
      // Poslovni delovnik: izvede RSI predlog in zapiše v knjigo (kot CLI --business).
      const proc = Bun.spawn({
        cmd: ['python', 'run_swarm.py', '--business', idea],
        cwd: OUT_ROOT, stdio: ['ignore', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
      });
      const out = await new Response(proc.stdout).text();
      const err = await new Response(proc.stderr).text();
      const code = await proc.exited;
      return json({ ok: code === 0, exit: code, log: (out + err).slice(0, 3000) });
    }

    // ================================================================
    // (G_SCOPES je premaknjen na nivo modula — glej zgoraj ob GOOGLE konfiguraciji.)

    // Google OAuth + API (Drive/Gmail/Calendar) — izpostavljeno v handleGoogleApi.
    if (url.pathname.startsWith('/api/google/')) return await handleGoogleApi(req, url);

    return json({ ok: false, error: '404 · neznana pot: ' + url.pathname }, 404);
  },
});

// Faza 2 — periodični Gmail polling (npr. vsakih 5 min), ko server teče.
setInterval(() => { gmailToAgenda().catch(() => {}); }, 5 * 60 * 1000);

console.log(`\n[command-center] živo na http://localhost:${server.port}/`);
console.log(`  /api/health · /api/ledger · /api/runs · /api/modules · /api/export · POST /api/run\n`);
