/**
 * agents/qa.ts — tester v povratni zanki: poganja preverjanje in odloca.
 *
 * CIST REDUKTOR. QA ne izvaja nicesar sam; ko vidi:
 *   - `qa.decision` action='verify' (od builderja): izda `cmd.exec` z ukazom
 *     preverjanja za naslednji delovni korak iz `state.workplan`;
 *   - `exec.ran`: razume izhod in odloca —
 *       exit===0          -> `complete` in `run.complete`;
 *       exit!==0          -> `retry` z NOVIM exec (idempotentna razlika);
 *       prevec poskusov   -> `run.declareStuck` (meja maxFixPasses).
 *
 * Idempotenca: vsak retry ima lasten `idemKey`, ki vkljucuje attempt (= stevilo
 * ze izvedenih izvedb iz `state.executionHealth`). Zato replay ne ponovi in se
 * vsak poskus zanke vidi kot nov dogodek.
 */

import type { Agent, Command, Event, RunState } from '../hermes/types.ts';
import { idemKeyFor } from '../hermes/types.ts';
import { LIMITS } from '../hermes/limits.ts';

/** Naslednji delovni korak, ki se še ni dokoncal (prvi v orderju). */
function nextTodo(state: RunState) {
  return state.workplan.find((s) => s.status === 'todo' || s.status === 'doing');
}

/** Koliko poskusov je bilo ze izvedenih na tem koraku (za determinizem idemKey). */
function attempts(state: RunState): number {
  return state.executionHealth.exit + state.executionHealth.error;
}

/**
 * Ukaz preverjanja za korak. Ce workplan korak ni nastavil preverjanja, ga QA
 * PRESKOCI — ni treba siliti praznega ukaza. Vrne null (no-op) ce ni verify.
 */
export function verifyArgv(step: { verify?: string[] }): string[] | null {
  return step.verify?.length ? step.verify : null;
}

export const qa: Agent = {
  role: 'qa',

  reduce(state: RunState, event: Event): Command[] {
    // ── model ni odgovoril: ni gradnje, ki bi jo bilo mogoce preveriti.
    if (event.kind === 'llm.failed') {
      return [
        {
          type: 'run.declareStuck',
          idemKey: idemKeyFor('qa', event.runSeq, 0),
          becauseOf: event.runSeq,
          reason: `model ni odgovoril (${(event.payload as { code?: string }).code ?? '?'})`,
        },
      ];
    }

    // ── builder je koncal generiranje; pozeni preverjanje za naslednji korak.
    if (event.kind === 'qa.decision') {
      const p = event.payload as { action: string };
      if (p.action !== 'verify') return [];

      const step = nextTodo(state);
      if (!step) return []; // ni vec dela.

      const verify = verifyArgv(step);
      // Korak brez izrecnega preverjanja: preskoci izvedbo in ga obravnavaj kot done.
      if (!verify) {
        const at = attempts(state);
        return [
          { type: 'qa.decide', idemKey: idemKeyFor('qa', event.runSeq, at), becauseOf: event.runSeq, action: 'complete', which: step.id, reason: 'ni preverjanja' },
          { type: 'run.complete', idemKey: idemKeyFor('qa', event.runSeq, at + 1), becauseOf: event.runSeq, reason: 'vsi koraki preverjeni' },
        ];
      }

      return [
        {
          type: 'cmd.exec',
          idemKey: idemKeyFor('qa', event.runSeq, attempts(state)),
          becauseOf: event.runSeq,
          argv: verify,
        },
      ];
    }

    // ── izid izvajanja se je zgodil; odloci, kaj naprej.
    if (event.kind === 'exec.ran' && state.lastExec) {
      const step = nextTodo(state);
      if (!step) return [];

      const at = attempts(state); // vkljucuje pravkar videni izid
      const ok = state.lastExec.kind === 'exit' && state.lastExec.code === 0;
      if (ok) {
        return [
          { type: 'qa.decide', idemKey: idemKeyFor('qa', event.runSeq, at), becauseOf: event.runSeq, action: 'complete', which: step.id, reason: 'preverjanje uspesno' },
          { type: 'run.complete', idemKey: idemKeyFor('qa', event.runSeq, at + 1), becauseOf: event.runSeq, reason: 'vsi koraki preverjeni' },
        ];
      }
      return retryOrStuck(state, event.runSeq, step, at);
    }

    // ── izjema v jedru (exec.failed) — enako kot neuspeh na koraku.
    if (event.kind === 'exec.failed') {
      const step = nextTodo(state);
      if (!step) return [];
      return retryOrStuck(state, event.runSeq, step, attempts(state));
    }

    return [];
  },
};

/** Neuspeh (exit!=0, timeout ali error): ce je prostora, poskusi znova; drugace stuck. */
function retryOrStuck(
  _state: RunState,
  triggerRunSeq: number,
  step: { id: string; verify?: string[] },
  at: number,
): Command[] {
  if (at <= LIMITS.maxFixPasses) {
    // Do retry-ja pride samo, ce je bil verify ze uporabljen (izvajali smo ga);
    // fallback na prazno se tu ne razmnozi, ker preskocenih korakov ne izvajamo.
    const argv = verifyArgv(step) ?? [];
    return [
      {
        type: 'cmd.exec',
        idemKey: idemKeyFor('qa', triggerRunSeq, at + 1),
        becauseOf: triggerRunSeq,
        argv,
      },
    ];
  }
  return [
    {
      type: 'run.declareStuck',
      idemKey: idemKeyFor('qa', triggerRunSeq, at + 1),
      becauseOf: triggerRunSeq,
      reason: `preverjanje koraka '${step.id}' ne uspe po ${at} poskusih`,
    },
  ];
}
