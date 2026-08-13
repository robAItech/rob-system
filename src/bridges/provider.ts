/**
 * bridges/provider.ts — register ponudnikov.
 *
 * Predpostavka P1 nacrta pravi, da `bridges/` ni podsistem, ampak konfiguracijska
 * tabela. Tu je ta tabela. Vsi trije ponudniki govorijo isti OpenAI wire format,
 * zato je razlika med njimi bazni naslov, kljuc in privzeti model.
 *
 * Ollama je dokaz te predpostavke: dodan je bil kot tretja vrstica, brez ene same
 * vrstice nove logike, in ne potrebuje kljuca ne omreznega dostopa navzven.
 */

export interface ProviderConfig {
  /** Bazni naslov, ki se konca s segmentom, na katerega se pripne /chat/completions. */
  baseUrl: string;
  /** Ime okoljske spremenljivke s kljucem, ali `null`, ce kljuc ni potreben. */
  apiKeyEnv: string | null;
  defaultModel: string;
  /** Preglasitev baznega naslova iz okolja, na primer za lokalni proxy. */
  baseUrlEnv: string;
}

export const PROVIDERS = {
  ollama: {
    baseUrl: 'http://127.0.0.1:11434/v1',
    apiKeyEnv: null,
    defaultModel: 'llama3.2:3b',
    baseUrlEnv: 'OLLAMA_BASE_URL',
  },
  openai: {
    baseUrl: 'https://api.openai.com/v1',
    apiKeyEnv: 'OPENAI_API_KEY',
    defaultModel: 'gpt-4o-mini',
    baseUrlEnv: 'OPENAI_BASE_URL',
  },
  deepseek: {
    baseUrl: 'https://api.deepseek.com/v1',
    apiKeyEnv: 'DEEPSEEK_API_KEY',
    defaultModel: 'deepseek-chat',
    baseUrlEnv: 'DEEPSEEK_BASE_URL',
  },
} as const satisfies Record<string, ProviderConfig>;

export type ProviderName = keyof typeof PROVIDERS;

export function isProviderName(x: string): x is ProviderName {
  return Object.hasOwn(PROVIDERS, x);
}

/** Ponudnik iz okolja. Privzeto Ollama, ker tece lokalno in ne stane nic. */
export function resolveProvider(env: Record<string, string | undefined>): {
  name: ProviderName; config: ProviderConfig; baseUrl: string;
  apiKey: string | null; model: string;
} {
  const raw = env.LLM_PROVIDER ?? 'ollama';
  if (!isProviderName(raw)) {
    throw new Error(
      `neznan LLM_PROVIDER '${raw}'; na voljo: ${Object.keys(PROVIDERS).join(', ')}`,
    );
  }

  const config = PROVIDERS[raw];
  const baseUrl = env[config.baseUrlEnv] ?? config.baseUrl;
  const apiKey = config.apiKeyEnv ? (env[config.apiKeyEnv] ?? null) : null;

  if (config.apiKeyEnv && !apiKey) {
    throw new Error(
      `ponudnik '${raw}' zahteva ${config.apiKeyEnv}, ki ni nastavljen. ` +
      `Za tek brez kljuca uporabi LLM_PROVIDER=ollama.`,
    );
  }

  return { name: raw, config, baseUrl, apiKey, model: env.LLM_MODEL ?? config.defaultModel };
}
