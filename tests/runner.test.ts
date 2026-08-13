/**
 * tests/runner.test.ts — end-to-end: tek cez zanko runnerja, od naloge do artefakta.
 *
 * Uporablja REALNE agente (architect + engineer) in REALNI Ledger ter Runner,
 * le zunanje storitve (LLM, spomin, disk) so nadomescene z laznimi. To dokazuje,
 * da skelet tece: arhitekt se odzove na nalogo, inzenir zapise artefakt in
 * zakljuci tek.
 */

import { test, expect } from 'bun:test';
import { Ledger } from '../src/hermes/ledger.ts';
import { Runner, type FsLike } from '../src/hermes/runner.ts';
import { provenance } from '../src/hermes/provenance.ts';
import { architect } from '../src/agents/architect.ts';
import { engineer } from '../src/agents/engineer.ts';
import type { CompletionRequest, CompletionResult, LLMProvider, MemoryHit, MemoryStore } from '../src/hermes/types.ts';

/** Fake LLM: zmeraj vrne kratek, napovedljiv odgovor. Nobenega omrezja. */
class FakeLLM implements LLMProvider {
  readonly name = 'fake';
  liveCalls = 0;
  async complete(req: CompletionRequest): Promise<CompletionResult> {
    this.liveCalls += 1;
    void req;
    return {
      text: '# Nacrt\n\n1. Gre na out/RESULT.md',
      usage: { promptTokens: 10, completionTokens: 5, usdMicros: 0 },
      cached: false,
    };
  }
}

/** Fake spomin: shranjuje v Map. Brez SQL in brez omrezja. */
class FakeMemory implements MemoryStore {
  private readonly store = new Map<string, string>();
  async remember(entry: { key: string; text: string; tags?: string[] }): Promise<void> {
    this.store.set(entry.key, entry.text);
  }
  async recall(query: string, _limit?: number): Promise<MemoryHit[]> {
    const hits: MemoryHit[] = [];
    for (const [key, text] of this.store) {
      if (text.toLowerCase().includes(query.toLowerCase())) hits.push({ key, text, score: 1 });
    }
    return hits;
  }
  async health(): Promise<{ ok: boolean; backend: string }> {
    return { ok: true, backend: 'fake' };
  }
}

/** Fake disk: pise v Map in vrne bajte. */
class FakeFs implements FsLike {
  writes = new Map<string, string>();
  async write(path: string, content: string): Promise<Uint8Array> {
    this.writes.set(path, content);
    return new TextEncoder().encode(content);
  }
  async read(path: string): Promise<Uint8Array> {
    const content = this.writes.get(path);
    if (content === undefined) throw new Error('no such file: ' + path);
    return new TextEncoder().encode(content);
  }
}

function live(): { r: Runner; l: Ledger; llm: FakeLLM; fs: FakeFs } {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun();
  const llm = new FakeLLM();
  const fs = new FakeFs();
  const r = Runner.forRun(runId, {
    ledger: l,
    agents: [architect, engineer],
    llm,
    provider: 'fake',
    model: 'fake-model',
    memory: new FakeMemory(),
    fs,
  });
  return { r, l, llm, fs };
}

test('celoten tek od naloge do artefakta in provenience', async () => {
  const { r, l, fs } = live();
  const out = await r.run('Izdelaj nacrt sistema');

  expect(out.status).toBe('completed');
  expect(out.artifactPath).toBe('out/RESULT.md');
  expect(out.stepsUsed).toBeGreaterThan(0);

  // Artefakt res obstaja v laznem disku in ni prazen.
  expect(fs.writes.get('out/RESULT.md')).toContain('# Nacrt');

  // Providenca je VERIGA do artefakta, ne samo artefakt.
  const chain = provenance(l.read(out.runId), 'out/RESULT.md');
  const kinds = chain.map((e) => e.kind);
  expect(kinds).toContain('task.submitted');
  expect(kinds[kinds.length - 1]).toBe('artifact.written');
  // Vsi cleni so razlicni: to NI zvezda.
  expect(new Set(chain.map((e) => e.runSeq)).size).toBe(chain.length);
});

test('replay: zagon istega teka ne ponovi omreznih klicev', async () => {
  const { r, l, llm } = live();
  const first = await r.run('Zahtevaj rezultat');
  const callsAfterFirst = llm.liveCalls;

  // Drugi zagon istega runId: runner preskoci ze nastale rezultate in ne
  // vraca "running", ki se nikoli ne konca.
  const second = await r.run('Zahtevaj rezultat');
  expect(second.status).toBe('completed');
  // Po replayu liveCalls ne sme narasti (vsak klic agenta se bere iz dnevnika).
  // Ker agent reduzira enkrat za llm, drugi zagon ne sme dodati novega klica.
  expect(llm.liveCalls).toBe(callsAfterFirst);
  void l;
});
