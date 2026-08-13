/**
 * agents/builder.ts — koder: razreze LLM-ov odgovor na `@file` bloke in pise datoteke.
 *
 * CIST REDUKTOR. Celoten razrez je PURE string-logika (brez I/O, brez ure):
 * poisce vzorce `@file <pot>` in linijske tri-nadstropske bloke ``````, ter vsak
 * pretvori v `fs.write`. Na koncu izda `qa.decide` (action 'verify'), da qa ve,
 * kdaj je generiranje koncano in naj pozeni preverjanje.
 *
 * `becauseOf` na vsakem `fs.write` je nastavljen na odlocitev (plannerjev runSeq),
 * da `provenance()` vrne verigo ideja -> odlocitev -> artefakt, ne zvezdo.
 */

import type { Agent, Command, Event, RunState } from '../hermes/types.ts';
import { idemKeyFor } from '../hermes/types.ts';

/**
 * Robusten razrez `@file` blokov. Sprejme dve obliki, ki ju lokalni modeli
 * dejansko vmejo:
 *   1. striktni:  @file pot\n```lang\nvsebina\n```
 *   2. prosti:    @file pot\nvsebina … (do naslednjega @file ali konca)
 * Vsebina preskoci vodilne `` ``` ``/```` ``` ```` oznake, da se ne smetejo v artefakt.
 */
function parseArtifacts(text: string): { path: string; content: string }[] {
  const out: { path: string; content: string }[] = [];
  const parts = text.split(/(?=^@file\s)/m);
  for (const part of parts) {
    const mm = /^@file\s+(\S+)\s*\n?([\s\S]*)$/.exec(part.trimStart());
    if (!mm) continue;
    const path = mm[1]!.trim();
    let content = mm[2] ?? '';
    if (!path) continue;
    // Odstrani vodilni tri-or-nadstropni oznacevalec (```lang / ```) ce obstaja.
    content = content.replace(/^```[^\n]*\n/, '');
    // Odstrani zakljucni ``` ce je tam.
    content = content.replace(/\s*```\s*$/, '');
    content = content.replace(/\n+$/, '');
    if (content.length > 0 || part.includes('```')) out.push({ path, content });
  }
  return out;
}

export const builder: Agent = {
  role: 'builder',

  reduce(state: RunState, event: Event): Command[] {
    // Reagira samo, ko je model odgovoril in nista ze vse pisbe izvedena.
    if (event.kind !== 'llm.responded') return [];
    if (state.artifacts.length > 0) return [];

    const text = state.lastLLM?.text ?? '';
    let artifacts = parseArtifacts(text);
    const decisionRunSeq = state.decisions.at(-1)?.runSeq ?? event.runSeq;

    // Obstojc: model ni uporabil strukture @file (npr. se za poslovni predlog vrne
    // navadan Markdown). Namesto da bi sistem zavrel na "ni @file bloka", zapakiramo
    // celoten odgovor v eno datoteko — za besedilne artefakte je to pravilno, ne zguba.
    if (artifacts.length === 0 && text.trim().length > 0) {
      artifacts = [{ path: 'out/RESULT.md', content: text }];
    }
    if (artifacts.length === 0) {
      return [
        {
          type: 'run.declareStuck',
          idemKey: idemKeyFor('builder', event.runSeq, 0),
          becauseOf: event.runSeq,
          reason: 'LLM je vrnil prazen odgovor',
        },
      ];
    }

    // Pripis verigi: vsak zapis iz vira odlocitev (zadnja decision.made).
    const cmds: Command[] = artifacts.map((a, i) => ({
      type: 'fs.write',
      idemKey: idemKeyFor('builder', event.runSeq, i + 1),
      becauseOf: decisionRunSeq,
      path: a.path,
      content: a.content,
    }));

    // Na koncu sprozi qa, da verificira generirano vsebino.
    cmds.push({
      type: 'qa.decide',
      idemKey: idemKeyFor('builder', event.runSeq, artifacts.length + 1),
      becauseOf: decisionRunSeq,
      action: 'verify',
      which: 'generate',
      reason: 'generirano; prosim preveri',
    });

    return cmds;
  },
};
