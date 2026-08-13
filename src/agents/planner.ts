/**
 * agents/planner.ts — orkestrator produktnega generatorja.
 *
 * CIST REDUKTOR (glej prava pri arhitektu). Na oddano nalogo:
 *   1. zaznamuje odlocitev (kaj proizvesti),
 *   2. posreduje workplan (seznam korakov), da imajo build/qa kaj poganjati,
 *   3. naroci LLM, da vrne vsebino v strukturi `@file <relpath>` — builder jo
 *      potem razrez in zapise na vec poti.
 *
 * Workplan je namenoma SEED (en korak) in ne izpeljan iz naloge z LLM-jem:
 * dejansko razclenitev del kode artefaktov prevzame `@file` razrez v builderju.
 * V zahtevnejši vosi bi planner vsak korak verificiral z LLM-om; tukaj je to
 * stabilna izpeljava, da se zanka ne zaleti.
 */

import type { Agent, Command, Event, RunState } from '../hermes/types.ts';
import { idemKeyFor } from '../hermes/types.ts';

const SYSTEM_PROMPT = [
  'Si orkestrator programerskega podjetja.',
  'Izpolni nalogo s konkretnimi datotekami.',
  'Vsako izhodno datoteko podaj v natancnem formatu:',
  '@file <relativna_posix_pot>',
  '```<jezik>',
  '<vsebina>',
  '```',
  'Prvi blok naj bo @file out/PLAN.md s kratkim nacrtom, nadaljnji pojljubni artefakti.',
  'Brez uvoda, brez komentarja zunaj blokov.',
].join(' ');

/**
 * En sam seed korak. `verify` je prazna -> QA ga preskoci in obravnava kot done
 * (generacija ni stran-specificna; v dejanskem produktnem delu bi planner vpise
 * pravi build/test ukaz, npr. ['bun','test']).
 */
const SEED_STEP = {
  id: 'generate',
  label: 'generiraj artefakte',
  status: 'todo' as const,
  verify: [] as string[],
};

export const planner: Agent = {
  role: 'planner',

  reduce(state: RunState, event: Event): Command[] {
    if (event.kind !== 'task.submitted') return [];
    if (state.workplan.length > 0) return [];

    const task = state.task ?? '';
    const runSeq = event.runSeq;

    return [
      {
        type: 'decision.record',
        idemKey: idemKeyFor('planner', runSeq, 0),
        becauseOf: runSeq,
        question: 'Kako razcleniti nalogo na artefakte?',
        choice: 'plan + vsebino prek @file datotek',
        rationale:
          'Produktni generator napaja strukturo @file: planner posreduje workplan, ' +
          'builder razreze vsebino na poti, qa poganja preverjanje.',
      },
      {
        type: 'plan.record',
        idemKey: idemKeyFor('planner', runSeq, 1),
        becauseOf: runSeq,
        steps: [SEED_STEP],
      },
      {
        type: 'llm.complete',
        idemKey: idemKeyFor('planner', runSeq, 2),
        becauseOf: runSeq,
        ask: {
          attempt: 0,
          temperature: 0,
          messages: [
            { role: 'system', content: SYSTEM_PROMPT },
            { role: 'user', content: task },
          ],
        },
      },
    ];
  },
};
