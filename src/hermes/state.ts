/**
 * hermes/state.ts — deterministicna zlozba dnevnika v stanje.
 *
 * `RunState` je poleg dogodka edini vhod agenta. Ker je izpeljan izkljucno iz
 * dnevnika, dva enaka dnevnika dasta dve enaki stanji, kar je pogoj za replay.
 */

import type {
  ArtifactWrittenPayload, DecisionMadePayload, Event, ExecRanPayload,
  LLMRespondedPayload, PlanSubmittedPayload, QaDecisionPayload, ReadObtainedPayload,
  RunState, TaskSubmittedPayload,
} from './types.ts';

export function foldState(runId: string, events: Event[]): RunState {
  const state: RunState = {
    runId,
    task: null,
    decisions: [],
    artifacts: [],
    lastLLM: null,
    stepsUsed: 0,
    eventsCount: events.length,
    finished: false,
    workplan: [],
    lastRead: null,
    lastExec: null,
    executionHealth: { exit: 0, signal: 0, timedout: 0, error: 0 },
    qaLast: null,
  };

  for (const e of events) {
    switch (e.kind) {
      case 'task.submitted':
        state.task = (e.payload as TaskSubmittedPayload).task;
        break;

      case 'decision.made': {
        const p = e.payload as DecisionMadePayload;
        state.decisions.push({
          runSeq: e.runSeq, question: p.question, choice: p.choice, rationale: p.rationale,
        });
        break;
      }

      case 'llm.responded':
        state.lastLLM = { runSeq: e.runSeq, text: (e.payload as LLMRespondedPayload).text };
        break;

      case 'artifact.written': {
        const p = e.payload as ArtifactWrittenPayload;
        state.artifacts.push({ path: p.path, sha256: p.sha256 });
        break;
      }

      // `stepsUsed` je izpeljan iz dnevnika, ne iz mutirane spremenljivke v zanki.
      // To je bil blokirni hrosc revizije 2 nacrta: proracun se ni nikoli premaknil.
      case 'step.completed':
        state.stepsUsed += 1;
        break;

      case 'run.completed':
      case 'run.stuck':
      case 'run.aborted':
        state.finished = true;
        break;

      // ─── produktni generator ────────────────────────────────────────────────

      case 'plan.submitted':
        state.workplan = (e.payload as PlanSubmittedPayload).steps;
        break;

      case 'read.obtained': {
        const p = e.payload as ReadObtainedPayload;
        state.lastRead = { runSeq: e.runSeq, path: p.path, content: p.content };
        break;
      }

      case 'exec.ran': {
        const p = e.payload as ExecRanPayload;
        state.lastExec = {
          runSeq: e.runSeq,
          kind: p.timedout ? 'timedout' : p.signal ? 'signal' : 'exit',
          code: p.exit,
          stdout: p.stdout,
          stderr: p.stderr,
        };
        if (p.timedout) state.executionHealth.timedout += 1;
        else if (p.signal) state.executionHealth.signal += 1;
        else state.executionHealth.exit += 1;
        break;
      }

      case 'exec.failed': {
        const p = e.payload as { reason: string };
        state.lastExec = {
          runSeq: e.runSeq, kind: 'error', code: null, stdout: '', stderr: p.reason,
        };
        state.executionHealth.error += 1;
        break;
      }

      case 'qa.decision': {
        const p = e.payload as QaDecisionPayload;
        state.qaLast = { runSeq: e.runSeq, action: p.action, which: p.which, reason: p.reason };
        break;
      }

      default:
        break;
    }
  }

  return state;
}
