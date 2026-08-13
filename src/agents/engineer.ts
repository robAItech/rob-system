/**
 * agents/engineer.ts — inzenir.
 *
 * CIST REDUKTOR, enaka pravila kot pri arhitektu.
 *
 * Inzenir vzame zadnji odgovor modela in ga zapise na disk. Pomembna podrobnost je
 * `becauseOf`: zapis se pripise ODLOCITVI, zaradi katere je nastal, ne dogodku, ki ga
 * je sprozil. Brez tega bi `provenance()` vrnil zvezdo namesto verige in test verige
 * bi padel.
 */

import type { Agent, Command, Event, RunState } from '../hermes/types.ts';
import { idemKeyFor } from '../hermes/types.ts';

const ARTIFACT_PATH = 'out/RESULT.md';

export const engineer: Agent = {
  role: 'engineer',

  reduce(state: RunState, event: Event): Command[] {
    // Model je odgovoril: zapisi artefakt in zakljuci tek.
    if (event.kind === 'llm.responded') {
      // Idempotenca na ravni pomena: ce artefakt ze obstaja, ne pisi znova.
      if (state.artifacts.length > 0) return [];

      const lastDecision = state.decisions.at(-1);
      const because = lastDecision ? lastDecision.runSeq : event.runSeq;
      const content = state.lastLLM?.text ?? '';

      return [
        {
          type: 'fs.write',
          idemKey: idemKeyFor('engineer', event.runSeq, 0),
          becauseOf: because,
          path: ARTIFACT_PATH,
          content,
        },
        {
          type: 'run.complete',
          idemKey: idemKeyFor('engineer', event.runSeq, 1),
          becauseOf: because,
          reason: `artefakt ${ARTIFACT_PATH} zapisan`,
        },
      ];
    }

    // Model je odpovedal: tek se ne pretvarja, da je uspel.
    if (event.kind === 'llm.failed') {
      return [
        {
          type: 'run.declareStuck',
          idemKey: idemKeyFor('engineer', event.runSeq, 0),
          becauseOf: event.runSeq,
          reason: 'ponudnik LLM ni vrnil odgovora',
        },
      ];
    }

    return [];
  },
};
