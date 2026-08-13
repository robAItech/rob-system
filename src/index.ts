/**
 * src/index.ts — vstopna tocka (CLI) za mejnik 1.
 *
 * Sestavi celoten sistem iz gradnikov in zazene EN tek: poda nalogo, pusti
 * arhitektu in inzenirju, da delujeta skozi runner, in izpise rezultat skupaj
 * s provienenco (vzrocno verigo) do koncnega artefakta.
 *
 * Zagon:
 *   bun install            # natsanavi odvisnosti (samo @types/bun)
 *   bun run src/index.ts   # lokalen tek brez stroskov, ce je Ollama dosegljiva
 *
 * Nalogo je mogoce podati prek ukazne vrstice:
 *   bun run src/index.ts "Izdelaj primer dokumentacije hermes runnerja"
 *
 * Najprej pazi, da LLM_PROVIDER kaze na dosegljiv vticnik (glej .env.example).
 */

import { planner } from './agents/planner.ts';
import { builder } from './agents/builder.ts';
import { qa } from './agents/qa.ts';
import { screenshot } from './agents/screenshot.ts';
import { Ledger } from './hermes/ledger.ts';
import { Runner, type FsLike } from './hermes/runner.ts';
import { provenance } from './hermes/provenance.ts';
import type { MemoryStore } from './hermes/types.ts';
import { OpenAICompatibleProvider } from './bridges/openai-compatible.ts';
import { LLMCache } from './bridges/cache.ts';
import { resolveProvider } from './bridges/provider.ts';
import { SqliteMemoryStore } from './memory/sqlite-store.ts';
import { BunExec } from './bridges/exec.ts';

/** Privzeta pot do podatkovne baze. Usklajena s .env.example (LEDGER_DB). */
const DB_PATH = process.env.LEDGER_DB ?? '.gstack-run.sqlite';

const DEFAULT_TASK =
  'Izdelaj kratek primer dokumentacije o tem, kako je run tega podjetja dosegel rezultat.';

/**
 * Resnicni disk. `root` (od --out) postane koren za izhodne datoteke,
 * da `--out demo` res napise v demo/ in ne v tekocem imeniku.
 */
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

function usage(): void {
  console.error(
    `Poraba: bun run src/index.ts [naloga] [flags]\n` +
      `  --kind full|dashboard   nabor agentov (privzeto full)\n` +
      `  --out <cesta>           koren za izhodne datoteke (privzeto '.')\n` +
      `  --no-verify             izpusti izvajanje programov (razvoj)\n` +
      `  --dry-run               uporabi vgrajeni 'fake' provider (demo, brez omrezja)\n` +
      `\nPrimer: bun run src/index.ts "Izdelaj dashboard porabe" --kind dashboard`,
  );
}

async function main(): Promise<void> {
  const args = process.argv.slice(2);

  // ── Flag parsing (enostaven, brez dependency).
  const flags = { kind: 'full' as 'full' | 'dashboard', out: '.', noVerify: false, dryRun: false };
  const taskArgs: string[] = [];
  for (let i = 0; i < args.length; i++) {
    const a = args[i]!;
    if (a === '--kind') { flags.kind = (args[++i] as 'full' | 'dashboard') ?? 'full'; continue; }
    if (a === '--out') { flags.out = args[++i] ?? '.'; continue; }
    if (a === '--no-verify') { flags.noVerify = true; continue; }
    if (a === '--dry-run') { flags.dryRun = true; continue; }
    if (a === '--help' || a === '-h') { usage(); return; }
    taskArgs.push(a);
  }

  // 1. Ponudnik LLM. --dry-run uporabi fake (brez omrezja); obicajno iz okolja.
  const p = flags.dryRun
    ? { name: 'fake', baseUrl: 'http://127.0.0.1:1/v1', apiKey: null, model: 'fake-model' } as const
    : resolveProvider(process.env);

  // 2. Ledger: edini lastnik stanja na disku.
  const ledger = new Ledger(DB_PATH);
  // 3. Predpomnilnik odgovorov (tabela llm_cache v isti bazi).
  const cache = new LLMCache(ledger.db);
  // 4. Vticnik LLM.
  const llm = flags.dryRun
    ? fakeProvider()
    : new OpenAICompatibleProvider(p.name, { baseUrl: p.baseUrl, apiKey: p.apiKey, cache });
  // 5. Spomin.
  const memory: MemoryStore = new SqliteMemoryStore(ledger.db);

  // 6. Ustvari tek. runId potrebuje Runner (vezan na en tek).
  const runId = ledger.createRun({ note: `produktni generator (${flags.kind})` });

  // 7. Runner z resnicnim izvajalno (razen --no-verify).
  const runner = Runner.forRun(runId, {
    ledger,
    agents: flags.kind === 'dashboard'
      ? [planner, builder, qa]
      : [planner, builder, qa, screenshot],
    llm,
    provider: p.name,
    model: p.model,
    memory,
    fs: new Disk(flags.out),
    exec: new BunExec(),
    execCwdRoot: flags.out,
    execDisabled: flags.noVerify,
  });

  // 8. Pozeni tek z nalogo.
  const task = taskArgs.join(' ') || DEFAULT_TASK;
  console.log(`\n[tek] ${flags.kind} · provider=${p.name} · verify=${flags.noVerify ? 'izklopljeno' : 'vklopljeno'}`);
  const out = await runner.run(task);

  // 9. Povzetek + provienerica za vsak artefakt.
  const events = ledger.read(runId);
  console.log('\n=== Rezultat teka ===');
  console.log(`status:   ${out.status}`);
  console.log(`razlog:   ${out.reason}`);
  console.log(`koraki:   ${out.stepsUsed} · poraba: ${out.spendMicros} mikrodolarjev`);
  if (out.artifactPaths.length === 0) console.log('artefakt: (ni nastal)');

  for (const path of out.artifactPaths) {
    console.log(`\n── artefakt: ${path}`);
    const chain = provenance(events, path);
    if (chain.length === 0) { console.log('   (veriga ni dolocljiva)'); continue; }
    for (const e of chain) {
      const payload = (e.payload && typeof e.payload === 'object' ? e.payload : {}) as Record<string, unknown>;
      const label =
        e.kind === 'task.submitted' ? `naloga`
        : e.kind === 'decision.made' ? `odlocitev`
        : e.kind === 'llm.responded' ? `odgovor modela`
        : e.kind === 'artifact.written' ? `artefakt`
        : e.kind;
      console.log(`   [${e.runSeq}] ${e.actor} · ${label}`);
    }
  }

  ledger.close();
}

/** Fake provider za --dry-run: vrne eno @file datoteko (demo brez omrezja). */
function fakeProvider(): {
  name: string;
  complete(): Promise<{ text: string; usage: { promptTokens: number; completionTokens: number; usdMicros: number }; cached: boolean }>;
} {
  return {
    name: 'fake',
    async complete() {
      return {
        text:
          '@file out/PLAN.md\n```md\n# Demo plan\n```\n' +
          '@file app/demo.txt\n```\nPozdrav svet\n```',
        usage: { promptTokens: 8, completionTokens: 3, usdMicros: 0 },
        cached: false,
      };
    },
  };
}

main().catch((err) => {
  console.error(`\n[NAPAKA] ${String(err instanceof Error ? err.message : err)}`);
  process.exitCode = 1;
});
