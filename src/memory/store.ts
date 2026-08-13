/**
 * memory/store.ts — pogodba spominskega sloja.
 *
 * Vmesnik zivi v hermes/types.ts, ker ga potrebuje tudi runner. Tu je ponovno izvozen,
 * da je mesto pogodbe ocitno, in tu zivi pravilo degradacije.
 *
 * PRAVILO: spomin nikoli ne ustavi teka. Ce je zaledje nedosegljivo, `health()` vrne
 * `ok: false`, runner zapise `memory.degraded` in podjetje tece naprej v amneziji.
 * Podsistem, ki si zapomni stvari, ne sme biti tisti, ki podjetje ubije.
 */

export type { MemoryEntry, MemoryHit, MemoryStore } from '../hermes/types.ts';
