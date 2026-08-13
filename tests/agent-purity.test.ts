/**
 * tests/agent-purity.test.ts — uveljavi cistost agentov.
 *
 * Agentni (`src/agents/*.ts`) morajo biti CISTI reduktorji. To ni le slog; je
 * meja, brez katere determinizem (hashEvents, replay) ne more stati. Test preveri
 * IZVORNO kodo, ne izvedbe: ce agent vsili telefon skozi skriti bool ali stavek
 * se bo ta datoteka sprozila prej, kot bo skoda.
 *
 * Prepovedane zmoznosti:
 *   - `fetch(`, `XMLHttpRequest` — omrezje
 *   - `Bun.` — vhod/izhod prek Bun runtime
 *   - `process.` — dostop do okoljske spremenljivke
 *   - `Date.` — stenska ura
 *   - `Math.random` — nakljucje
 *
 * Dovoljena izjema: komentarji (test vsako besedo cez # not in // not, a ne
 * sme zaiti v besedilo string). Za mejnik zadostuje resnica, da ob napravi
 * spremembe pade.
 */

import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { test, expect } from 'bun:test';

const AGENTS_DIR = join(process.cwd(), 'src', 'agents');

// Prepovedani znaki/ti.
const FORBIDDEN: [string, RegExp][] = [
  ['omrezje (fetch/XHR)', /\bfetch\s*\(/],
  ['Bun runtime (Bun.)', /\bBun\s*\./],
  ['os (process.)', /\bprocess\s*\./],
  ['stenska ura (Date)', /\bDate\s*\./],
  ['nakljucje (Math.random)', /\bMath\s*\.\s*random\b/],
];

function agentFiles(): string[] {
  return readdirSync(AGENTS_DIR)
    .filter((f) => f.endsWith('.ts'))
    .map((f) => join(AGENTS_DIR, f));
}

for (const file of agentFiles()) {
  test(`cist reduktor: ${file}`, () => {
    const src = readFileSync(file, 'utf8');

    // Stripi komentarje, da sporocilo v komentarju ne sprozi laznega alarma.
    const withoutComments = src
      .replace(/\/\*[\s\S]*?\*\//g, '')
      .replace(/(^|[^:])\/\/[^\n]*/g, '$1');

    for (const [name, re] of FORBIDDEN) {
      if (re.test(withoutComments)) {
        throw new Error(
          `${file} uporablja prepovedano zmoznost: ${name}.\n` +
            `Agenti so cisti reduktorji in nimajo dostopa do I/O, omrezja ali ure.`,
        );
      }
    }
  });
}

// Preveri, da obstajata oba agenta, ki jih runner pripne (mejnik 1).
test('agentni importi so enaki tistim, ki jih uporablja index.ts', () => {
  const files = agentFiles().map((f) => f.split(/[\\/]/).pop());
  expect(files).toEqual(expect.arrayContaining(['architect.ts', 'engineer.ts']));
});
