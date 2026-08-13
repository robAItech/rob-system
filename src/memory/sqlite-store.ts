/**
 * memory/sqlite-store.ts — privzeti spominski izvajalec.
 *
 * Namenoma preprost: iskanje po ujemanju podnizov, brez vlaganj. Za en solo repozitorij
 * je to dovolj, in za razliko od gbrain ne potrebuje ne Ollame ne zunanjega procesa.
 *
 * Deluje nad ISTO bazo kot dnevnik. Rocico dobi z injekcijo, ker je hermes edini
 * lastnik datoteke na disku.
 *
 * gbrain adapter (`gbrain-store.ts`) implementira isti vmesnik in pride po skeletu.
 * Takrat se zamenja tu in nikjer drugje; agenti se ne spremenijo.
 */

import type { Database } from 'bun:sqlite';
import type { FailureCode, MemoryEntry, MemoryHit, MemoryStore } from '../hermes/types.ts';

export class SqliteMemoryStore implements MemoryStore {
  constructor(
    private readonly db: Database,
    private readonly clock: () => string = () => new Date().toISOString(),
  ) {}

  async remember(entry: MemoryEntry): Promise<void> {
    this.db.run(
      `INSERT OR REPLACE INTO memory (key, text, tags, created_at) VALUES (?, ?, ?, ?)`,
      [entry.key, entry.text, JSON.stringify(entry.tags ?? []), this.clock()],
    );
  }

  async recall(query: string, limit = 5): Promise<MemoryHit[]> {
    const needle = `%${query.toLowerCase()}%`;
    const rows = this.db
      .query<{ key: string; text: string }, [string, string, number]>(
        `SELECT key, text FROM memory
         WHERE lower(text) LIKE ? OR lower(key) LIKE ?
         ORDER BY key ASC LIMIT ?`,
      )
      .all(needle, needle, limit);

    // Ocena je namenoma determinsticna in preprosta: daljse ujemanje ni bolje,
    // vrstni red je po kljucu. Nakljucje ali cas tu ne smeta nastopiti.
    return rows.map((r, i) => ({ key: r.key, text: r.text, score: 1 - i / (rows.length || 1) }));
  }

  async health(): Promise<{ ok: boolean; backend: string; detail?: FailureCode }> {
    try {
      this.db.query('SELECT 1 FROM memory LIMIT 1').get();
      return { ok: true, backend: 'sqlite' };
    } catch {
      return { ok: false, backend: 'sqlite', detail: 'EUNKNOWN' };
    }
  }
}
