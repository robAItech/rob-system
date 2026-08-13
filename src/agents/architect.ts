/**
 * agents/architect.ts — arhitekt.
 *
 * CIST REDUKTOR. Edini uvoz je hermes/types.ts, edina vhoda sta `RunState` in `Event`,
 * in v telesu ni nobene zmoznosti: ne `fetch`, ne `Bun`, ne `process`, ne `Date`,
 * ne `Math.random`. `tests/agent-purity.test.ts` to uveljavlja nad izvorno kodo.
 *
 * Naloga arhitekta v mejniku 1 je namenoma skromna: zabelezi odlocitev o tem, kaj
 * naj nastane, in vprasaj model. Odlocitev ni okras. Je clen v verigi, ki jo pozneje
 * vrne `provenance()`, in je eden od dveh dogodkov, ki stejeta kot napredek.
 */

import type { Agent, Command, Event, RunState } from '../hermes/types.ts';
import { idemKeyFor } from '../hermes/types.ts';

const SYSTEM_PROMPT = [
  'Si arhitekt v avtonomnem programerskem podjetju.',
  'Odgovori s kratkim, konkretnim nacrtom v Markdown obliki.',
  'Brez uvoda, brez opravicil, brez ponavljanja naloge.',
  'Zacni z naslovom prve stopnje in nadaljuj z oznacenim seznamom korakov.',
].join(' ');

export const architect: Agent = {
  role: 'architect',

  reduce(state: RunState, event: Event): Command[] {
    // Arhitekt se odzove samo na oddano nalogo. Vse drugo je tuja pristojnost.
    if (event.kind !== 'task.submitted') return [];
    if (state.decisions.length > 0) return [];

    const task = state.task ?? '';

    return [
      {
        type: 'decision.record',
        idemKey: idemKeyFor('architect', event.runSeq, 0),
        becauseOf: event.runSeq,
        question: 'Kaksen artefakt naj podjetje proizvede za to nalogo?',
        choice: 'eno datoteko Markdown na poti out/RESULT.md',
        rationale:
          'Mejnik 1 dokazuje podlago, ne bogastva izhoda. En resnicen artefakt na disku ' +
          'zadosca, da se dokaze veriga od naloge prek odlocitve do datoteke.',
      },
      {
        type: 'llm.complete',
        idemKey: idemKeyFor('architect', event.runSeq, 1),
        becauseOf: event.runSeq,
        ask: {
          attempt: 0,
          // Temperatura 0: determinizem na poti naprej je vreden vec kot pestrost.
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
