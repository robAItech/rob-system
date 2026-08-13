/**
 * hermes/limits.ts — vse meje na enem mestu.
 *
 * Brez teh stevil je ustavitveni pogoj nedolocen, sistem pa bi se lahko vrtel
 * v krogu ali porabil ves proracun na eni nalogi.
 */
export const LIMITS = {
  /** Koliko dogodkov sme runner obdelati, preden tek razglasi za `stuck`. */
  stepBudget: 120,

  /** Po toliko zaporednih korakih brez napredka je tek `stuck`. */
  noProgressN: 8,

  /** Trda zgornja meja ukazov iz ene redukcije. Brani pred agentom, ki znori. */
  maxCommandsPerAgent: 8,

  /** Trda zgornja meja dogodkov na tek. Zadnja obramba pred neomejeno rastjo. */
  maxEventsPerRun: 2000,

  // produktni generator
  /** Kolikokrat sme qa zazene isti delovni korak (vkl. ponovne izvedbe). */
  maxExecPerStep: 4,
  /** Kolikokrat sme qa POPRAVI isti korak, preden razglasi `stuck`. */
  maxFixPasses: 3,
  /** Zgornja meja izvajanja enega programa (ms). */
  maxExecTimeoutMs: 30_000,
  /** Koliko znakov stdout/stderr sme priti v payload dogodka (determinizem). */
  maxCapturedChars: 6_000,
} as const;
