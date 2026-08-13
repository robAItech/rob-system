/**
 * bridges/cache.ts — predpomnilnik, naslovljen po vsebini zahteve.
 *
 * POMEMBNO glede vloge: determinizem replaya NE prihaja od tod. Replay ne izvrsi
 * nobenega ucinka in vsak rezultat prebere iz zapisanega dogodka. Predpomnilnik ima
 * natanko dva namena:
 *   1. ponovljene enake pozive na poti naprej ne placas dvakrat,
 *   2. forkana veja poceni ponovi zahteve, ki jih je starс ze placal.
 *
 * ZNANA OMEJITEV: predpomnilnik ni omejen na tek. Forkana veja, ki izda bajtno enak
 * poziv, dobi starsev odgovor in pri `temperature > 0` ne more potegniti drugega
 * vzorca. Protidejstveni teki se torej lahko razlikujejo po pozivu, ne po ponovnem
 * zrebu. Ce zelis nov zreb, povisaj `attempt` v zahtevi; to je nov kljuc.
 */

import type { Database } from 'bun:sqlite';
import { canonicalJson, sha256Hex } from '../hermes/canonical.ts';
import type { CompletionRequest } from '../hermes/types.ts';

export interface CachedCompletion {
  text: string;
  usage: { promptTokens: number; completionTokens: number; usdMicros: number };
}

/**
 * Kanonizacija zahteve. `provider` je del zgoscene vrednosti, sicer bi ista zahteva
 * na DeepSeek in na OpenAI trcila v isti kljuc. `attempt` je prav tako del kljuca,
 * sicer bi zataknjen tek ob ponovnem poskusu vecno dobival isti odgovor.
 */
export function requestHash(req: CompletionRequest): string {
  return sha256Hex(
    canonicalJson({
      provider: req.provider,
      model: req.model,
      messages: req.messages,
      temperature: req.temperature ?? null,
      maxTokens: req.maxTokens ?? null,
      attempt: req.attempt,
    }),
  );
}

export class LLMCache {
  constructor(private readonly db: Database, private readonly clock: () => string = () => new Date().toISOString()) {}

  get(reqHash: string): CachedCompletion | null {
    const row = this.db
      .query<{ response: string; usage: string }, [string]>(
        'SELECT response, usage FROM llm_cache WHERE req_hash = ?',
      )
      .get(reqHash);
    if (!row) return null;
    return {
      text: row.response,
      usage: JSON.parse(row.usage) as CachedCompletion['usage'],
    };
  }

  put(reqHash: string, provider: string, model: string, value: CachedCompletion): void {
    this.db.run(
      `INSERT OR REPLACE INTO llm_cache (req_hash, provider, model, response, usage, created_at)
       VALUES (?, ?, ?, ?, ?, ?)`,
      [reqHash, provider, model, value.text, JSON.stringify(value.usage), this.clock()],
    );
  }
}
