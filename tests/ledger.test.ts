/**
 * tests/ledger.test.ts — podlaga: tabela, append, branje, fork, idempotenca.
 *
 * Ledger je edini lastnik stanja na disku. Ti testi dokazajo, da aredbanem
 * `createRun` ustreza dogodek `run.started`, da `append` dodeli monotono
 * `run_seq`, da `fork` podeduje prefiks z enakimi idemKeys in da se dvojni
 * zapis istega `idemKey` dvigne kot DuplicateIdemKeyError (NE pa razbije bazo).
 */

import { test, expect } from 'bun:test';
import { Ledger, DuplicateIdemKeyError } from '../src/hermes/ledger.ts';

function newLedger(): Ledger {
  // :memory: - vsaka instanca dobi svojo bazo, kar je to, kar test hoce.
  return new Ledger(':memory:', {
    idGen: (() => {
      let n = 0;
      return () => `run-${++n}`;
    })(),
  });
}

test('createRun doda run.started na runSeq 0 in shrani vrstni red', () => {
  const l = newLedger();
  const runId = l.createRun();
  const ev = l.read(runId);
  expect(ev).toHaveLength(1);
  expect(ev[0]).toMatchObject({ kind: 'run.started', runSeq: 0, actor: 'runner' });
  expect(l.getRun(runId)?.status).toBe('running');
  l.close();
});

test('append dodeli zaporedne run_seq in podpira branje po indeksu', () => {
  const l = newLedger();
  const runId = l.createRun();

  const a = l.append({
    runId, actor: 'human', kind: 'task.submitted', payload: { task: 'x' },
    causedByRunSeq: 0, idemKey: 'k:task',
  });
  const b = l.append({
    runId, actor: 'architect', kind: 'decision.made', payload: { question: 'q', choice: 'c', rationale: 'r' },
    causedByRunSeq: a.runSeq, idemKey: 'k:dec',
  });

  expect(a.runSeq).toBe(1);
  expect(b.runSeq).toBe(2);
  expect(b.causedByRunSeq).toBe(1);

  // read since runSeq pozitiven: vrne samo novejse.
  const since = l.read(runId, 1);
  expect(since.map((e) => e.runSeq)).toEqual([2]);
  l.close();
});

test('dvojna append istega idemKey v istem teku vrze DuplicateIdemKeyError', () => {
  const l = newLedger();
  const runId = l.createRun();

  l.append({
    runId, actor: 'human', kind: 'task.submitted', payload: { task: 'x' },
    causedByRunSeq: 0, idemKey: 'k:dup',
  });

  expect(() =>
    l.append({
      runId, actor: 'runner', kind: 'run.completed', payload: { reason: 'r' },
      causedByRunSeq: 0, idemKey: 'k:dup',
    }),
  ).toThrow(DuplicateIdemKeyError);
  l.close();
});

test('fork kopira prefiks dobesedno, ohrani idemKey in ponastavi steps/spend', () => {
  const l = newLedger();
  const runId = l.createRun();

  l.append({
    runId, actor: 'human', kind: 'task.submitted', payload: { task: 'x' },
    causedByRunSeq: 0, idemKey: 't:s1',
  });
  l.append({
    runId, actor: 'architect', kind: 'decision.made', payload: { question: 'q', choice: 'c', rationale: 'r' },
    causedByRunSeq: 1, idemKey: 'd:s2',
  });
  // Nekaj porabe zgolj za testiranje resetiranja.
  l.addSpendMicros(runId, 500);

  const forkId = l.fork(runId, 2);
  const forked = l.read(forkId);

  // Prefiks (run.started + task + decision) se prenese dobesedno.
  expect(forked.map((e) => e.kind)).toEqual(['run.started', 'task.submitted', 'decision.made']);
  expect(forked.map((e) => e.idemKey)).toEqual(['run.started', 't:s1', 'd:s2']);
  expect(forked.map((e) => e.causedByRunSeq)).toEqual([null, 0, 1]);

  // Poraba se ne podeduje, steps_used se zacne na 0.
  expect(l.getRun(forkId)?.spendMicros).toBe(0);
  expect(l.getRun(forkId)?.stepsUsed).toBe(0);
  expect(l.getRun(forkId)?.forkedFrom).toBe(runId);
  l.close();
});
