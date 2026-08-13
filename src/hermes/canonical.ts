/**
 * hermes/canonical.ts — kanonizacija in zgoscene vrednosti.
 *
 * Determinizem stoji ali pade tu. Dve strukturi, ki sta pomensko enaki, morata dati
 * isti niz, sicer se replay razide in predpomnilnik zgresi.
 */

import type { Event } from './types.ts';

/**
 * JSON s stabilnim vrstnim redom kljucev in brez presledkov.
 *
 * - Kljuci objektov so urejeni po abecedi (leksikografsko po kodnih tockah).
 * - `undefined` v objektu se izpusti, v polju postane `null` (kot pri JSON.stringify).
 * - Plavajoce vejice so dovoljene, a jih sistem namenoma ne uporablja za denar;
 *   denar je povsod v celih mikrodolarjih.
 */
export function canonicalJson(value: unknown): string {
  return stringify(value);
}

function stringify(v: unknown): string {
  if (v === null) return 'null';

  const t = typeof v;
  if (t === 'number') {
    if (!Number.isFinite(v as number)) {
      throw new Error('canonicalJson: neskoncna ali NaN vrednost ni dovoljena');
    }
    return JSON.stringify(v);
  }
  if (t === 'string' || t === 'boolean') return JSON.stringify(v);
  if (t === 'undefined') return 'null';

  if (Array.isArray(v)) {
    return '[' + v.map(stringify).join(',') + ']';
  }

  if (t === 'object') {
    const obj = v as Record<string, unknown>;
    const keys = Object.keys(obj).filter((k) => obj[k] !== undefined).sort();
    return '{' + keys.map((k) => JSON.stringify(k) + ':' + stringify(obj[k])).join(',') + '}';
  }

  throw new Error(`canonicalJson: nepodprt tip ${t}`);
}

/** sha256 nad nizom, vrnjen kot hex. */
export function sha256Hex(input: string): string {
  return new Bun.CryptoHasher('sha256').update(input, 'utf8').digest('hex');
}

/** sha256 nad medpomnilnikom. Uporabi se za artefakte, da CRLF na disku ne vpliva. */
export function sha256Bytes(input: Uint8Array): string {
  return new Bun.CryptoHasher('sha256').update(input).digest('hex');
}

/**
 * Deterministicen odtis dnevnika teka.
 *
 * Namenoma IZPUSCA `seq` (globalen, se ob replayu spremeni), `runId` (nov ob replayu
 * in forku) in `ts` (stenska ura). Vse ostalo mora biti reproducibilno, kar je razlog
 * za disciplino payloada v types.ts: brez absolutnih poti, brez casovnih zigov,
 * brez identifikatorjev odgovora ponudnika, denar v celih mikrodolarjih.
 */
export function hashEvents(events: Event[]): string {
  const shape = events.map((e) => ({
    runSeq: e.runSeq,
    actor: e.actor,
    kind: e.kind,
    payload: e.payload,
    causedByRunSeq: e.causedByRunSeq,
    idemKey: e.idemKey,
  }));
  return sha256Hex(canonicalJson(shape));
}

/** Normalizira pot v relativno POSIX obliko. Absolutne poti v payloadu so prepovedane. */
export function posixRelative(p: string): string {
  const unified = p.replace(/\\/g, '/');
  const stripped = unified.replace(/^[A-Za-z]:\//, '').replace(/^\/+/, '');
  return stripped.replace(/\/{2,}/g, '/');
}
