/**
 * bridges/openai-compatible.ts — en odjemalec za vse tri ponudnike.
 *
 * Brez SDK. Surov `fetch` na POST {baseUrl}/chat/completions, brez pretakanja.
 * OpenAI, DeepSeek in Ollama govorijo isti format, zato je to vsa "integracija",
 * ki jo sistem potrebuje.
 */

import type { CompletionRequest, CompletionResult, FailureCode, LLMProvider } from '../hermes/types.ts';
import { LLMCache, requestHash } from './cache.ts';
import { costMicros } from './pricing.ts';

export class ProviderError extends Error {
  constructor(readonly code: FailureCode, message: string) {
    super(message);
    this.name = 'ProviderError';
  }
}

/** Preslika HTTP status ali omrezno napako v normalizirano kodo. Sporocila OS ne gredo v payload. */
function classify(status: number | null): FailureCode {
  if (status === null) return 'ENETWORK';
  if (status === 401 || status === 403) return 'EAUTH';
  if (status === 429) return 'ERATE';
  if (status >= 500) return 'ENETWORK';
  return 'EUNKNOWN';
}

interface ChatCompletionResponse {
  choices?: { message?: { content?: string } }[];
  usage?: { prompt_tokens?: number; completion_tokens?: number };
}

export interface OpenAICompatibleOptions {
  baseUrl: string;
  apiKey: string | null;
  cache: LLMCache;
  /** Injekcija za teste. Privzeto globalni `fetch`. */
  fetchImpl?: typeof fetch;
  timeoutMs?: number;
}

export class OpenAICompatibleProvider implements LLMProvider {
  /** Stevec resnicnih omreznih klicev. Replay ga mora pustiti na 0. */
  liveCalls = 0;

  private readonly fetchImpl: typeof fetch;

  constructor(readonly name: string, private readonly opts: OpenAICompatibleOptions) {
    this.fetchImpl = opts.fetchImpl ?? fetch;
  }

  async complete(req: CompletionRequest): Promise<CompletionResult> {
    const hash = requestHash(req);

    const hit = this.opts.cache.get(hash);
    if (hit) {
      return { text: hit.text, usage: hit.usage, cached: true };
    }

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (this.opts.apiKey) headers['Authorization'] = `Bearer ${this.opts.apiKey}`;

    let res: Response;
    this.liveCalls += 1;
    try {
      res = await this.fetchImpl(`${this.opts.baseUrl}/chat/completions`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          model: req.model,
          messages: req.messages,
          temperature: req.temperature ?? 0,
          max_tokens: req.maxTokens,
          stream: false,
        }),
        signal: AbortSignal.timeout(this.opts.timeoutMs ?? 600_000),
      });
    } catch {
      throw new ProviderError('ENETWORK', `omrezna napaka proti ${this.name}`);
    }

    if (!res.ok) {
      throw new ProviderError(classify(res.status), `${this.name} je vrnil ${res.status}`);
    }

    const body = (await res.json()) as ChatCompletionResponse;
    const text = body.choices?.[0]?.message?.content ?? '';
    const promptTokens = body.usage?.prompt_tokens ?? 0;
    const completionTokens = body.usage?.completion_tokens ?? 0;

    // Iz odgovora vzamemo SAMO to. `id`, `created` in `system_fingerprint` so
    // nedeterministicni in ne smejo v payload dogodka, ker je ta del `hashEvents`.
    const usage = {
      promptTokens,
      completionTokens,
      usdMicros: costMicros(req.model, promptTokens, completionTokens),
    };

    this.opts.cache.put(hash, req.provider, req.model, { text, usage });
    return { text, usage, cached: false };
  }
}
