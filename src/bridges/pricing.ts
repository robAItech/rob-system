/**
 * bridges/pricing.ts — rocno vzdrzevana cenovna tabela.
 *
 * Denar je povsod v CELIH mikrodolarjih (1 USD = 1_000_000 mikrodolarjev). Plavajoce
 * vejice bi se znasle v payloadu dogodka in s tem v `hashEvents`, kjer je serializacija
 * stevil obcutljiva na format. Cela stevila tega problema nimajo.
 *
 * OPOZORILO: te cene so rocno vpisane in se spreminjajo. Preveri jih, preden se
 * zanesli na `runs.spend_micros` za karkoli resnega. Neznan model se obracuna kot 0,
 * kar je namerno: raje prijavi nic kot izmisljeno stevilko.
 */

export interface ModelPrice {
  /** Mikrodolarji na milijon vhodnih zetonov. */
  inMicrosPerMTok: number;
  /** Mikrodolarji na milijon izhodnih zetonov. */
  outMicrosPerMTok: number;
}

export const PRICING: Record<string, ModelPrice> = {
  // OpenAI
  'gpt-4o-mini': { inMicrosPerMTok: 150_000, outMicrosPerMTok: 600_000 },
  'gpt-4o': { inMicrosPerMTok: 2_500_000, outMicrosPerMTok: 10_000_000 },

  // DeepSeek
  'deepseek-chat': { inMicrosPerMTok: 270_000, outMicrosPerMTok: 1_100_000 },
  'deepseek-reasoner': { inMicrosPerMTok: 550_000, outMicrosPerMTok: 2_190_000 },
};

/**
 * Lokalni modeli ne stanejo nic. Ollama modeli nimajo vnosa v `PRICING` in se
 * obracunajo kot 0, kar je pravilno, ne privzeto.
 */
export function costMicros(model: string, promptTokens: number, completionTokens: number): number {
  const price = PRICING[model];
  if (!price) return 0;
  const inCost = (promptTokens * price.inMicrosPerMTok) / 1_000_000;
  const outCost = (completionTokens * price.outMicrosPerMTok) / 1_000_000;
  return Math.round(inCost + outCost);
}
