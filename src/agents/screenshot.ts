/**
 * agents/screenshot.ts — zabelezi namero zajema zaslona aplikacije.
 *
 * CIST REDUKTOR. Ta korak je v skeletu NAMERA, ne dejanski zajem slike:
 * pravi pixel-push bi zahteval resnični headless brskalnik in dev strežnik,
 * kar je presoja (varnostna zavesa) zunaj `cmd.exec`. Tukaj qa poganja build
 * (verify), ta agent pa po koncu zabelezi, KJE bi bil screenshot in kaj bi
 * pokazal — v dnevniku ostane only odlocitev, nobena binarvna vsebina.
 *
 * Determinizem: brez baze64, brez absolutnih poti, brez ure.
 */

import type { Agent, Command, Event, RunState } from '../hermes/types.ts';
import { idemKeyFor } from '../hermes/types.ts';

export const screenshot: Agent = {
  role: 'screenshot',

  reduce(state: RunState, event: Event): Command[] {
    // Odzovemo se, ko je bil zapisan kak artefakt (npr. app/main.ts) …
    if (event.kind !== 'artifact.written') return [];
    // … in ce je med artefakti kaksna spletna aplikacija/dashboard.
    const webArtifact = state.artifacts.find(
      (a) => /app\/|\.html$|dashboard/i.test(a.path),
    );
    if (!webArtifact) return [];

    return [
      {
        type: 'decision.record',
        idemKey: idemKeyFor('screenshot', event.runSeq, 0),
        becauseOf: event.runSeq,
        question: 'Kje bi bil screenshot aplikacije?',
        choice: 'posnetka zaslona ni v tej fazi (presoja brskalnika izven cmd.exec)',
        rationale:
          `Zajem slike bi zahteval dejansko brskalniško relo (dev strežnik + screenshot), ` +
          `ki bi sliko uvrstil v dnevnik. V skeletu to izpustimo, vendar zabeležimo ` +
          `artefakt '${webArtifact.path}' kot kandidata za screenshot.`,
      },
    ];
  },
};
