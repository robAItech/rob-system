/**
 * tests/prodg.test.ts — e2e za produktni generator (M1..M4).
 *
 * Uporablja REALNE agente in REALNI Runner, le zunanje storitve so laznih
 * (FakeLLM, FakeFs, FakeExec, FakeMemory). Skupaj z tests/runner.test.ts
 * dokazuje, da se celoten skelet + produktni generator vrti brez potrebe
 * po dejanskem omrezju ali modelu.
 */

import { test, expect } from 'bun:test';
import { Ledger } from '../src/hermes/ledger.ts';
import { Runner, type FsLike } from '../src/hermes/runner.ts';
import { provenance } from '../src/hermes/provenance.ts';
import { planner } from '../src/agents/planner.ts';
import { builder } from '../src/agents/builder.ts';
import { qa } from '../src/agents/qa.ts';
import type {
  CompletionRequest, CompletionResult, LLMProvider, MemoryHit, MemoryStore,
} from '../src/hermes/types.ts';
import type { ExecLike, ExecResult, ExecSpec } from '../src/bridges/exec.ts';

/** Fake LLM, ki vrne strukturo `@file` (za M2). */
class FakeLLM implements LLMProvider {
  readonly name = 'fake';
  liveCalls = 0;
  async complete(req: CompletionRequest): Promise<CompletionResult> {
    this.liveCalls += 1;
    void req;
    return {
      text:
        '@file out/plan.md\n```md\n# Nacrt\n```\n' +
        '@file app/main.ts\n```ts\nexport const x = 1;\n```',
      usage: { promptTokens: 9, completionTokens: 4, usdMicros: 0 },
      cached: false,
    };
  }
}

/** Fake spomin. */
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
  async health() {
    return { ok: true, backend: 'fake' };
  }
}

/** Fake disk. */
class FakeFs implements FsLike {
  writes = new Map<string, string>();
  async write(path: string, content: string): Promise<Uint8Array> {
    this.writes.set(path, content);
    return new TextEncoder().encode(content);
  }
  async read(path: string): Promise<Uint8Array> {
    const c = this.writes.get(path);
    if (c === undefined) throw new Error('no such file: ' + path);
    return new TextEncoder().encode(c);
  }
}

/** Skonfigurabilen fake exec: vraca vnaprej doloceno zaporedje; padajoce -> code:1. */
class FakeExec implements ExecLike {
  timer = 0;
  defaultCode = 0;                       // izid, ko zaporedje izpraznimo
  sequence: Array<Partial<ExecResult>> = [];
  liveExecs = 0;
  calls: string[][] = [];

  async run(spec: ExecSpec): Promise<ExecResult> {
    this.liveExecs += 1;
    this.calls.push(spec.argv);
    const next = this.sequence[this.timer];
    this.timer += 1;
    const base: ExecResult = {
      code: this.defaultCode, signal: null, timedout: false, stdout: '', stderr: '',
    };
    return next ? { ...base, ...next } : base;
  }

  queue(...r: Array<Partial<ExecResult>>) {
    this.sequence.push(...r);
  }
}

// Minimalni testni agent, ki ob nalogi izda en `cmd.exec` in ob uspehu zakljuci (M1 test).
import type { Agent, Command, Event, RunState } from '../src/hermes/types.ts';
const execAgent: Agent = {
  role: 'qa',
  reduce(state: RunState, event: Event): Command[] {
    // Vhodni nalogi: izdaj en cmd.exec.
    if (event.kind === 'task.submitted' && !state.lastExec) {
      return [{ type: 'cmd.exec', argv: ['echo', 'hello'], idemKey: 'qa:echo' }];
    }
    // Rezultatu izvedbe: zakljuci ob uspehu, stuck ob napaki.
    if (event.kind === 'exec.ran' && state.lastExec) {
      if (state.lastExec.kind === 'exit' && state.lastExec.code === 0) {
        return [{ type: 'run.complete', reason: 'echo ok', idemKey: 'qa:done' }];
      }
      return [{ type: 'run.declareStuck', reason: 'exec ni uspel', idemKey: 'qa:stuck' }];
    }
    return [];
  },
};

test('M1: cmd.exec izvede, zabelezi exec.ran in se ne izvede pri replayu', async () => {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun();
  const exec = new FakeExec();
  exec.queue({ code: 0, stdout: 'hello\n' });
  const rr = Runner.forRun(runId, {
    ledger: l, agents: [execAgent], llm: new FakeLLM(), provider: 'fake', model: 'm',
    memory: new FakeMemory(), fs: new FakeFs(), exec,
  });

  const first = await rr.run('pozeni eno');
  expect(first.status).toBe('completed');
  const execCallsAfterFirst = exec.liveExecs;
  expect(execCallsAfterFirst).toBe(1);

  // V dnevniku je exec.ran.
  const evs = l.read(runId);
  expect(evs.some((e) => e.kind === 'exec.ran')).toBe(true);

  // Replay: isti runId — rezultat ze obstaja, exec se ne zazene ponovno.
  const second = await rr.run('pozeni eno');
  expect(second.status).toBe('completed');
  expect(exec.liveExecs).toBe(execCallsAfterFirst);
  expect(exec.calls).toHaveLength(1);
});

// M2: trivialni finisher — ob qa.decision (verify) zakljuci tek. Pravi qa pride v M3.
const finisher: Agent = {
  role: 'qa',
  reduce(_state: RunState, event: Event): Command[] {
    if (event.kind === 'qa.decision') {
      return [{ type: 'run.complete', reason: 'generirano', idemKey: 'fin:done' }];
    }
    return [];
  },
};

test('M2: planner + builder razreze @file na vec fs.write (artifactPaths >= 2)', async () => {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun();
  const fs = new FakeFs();
  const rr = Runner.forRun(runId, {
    ledger: l,
    agents: [planner, builder, finisher],
    llm: new FakeLLM(), provider: 'fake', model: 'm',
    memory: new FakeMemory(), fs,
  });

  const out = await rr.run('Izdelaj plan in aplikacijo');
  expect(out.status).toBe('completed');

  // Vsaj dva artefakta (out/plan.md + app/main.ts) - FakeLLM vrača 2 @file bloka.
  expect(out.artifactPaths.length).toBeGreaterThanOrEqual(2);
  expect(fs.writes.has('out/plan.md')).toBe(true);
  expect(fs.writes.has('app/main.ts')).toBe(true);

  // Providenca do vsakega artefakta je veriga (naloga -> odlocitev -> artefakt).
  for (const p of out.artifactPaths) {
    const chain = provenance(l.read(runId), p);
    expect(chain.map((e) => e.kind)).toContain('decision.made');
    expect(chain[chain.length - 1]?.kind).toBe('artifact.written');
    expect(new Set(chain.map((e) => e.runSeq)).size).toBe(chain.length);
  }
});

test('M3: QA brez izrecnega verify-ja preskoci in zakljuci tek', async () => {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun();
  const exec = new FakeExec();               // defaultCode 0 -> ce bi se izvajal, ok.
  const rr = Runner.forRun(runId, {
    ledger: l, agents: [planner, builder, qa],
    llm: new FakeLLM(), provider: 'fake', model: 'm',
    memory: new FakeMemory(), fs: new FakeFs(), exec,
  });

  const out = await rr.run('Izdelaj dashboard');
  expect(out.status).toBe('completed');
  // Seed korak nima izrecnega verify -> QA preskoči izvedbo (0 klicov).
  expect(exec.calls.length).toBe(0);
  expect(l.read(runId).some((e) => e.kind === 'run.completed')).toBe(true);
});

// Inline agent, ki na nalogi poganja `cmd.exec(['false'])` (vedno pade) in se
// vrti z retry-ji — dokazuje povratno zanko neuspeha -> stuck neodv. od planner.
const failLoop: Agent = {
  role: 'qa',
  reduce(_state: RunState, event: Event): Command[] {
    if (event.kind === 'llm.failed') {
      return [{ type: 'run.declareStuck', idemKey: 'fl:llmfail', reason: 'model padel' }];
    }
    if (event.kind === 'exec.ran' && _state.lastExec && _state.lastExec.code !== 0) {
      // Ta ima verify s kodom !=0: retry z novim idemKey, do maxFixPasses+1.
      const at = _state.executionHealth.exit;
      if (at >= 4) {
        return [{ type: 'run.declareStuck', idemKey: 'fl:stuck', reason: `neuspeh po ${at}` }];
      }
      return [{ type: 'cmd.exec', argv: ['false'], idemKey: `fl:retry:${at}` }];
    }
    if (event.kind === 'exec.ran' && _state.lastExec && _state.lastExec.code === 0) {
      return [{ type: 'run.complete', idemKey: 'fl:done', reason: 'ok' }];
    }
    if (event.kind === 'task.submitted' && !_state.lastExec) {
      return [{ type: 'cmd.exec', argv: ['false'], idemKey: 'fl:first' }];
    }
    return [];
  },
};

test('M3: vztrajen neuspeh izvajanja vodi v stuck po poskusih', async () => {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun();
  const exec = new FakeExec();
  exec.defaultCode = 1;                       // vsak `false` se izvaja in pade.
  const rr = Runner.forRun(runId, {
    ledger: l, agents: [failLoop],
    llm: new FakeLLM(), provider: 'fake', model: 'm',
    memory: new FakeMemory(), fs: new FakeFs(), exec,
  });

  const out = await rr.run('test');
  expect(out.status).toBe('stuck');
  expect(exec.calls.length).toBeGreaterThan(3);   // veckratni retry.
  expect(l.read(runId).some((e) => e.kind === 'run.stuck')).toBe(true);
});
