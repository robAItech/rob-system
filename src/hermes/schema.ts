/**
 * hermes/schema.ts — edina shema, edina baza.
 *
 * Obstaja natanko ena SQLite datoteka. Vse tri tabele so tu, hermes drzi rocico,
 * vticniki (bridges/cache, memory/sqlite-store) jo dobijo z injekcijo. Tako drzi
 * trditev, da je hermes edini lastnik stanja na disku.
 */

import type { Database } from 'bun:sqlite';
import { ALL_ACTORS, ALL_EVENT_KINDS, ALL_RUN_STATUSES } from './types.ts';

const sqlList = (xs: readonly string[]): string => xs.map((x) => `'${x}'`).join(',');

/**
 * Pragme so vezane na POVEZAVO, ne na datoteko. `foreign_keys` je treba nastaviti
 * ob vsakem odprtju; `journal_mode = WAL` se sicer zapise trajno, a ga nastavimo
 * skupaj, da je vedenje enako ne glede na to, kdo je bazo ustvaril.
 */
export function applyPragmas(db: Database): void {
  db.run('PRAGMA journal_mode = WAL');
  db.run('PRAGMA foreign_keys = ON');
}

export function migrate(db: Database): void {
  db.run(`
    CREATE TABLE IF NOT EXISTS runs (
      run_id            TEXT PRIMARY KEY,
      created_at        TEXT    NOT NULL,
      forked_from       TEXT    REFERENCES runs(run_id),
      forked_at_run_seq INTEGER,
      status            TEXT    NOT NULL CHECK (status IN (${sqlList(ALL_RUN_STATUSES)})),
      step_budget       INTEGER NOT NULL,
      steps_used        INTEGER NOT NULL DEFAULT 0,
      spend_micros      INTEGER NOT NULL DEFAULT 0
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS events (
      seq               INTEGER PRIMARY KEY AUTOINCREMENT,
      run_id            TEXT    NOT NULL REFERENCES runs(run_id),
      run_seq           INTEGER NOT NULL,
      ts                TEXT    NOT NULL,
      actor             TEXT    NOT NULL CHECK (actor IN (${sqlList(ALL_ACTORS)})),
      kind              TEXT    NOT NULL CHECK (kind  IN (${sqlList(ALL_EVENT_KINDS)})),
      payload           TEXT    NOT NULL,
      caused_by_run_seq INTEGER,
      idem_key          TEXT    NOT NULL,
      UNIQUE (run_id, run_seq),
      -- NE globalno: fork kopira prefiks dobesedno, skupaj s kljuci idempotence.
      UNIQUE (run_id, idem_key)
    )
  `);

  db.run('CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, run_seq)');

  db.run(`
    CREATE TABLE IF NOT EXISTS llm_cache (
      req_hash   TEXT PRIMARY KEY,
      provider   TEXT NOT NULL,   -- ni del kljuca, je pa v zgosceni vrednosti; tu zaradi pregleda
      model      TEXT NOT NULL,
      response   TEXT NOT NULL,
      usage      TEXT NOT NULL,
      created_at TEXT NOT NULL
    )
  `);

  db.run(`
    CREATE TABLE IF NOT EXISTS memory (
      key        TEXT PRIMARY KEY,
      text       TEXT NOT NULL,
      tags       TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL
    )
  `);
}
