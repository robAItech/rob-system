/**
 * hermes/ledger.ts — podlaga celotnega sistema.
 *
 * Ledger je edini lastnik identitete teka, zaporedja in razcepa. Nihce drug ne
 * odloca, kaj se je zgodilo. Vsi vticniki pisejo skozi runner, ki pise sem.
 */

import { Database } from 'bun:sqlite';
import { applyPragmas, migrate } from './schema.ts';
import type { Actor, Event, EventKind, NewEvent, RunMeta, RunStatus } from './types.ts';
import { LIMITS } from './limits.ts';

interface EventRow {
  seq: number;
  run_id: string;
  run_seq: number;
  ts: string;
  actor: string;
  kind: string;
  payload: string;
  caused_by_run_seq: number | null;
  idem_key: string;
}

const toEvent = (r: EventRow): Event => ({
  seq: r.seq,
  runId: r.run_id,
  runSeq: r.run_seq,
  ts: r.ts,
  actor: r.actor as Actor,
  kind: r.kind as EventKind,
  payload: JSON.parse(r.payload) as unknown,
  causedByRunSeq: r.caused_by_run_seq,
  idemKey: r.idem_key,
});

/** Napaka ob poskusu dvojnega zapisa istega ukaza. Runner jo obravnava kot "ze narejeno". */
export class DuplicateIdemKeyError extends Error {
  constructor(runId: string, idemKey: string) {
    super(`dogodek z idemKey '${idemKey}' v teku '${runId}' ze obstaja`);
    this.name = 'DuplicateIdemKeyError';
  }
}

export interface LedgerOptions {
  /** Injekcija za teste; privzeto `crypto.randomUUID()`. */
  idGen?: () => string;
  /** Injekcija za teste; privzeto stenska ura. `ts` ni del `hashEvents`. */
  clock?: () => string;
}

export class Ledger {
  readonly db: Database;
  private readonly idGen: () => string;
  private readonly clock: () => string;

  constructor(path: string, opts: LedgerOptions = {}) {
    this.db = new Database(path);
    applyPragmas(this.db);
    migrate(this.db);
    this.idGen = opts.idGen ?? (() => crypto.randomUUID());
    this.clock = opts.clock ?? (() => new Date().toISOString());
  }

  /** Ustvari tek IN atomarno doda `run.started` na runSeq 0. */
  createRun(meta: RunMeta = {}): string {
    const runId = this.idGen();
    const budget = meta.stepBudget ?? LIMITS.stepBudget;
    const now = this.clock();

    this.db.transaction(() => {
      this.db.run(
        `INSERT INTO runs (run_id, created_at, forked_from, forked_at_run_seq,
                           status, step_budget, steps_used, spend_micros)
         VALUES (?, ?, NULL, NULL, 'running', ?, 0, 0)`,
        [runId, now, budget],
      );
      // Payload je namenoma prazen objekt: karkoli drugega bi zaneslo nedeterminizem
      // v prvi dogodek in s tem v `hashEvents`.
      this.insertEvent(runId, 0, now, 'runner', 'run.started', {}, null, 'run.started');
    })();

    return runId;
  }

  /** run_seq = MAX(run_seq)+1 za ta tek, vse znotraj ene transakcije. */
  append(e: NewEvent): Event {
    const now = this.clock();

    const inserted = this.db.transaction(() => {
      const row = this.db
        .query<{ n: number | null }, [string]>(
          'SELECT MAX(run_seq) AS n FROM events WHERE run_id = ?',
        )
        .get(e.runId);
      const nextRunSeq = (row?.n ?? -1) + 1;

      if (nextRunSeq >= LIMITS.maxEventsPerRun) {
        throw new Error(
          `tek '${e.runId}' je presegel maxEventsPerRun (${LIMITS.maxEventsPerRun})`,
        );
      }

      return this.insertEvent(
        e.runId, nextRunSeq, now, e.actor, e.kind, e.payload, e.causedByRunSeq, e.idemKey,
      );
    })();

    return inserted;
  }

  private insertEvent(
    runId: string,
    runSeq: number,
    ts: string,
    actor: Actor,
    kind: EventKind,
    payload: unknown,
    causedByRunSeq: number | null,
    idemKey: string,
  ): Event {
    try {
      this.db.run(
        `INSERT INTO events (run_id, run_seq, ts, actor, kind, payload, caused_by_run_seq, idem_key)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [runId, runSeq, ts, actor, kind, JSON.stringify(payload), causedByRunSeq, idemKey],
      );
    } catch (err) {
      if (String(err).includes('UNIQUE') && String(err).includes('idem_key')) {
        throw new DuplicateIdemKeyError(runId, idemKey);
      }
      throw err;
    }

    const row = this.db
      .query<EventRow, [string, number]>(
        'SELECT * FROM events WHERE run_id = ? AND run_seq = ?',
      )
      .get(runId, runSeq);
    if (!row) throw new Error('vstavljenega dogodka ni bilo mogoce prebrati nazaj');
    return toEvent(row);
  }

  /** Vedno urejeno po `run_seq`. Po forku je globalni `seq` prepleten z drugimi teki. */
  read(runId: string, sinceRunSeq = -1): Event[] {
    return this.db
      .query<EventRow, [string, number]>(
        'SELECT * FROM events WHERE run_id = ? AND run_seq > ? ORDER BY run_seq ASC',
      )
      .all(runId, sinceRunSeq)
      .map(toEvent);
  }

  getRun(runId: string): {
    runId: string; status: RunStatus; stepBudget: number;
    stepsUsed: number; spendMicros: number;
    forkedFrom: string | null; forkedAtRunSeq: number | null;
  } | null {
    const r = this.db
      .query<{
        run_id: string; status: string; step_budget: number; steps_used: number;
        spend_micros: number; forked_from: string | null; forked_at_run_seq: number | null;
      }, [string]>('SELECT * FROM runs WHERE run_id = ?')
      .get(runId);
    if (!r) return null;
    return {
      runId: r.run_id,
      status: r.status as RunStatus,
      stepBudget: r.step_budget,
      stepsUsed: r.steps_used,
      spendMicros: r.spend_micros,
      forkedFrom: r.forked_from,
      forkedAtRunSeq: r.forked_at_run_seq,
    };
  }

  /**
   * Kopira dogodke 0..atRunSeq DOBESEDNO v nov tek. Spremenita se le `seq` (svez iz
   * AUTOINCREMENT) in `run_id`. `idem_key`, `payload`, `ts`, `actor` in `caused_by_run_seq`
   * ostanejo nespremenjeni; prav zato je enolicnost kljuca omejena na tek in ne globalna.
   *
   * Veja podeduje `step_budget`, ponastavi pa `steps_used` in `spend_micros`, ker je
   * poraba starsa ze placana in je ne placujemo dvakrat.
   */
  fork(runId: string, atRunSeq: number): string {
    const parent = this.getRun(runId);
    if (!parent) throw new Error(`tek '${runId}' ne obstaja`);

    const newRunId = this.idGen();
    const now = this.clock();

    this.db.transaction(() => {
      this.db.run(
        `INSERT INTO runs (run_id, created_at, forked_from, forked_at_run_seq,
                           status, step_budget, steps_used, spend_micros)
         VALUES (?, ?, ?, ?, 'running', ?, 0, 0)`,
        [newRunId, now, runId, atRunSeq, parent.stepBudget],
      );

      this.db.run(
        `INSERT INTO events (run_id, run_seq, ts, actor, kind, payload, caused_by_run_seq, idem_key)
         SELECT ?, run_seq, ts, actor, kind, payload, caused_by_run_seq, idem_key
         FROM events WHERE run_id = ? AND run_seq <= ? ORDER BY run_seq ASC`,
        [newRunId, runId, atRunSeq],
      );
    })();

    return newRunId;
  }

  setStatus(runId: string, status: RunStatus): void {
    this.db.run('UPDATE runs SET status = ? WHERE run_id = ?', [status, runId]);
  }

  /** Drzi `runs.steps_used` usklajen s stevilom dogodkov `step.completed`. */
  incrementStep(runId: string): void {
    this.db.run('UPDATE runs SET steps_used = steps_used + 1 WHERE run_id = ?', [runId]);
  }

  /** Denar je povsod v celih mikrodolarjih, da serializacija ostane deterministicna. */
  addSpendMicros(runId: string, micros: number): void {
    this.db.run('UPDATE runs SET spend_micros = spend_micros + ? WHERE run_id = ?', [
      Math.round(micros), runId,
    ]);
  }

  close(): void {
    this.db.close();
  }
}
