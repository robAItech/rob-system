/**
 * tests/provenance.test.ts — vzrocna veriga od naloge do artefakta.
 *
 * Preveri, da pravilen `causedByRunSeq` (ki ga nastavlja runner in agenti prek
 * `becauseOf`) vrne UREJENO verigo od korena do zapisa artefakta — in NE zvezde,
 * kjer bi vsak dogodek padal na isti koren.
 */

import { test, expect } from 'bun:test';
import { Ledger } from '../src/hermes/ledger.ts';
import { provenance } from '../src/hermes/provenance.ts';

test('provenance vrne verigo naloga -> odlocitev -> artefakt', () => {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun(); // runSeq 0 = run.started

  // 1: naloga
  l.append({
    runId, actor: 'human', kind: 'task.submitted', payload: { task: 'Izdelaj nacrt' },
    causedByRunSeq: 0, idemKey: 't:1',
  });
  // 2: odlocitev, ki jo je izpodbudilo task.submitted
  l.append({
    runId, actor: 'architect', kind: 'decision.made',
    payload: { question: 'Kaj narediti?', choice: 'eno datoteko', rationale: 'dokaz verige' },
    causedByRunSeq: 1, idemKey: 'd:2',
  });
  // 3: artefakt, napisan ZARADI odlocitve (ne sprozilnega dogodka)
  l.append({
    runId, actor: 'engineer', kind: 'artifact.written',
    payload: { path: 'out/RESULT.md', sha256: 'aa', bytes: 3 },
    causedByRunSeq: 2, idemKey: 'a:3',
  });

  const chain = provenance(l.read(runId), 'out/RESULT.md');

  expect(chain.map((e) => e.kind)).toEqual([
    'run.started',
    'task.submitted',
    'decision.made',
    'artifact.written',
  ]);
  // Veriga, ne zvezda: vsi cleni so razlicni.
  expect(new Set(chain.map((e) => e.runSeq)).size).toBe(4);
  l.close();
});

test('provenance za neobstojeci artefakt vrne prazno polje', () => {
  const l = new Ledger(':memory:', {
    idGen: (() => { let n = 0; return () => `run-${++n}`; })(),
  });
  const runId = l.createRun();
  l.append({
    runId, actor: 'human', kind: 'task.submitted', payload: { task: 'x' },
    causedByRunSeq: 0, idemKey: 't:1',
  });
  expect(provenance(l.read(runId), 'out/NI_tam.md')).toEqual([]);
  l.close();
});
