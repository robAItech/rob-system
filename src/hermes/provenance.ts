/**
 * hermes/provenance.ts — "zakaj ta datoteka obstaja".
 *
 * Vrne vzrocno verigo od zacetka do artefakta, tako da sledi `causedByRunSeq` nazaj.
 * Veriga deluje samo, ce runner vzrocnost vezuje pravilno: odgovor kaze na svojo
 * zahtevo, zapis artefakta pa na odlocitev, zaradi katere je nastal (`becauseOf`).
 * Ce bi vsak dogodek kazal na sprozilni dogodek, bi dobili zvezdo in ne verige.
 */

import { posixRelative } from './canonical.ts';
import type { ArtifactWrittenPayload, Event } from './types.ts';

/**
 * @param events  celoten dnevnik teka, urejen po `runSeq`
 * @param artifactPath  relativna POSIX pot artefakta
 * @returns veriga od korena do artefakta; prazno polje, ce artefakta ni
 */
export function provenance(events: Event[], artifactPath: string): Event[] {
  const wanted = posixRelative(artifactPath);
  const byRunSeq = new Map<number, Event>();
  for (const e of events) byRunSeq.set(e.runSeq, e);

  const target = events.find(
    (e) => e.kind === 'artifact.written' &&
      posixRelative((e.payload as ArtifactWrittenPayload).path) === wanted,
  );
  if (!target) return [];

  const chain: Event[] = [];
  const seen = new Set<number>();
  let cursor: Event | undefined = target;

  while (cursor && !seen.has(cursor.runSeq)) {
    seen.add(cursor.runSeq);
    chain.push(cursor);
    cursor = cursor.causedByRunSeq === null ? undefined : byRunSeq.get(cursor.causedByRunSeq);
  }

  return chain.reverse();
}
