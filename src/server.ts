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
//  Google OAuth + API (Drive / Gmail / Calendar)
// =====================================================================
const GOOGLE_SECRET_FILE = `${OUT_ROOT}/client_secret.json`;
const GOOGLE_TOKEN_FILE = `${OUT_ROOT}/.gtoken.json`;
const G_REDIRECT = `http://localhost:${PORT}/api/google/oauth2callback`;

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
    const j = await r.json() as { access_token?: string; refresh_token?: string; expires_in?: number };
    if (!j.access_token) return false;
    await saveGoogleToken({ access_token: j.access_token, refresh_token: j.refresh_token ?? null, expires_at: Date.now() + (j.expires_in ?? 3600) * 1000 });
    return true;
  } catch { return false; }
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
    const r = await fetch(`${p.baseUrl}/models`, { signal: AbortSignal.timeout(2500) });
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
 */
async function runRsiBuild(target: string, directive: string, maxRetries = 5): Promise<Record<string, unknown>> {
  const pythonCmd = process.env.PYTHON_BIN ?? 'python';
  let sout = '';
  let serr = '';
  let exitCode = -1;
  const started = Date.now();
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
    sout = await new Response(proc.stdout).text();
    serr = await new Response(proc.stderr).text();
    exitCode = await proc.exited;
  } catch (err) {
    serr += '\n' + String(err instanceof Error ? err.message : err);
  }
  const seconds = Math.round((Date.now() - started) / 100) / 10;
  const moduleDir = `actions/${target}`;
  return {
    ok: exitCode === 0,
    target,
    exitCode,
    seconds,
    moduleDir,
    stdout: sout.slice(0, 4000),
    stderr: serr.slice(0, 2000),
  };
}

// =====================================================================
//  HTTP strežnik
// =====================================================================

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET,POST,OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type',
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

const server = Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    // CORS preflight
    if (req.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type' } });
    }

    // Serviraj dashboard.
    if (req.method === 'GET' && (url.pathname === '/' || url.pathname === '/index.html')) {
      const html = await Bun.file(`${OUT_ROOT}/out/Dashboard.html`).text().catch(() => null)
        ?? await Bun.file('out/Dashboard.html').text();
      return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }

    // Serviraj roadmap (strateški načrt) — samostojen HTML.
    if (req.method === 'GET' && url.pathname === '/roadmap') {
      const html = `${OUT_ROOT}/.rob_ai/roadmap.html`;
      const file = Bun.file(html);
      if (await file.exists()) {
        return new Response(await file.text(), { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
      }
      return json({ ok: false, error: 'roadmap.html manjka v .rob_ai/' }, 404);
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

    // API: ogled vsebine modula (Markdown → HTML ali surov HTML)
    if (req.method === 'GET' && url.pathname === '/api/view') {
      const rel = url.searchParams.get('path') || '';
      const v = await mdToHtml(rel);
      if (!v) return json({ ok: false, error: 'modul ne obstaja: ' + rel }, 404);
      return new Response(v.html, {
        headers: {
          'Content-Type': v.isHtml ? 'text/html; charset=utf-8' : 'text/html; charset=utf-8',
          'Access-Control-Allow-Origin': '*',
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
          headers: { 'Content-Type': mime, 'Content-Disposition': `attachment; filename="${encodeURIComponent(base)}.${ext}"`, 'Access-Control-Allow-Origin': '*' },
        });
      }
      // else: surov download izvirnika (MD/HTML/PY/JSON...)
      const raw = Bun.file(abs);
      const nm = rel.split('/').pop() || 'modul';
      const buf = await raw.arrayBuffer();
      return new Response(buf, {
        headers: { 'Content-Type': contentTypeFor(nm), 'Content-Disposition': `attachment; filename="${encodeURIComponent(nm)}"`, 'Access-Control-Allow-Origin': '*' },
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
      const headers: Record<string, string> = { 'Access-Control-Allow-Origin': '*' };
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
      const raw = await req.text().catch(() => '');
      let body: { target?: unknown; directive?: unknown; max_retries?: unknown } = {};
      try { body = JSON.parse(raw); } catch { /* ignore */ }
      const target = String(body.target || '').trim().replace(/[^a-zA-Z0-9_-]/g, '_');
      const directive = String(body.directive || '').trim();
      if (!target) return json({ ok: false, error: 'target je prazen' }, 400);
      if (!directive) return json({ ok: false, error: 'directive je prazen' }, 400);
      const maxRetries = Math.min(Number(body.max_retries) || 5, 10);
      try {
        const res = await runRsiBuild(target, directive, maxRetries);
        return json({ ok: true, ...res });
      } catch (err) {
        return json({ ok: false, error: String(err instanceof Error ? err.message : err) }, 500);
      }
    }

    // ================================================================
    // Google integracije: Drive / Gmail / Calendar (OAuth)
    // ================================================================
    const G_SCOPES = ['https://www.googleapis.com/auth/drive.readonly',
      'https://www.googleapis.com/auth/gmail.readonly',
      'https://www.googleapis.com/auth/calendar.readonly'];

    // Začetek avtorizacije → preusmeri na Google.
    if (req.method === 'GET' && url.pathname === '/api/google/auth') {
      const u = await googleAuthUrl(G_SCOPES);
      if (!u) return json({ ok: false, error: 'client_secret.json manjka ali ni veljaven' }, 500);
      return Response.redirect(u, 302);
    }
    // OAuth callback → izmenjaj code za token, vrni na dashboard.
    if (req.method === 'GET' && url.pathname === '/api/google/oauth2callback') {
      const code = url.searchParams.get('code') || '';
      const okCall = await googleExchangeCode(code);
      const html = okCall
        ? '<html><body style="font:15px system-ui;background:#061020;color:#eef;"><div style="max-width:420px;margin:10vh auto;padding:30px;border:1px solid #333;border-radius:14px;background:#0a1628"><h2 style="color:#ffd166">✅ Povezano z Googlom</h2><p>Token je shranjen. Vrni se na dashboard in klikni Drive / Email / Calendar.</p><p><a href="/" style="color:#4fc3ff">Nazaj na dashboard</a></p></div></body></html>'
        : '<html><body style="font:15px system-ui;background:#061020;color:#eef"><div style="max-width:420px;margin:10vh auto;padding:30px;border:1px solid #333;border-radius:14px;background:#301010"><h2 style="color:#ff5c7a">Napaka</h2><p>Google avtorizacija ni uspela. Poskusi znova.</p></div></body></html>';
      return new Response(html, { headers: { 'Content-Type': 'text/html; charset=utf-8' } });
    }
    // Drive: seznam datotek.
    if (req.method === 'GET' && url.pathname === '/api/google/drive') {
      const q = url.searchParams.get('q') || '';
      const d = await googleGet(`/drive/v3/files?pageSize=12&fields=files(id,name,mimeType,modifiedTime)&orderBy=modifiedTime desc&q=${encodeURIComponent("'" + q + "' in parents or trashed=false")}`);
      return d ? json({ ok: true, files: (d as { files?: unknown[] }).files || [] }) : json({ ok: false, error: 'ni avtorizacije / napaka', authorized: false }, 401);
    }
    // Email: zadnje sporočila.
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
    // Calendar: prihodnji dogodki.
    if (req.method === 'GET' && url.pathname === '/api/google/calendar') {
      const mY = new Date().toISOString();
      const d = await googleGet(`/calendar/v3/calendars/primary/events?maxResults=8&singleEvents=true&orderBy=startTime&timeMin=${encodeURIComponent(mY)}&fields=items(summary,start)`);
      return d ? json({ ok: true, events: (d as { items?: unknown[] }).items || [] }) : json({ ok: false, error: 'ni avtorizacije / napaka', authorized: false }, 401);
    }
    // Status povezave.
    if (req.method === 'GET' && url.pathname === '/api/google/status') {
      const tok = await googleToken();
      return json({ ok: true, connected: !!tok });
    }

    return json({ ok: false, error: '404 · neznana pot: ' + url.pathname }, 404);
  },
});

console.log(`\n[command-center] živo na http://localhost:${server.port}/`);
console.log(`  /api/health · /api/ledger · /api/runs · /api/modules · /api/export · POST /api/run\n`);
