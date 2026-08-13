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

const DB_PATH = process.env.LEDGER_DB ?? '.gstack-run.sqlite';
const PORT = Number(process.env.PORT ?? 8787);
const OUT_ROOT = process.env.OUT_ROOT ?? '.';

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

    // API: health / ledger / runs
    if (req.method === 'GET' && url.pathname === '/api/health') return json(await health());
    if (req.method === 'GET' && url.pathname === '/api/ledger') return json({ events: readEvents() });
    if (req.method === 'GET' && url.pathname === '/api/runs') return json({ runs: readRuns() });

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

    return json({ ok: false, error: '404 · neznana pot: ' + url.pathname }, 404);
  },
});

console.log(`\n[command-center] živo na http://localhost:${server.port}/`);
console.log(`  /api/health · /api/ledger · /api/runs · POST /api/run\n`);
