/**
 * hermes/runner.ts — izvajalno jedro.
 *
 * Runner ni agent in ni vticnik. Je edino mesto z zmoznostjo: branje okolja,
 * omrezje in disk. Zato je edini, ki pise skozi `Ledger`. Agenti so cisti
 * reduktorji, vticniki pasivne storitve; runner drzi skupaj celotno zanko teka.
 *
 * Determinizem:
 *   - Replay ne sme sproziti nobene zmoznosti. Vsak rezultat prihaja iz dnevnika
 *     oziroma iz predpomnilnika; `liveCalls` (v vticniku) ostane na 0 ob replayu.
 *   - Vsak izvrseni ukaz zapise en `step.completed`, da je `stepsUsed` (in s tem
 *     proracun) del dnevnika, ne zgolj stanja na disku. Replay da enake stevilke.
 *
 * Idempotenca:
 *   - Vsak ukaz nosi `idemKey`. Ce `Ledger.append` vrze `DuplicateIdemKeyError`,
 *     dogodek ze obstaja in runner to obravnava kot "ze narejeno", ne napako.
 *   - Redukcija enega agenta je omejena na `LIMITS.maxCommandsPerAgent`.
 *
 * Ustavitev (v tem zaporedju):
 *   1. agent izda `run.complete` ali `run.declareStuck`;
 *   2. izcrpan proracun korakov (`stepBudget`);
 *   3. prevec zaporednih korakov brez napredka (`noProgressN`);
 *   4. trda meja dogodkov (`maxEventsPerRun`, jo uveljavi `Ledger.append`).
 */

import { foldState } from './state.ts';
import { Ledger, DuplicateIdemKeyError } from './ledger.ts';
import { LIMITS } from './limits.ts';
import { sha256Bytes, posixRelative } from './canonical.ts';
import { requestHash } from '../bridges/cache.ts';
import { truncate } from '../bridges/exec.ts';
import type { ExecLike } from '../bridges/exec.ts';
import type {
  Agent, Command, CompletionResult, Event, EventKind, ExecRanPayload, FailureCode,
  LLMProvider, MemoryHit, MemoryStore,
} from './types.ts';
import { ACTIONABLE_KINDS } from './types.ts';

/** Razultat teka, kot ga vidita klicatelj in CLI. */
export interface RunOutcome {
  runId: string;
  status: 'completed' | 'stuck' | 'aborted';
  reason: string;
  stepsUsed: number;
  spendMicros: number;
  artifactPath: string | null;
  /** Vse poti artefaktov, ki so v tem teku nastali (produktni generator). */
  artifactPaths: string[];
}

/** Abstrakcija diska, injicirana za testabilnost. */
export interface FsLike {
  write(path: string, content: string): Promise<Uint8Array>;
  read(path: string): Promise<Uint8Array>;
}

/**
 * Zunanje storitve, vse injicirane. LLM prihaja iz vticnika, Memory iz memory/.
 *
 * `provider` in `model` poznata le runner in index.ts, NE agenti. Agent izda samo
 * `CompletionAsk` (vsebina vprasanja); runner ga zapakira v `CompletionRequest`
 * s providerjem in modelom, kot pravi komentar v types.ts.
 */
export interface RunnerDeps {
  ledger: Ledger;
  agents: readonly Agent[];
  llm: LLMProvider;
  /** Ime ponudnika (enako `llm.name`), del zgoscene vrednosti zahteve. */
  provider: string;
  /** Model, na katerega se posilja. Agent ga ne pozna; runner ga vedno dodaja. */
  model: string;
  memory: MemoryStore;
  fs: FsLike;
  /** Zmogljivost izvajanja programov. Ce ni podan, `cmd.exec` vraca EACCES. */
  exec?: ExecLike;
  /** Dovoljeni argv[0] za `cmd.exec`. Privzeto DEFAULT_EXEC_ALLOW. */
  execAllow?: string[];
  /** Koren imenika, znotraj katerega je izvajanju dovoljen `cwd`. */
  execCwdRoot?: string;
  /** Ce je true, `cmd.exec` diskretno zavrne (za --no-verify / demo). */
  execDisabled?: boolean;
}

/** Privzeti allowlist izvajalnih programov (varnostna zavesa). */
export const DEFAULT_EXEC_ALLOW = [
  'bun', 'node', 'npx', 'npm', 'pnpm', 'yarn',
  'git', 'echo', 'ls', 'cat', 'mkdir', 'rmdir', 'rm', 'cp', 'mv',
  'python3', 'python', 'bash', 'sh',
  'true', 'false',
] as const;

/** Kljuci, ki jih posredujemo izvajanju; vse ostalo v `env` se ignorira. */
const ALLOWED_ENV_KEYS = ['PATH', 'HOME', 'TMPDIR', 'CI', 'NODE_ENV', 'FORCE_COLOR'] as const;

function isActionable(kind: EventKind): boolean {
  return ACTIONABLE_KINDS.some((k) => k === kind);
}

/** Preveri, da cwd ostane znotraj korena (prepreci pobeg iz delovnega imenika). */
function cwdSafe(root: string | undefined, cwd: string): boolean {
  if (!root) return true;
  const rel = posixRelative(cwd);
  if (rel.startsWith('../') || rel === '..') return false;
  return true;
}

/** Zaporedje dela znotraj enega teka. */
type Work =
  | { kind: 'reduce'; event: Event }
  | { kind: 'exec'; cmd: Command; cause: number };

export class Runner {
  /** Runner je vezan na natanko en tek, da je `runId` vedno v dosegu. */
  private constructor(
    private readonly runId: string,
    private readonly deps: RunnerDeps,
  ) {}

  static forRun(runId: string, deps: RunnerDeps): Runner {
    return new Runner(runId, deps);
  }

  /**
   * Zazene (ali dokonca) tek.
   *
   * Idempotentna po naravi: ce tek ze vsebuje `task.submitted`, ga ne podvaji.
   * Ponovni klic z istim `runId` je zato nadaljevanje, ne nov tek.
   */
  async run(task: string): Promise<RunOutcome> {
    const { ledger } = this.deps;
    const runId = this.runId;

    const initial = ledger.getRun(runId);
    if (!initial) throw new Error(`tek '${runId}' ne obstaja`);
    if (initial.status === 'completed' || initial.status === 'aborted') {
      return this.snapshot();
    }

    // Vhodni korak ni 'korak' proracuna: je predpostavka naloge.
    if (!ledger.read(runId).some((e) => e.kind === 'task.submitted')) {
      this.appendSafe({
        actor: 'human', kind: 'task.submitted', payload: { task },
        causedByRunSeq: 0, idemKey: 'human:task.submitted',
      });
    }

    const queue: Work[] = [];
    const reduced = new Set<number>();

    const enqueueReductionFor = (trigger: Event) => {
      if (reduced.has(trigger.runSeq)) return;
      reduced.add(trigger.runSeq);
      queue.push({ kind: 'reduce', event: trigger });
    };

    const submitted = ledger.read(runId).find((e) => e.kind === 'task.submitted');
    if (submitted) enqueueReductionFor(submitted);

    let noProgress = 0;

    while (queue.length > 0) {
      const cur = ledger.getRun(runId)!;
      if (cur.status === 'completed' || cur.status === 'aborted') break;
      if (cur.stepsUsed >= LIMITS.stepBudget) {
        await this.declareStuck(`izcrpan proracun korakov (${LIMITS.stepBudget})`);
        break;
      }
      if (noProgress >= LIMITS.noProgressN) {
        await this.declareStuck(`${LIMITS.noProgressN} zaporednih korakov brez napredka`);
        break;
      }

      const work = queue.shift()!;

      if (work.kind === 'reduce') {
        const commands = this.reduceAgents(work.event);
        for (const cmd of commands) queue.push({ kind: 'exec', cmd, cause: work.event.runSeq });
        continue;
      }

      const progressed = await this.execute(work.cmd, work.cause);
      noProgress = progressed ? 0 : noProgress + 1;

      // Novi akcionabilni dogodki iz te izvedbe se reducirajo v naslednjem krogu.
      for (const e of ledger.read(runId)) {
        if (isActionable(e.kind) && !reduced.has(e.runSeq)) enqueueReductionFor(e);
      }
    }

    // Defenzivno: ce je zanka minila brez koncnega statusa, je tek obvisel.
    const final = ledger.getRun(runId)!;
    if (final.status === 'running') await this.declareStuck('zanka je minila, a tek je ostal running');

    return this.snapshot();
  }

  // ─── redukcija ──────────────────────────────────────────────────────────────

  private reduceAgents(trigger: Event): Command[] {
    const { ledger, agents } = this.deps;
    const events = ledger.read(trigger.runId);
    const state = foldState(trigger.runId, events);
    const ev = events.find((e) => e.runSeq === trigger.runSeq) ?? trigger;

    const commands: Command[] = [];
    for (const agent of agents) {
      let out: Command[];
      try {
        out = agent.reduce(state, ev);
      } catch (err) {
        // Agent pade: preskocimo ga, a sistem se ne vrti.
        console.error(`[runner] agent '${agent.role}' padel ob redukciji: ${String(err)}`);
        continue;
      }
      if (out.length > LIMITS.maxCommandsPerAgent) out = out.slice(0, LIMITS.maxCommandsPerAgent);
      commands.push(...out);
    }
    return commands;
  }

  // ─── izvedba ────────────────────────────────────────────────────────────────

  /** @returns `true`, ce je ukaz prinesel napredek (odlocitev ali artefakt). */
  private async execute(cmd: Command, fallbackCause: number): Promise<boolean> {
    // Agent, ki zna povedati VZROK, ga nastavi v `becauseOf` (npr. inzenir zapise
    // artefakt zaradi odlocitve). Brez tega bi vsak dogodek padal na sprozilnega in
    // `provenance()` bi vrnil zvezdo namesto verige.
    const cause = cmd.becauseOf ?? fallbackCause;
    switch (cmd.type) {
      case 'decision.record':
        this.writeStep(cmd, cause, 'decision.made', {
          question: cmd.question, choice: cmd.choice, rationale: cmd.rationale,
        });
        return true;

      case 'log.thought':
        this.writeStep(cmd, cause, 'agent.thought', { text: cmd.text });
        return false;

      case 'memory.store':
        return this.memoryStore(cmd, cause);

      case 'memory.recall':
        return this.memoryRecall(cmd, cause);

      case 'llm.complete':
        return this.llmComplete(cmd, cause);

      case 'fs.write':
        return this.fsWrite(cmd, cause);

      case 'cmd.exec':
        return this.execCommand(cmd, cause);

      case 'cmd.read':
        return this.readFile(cmd, cause);

      case 'plan.record':
        // zabelezi workplan; foldState jo postavi v state.workplan.
        this.appendSafe({
          kind: 'plan.submitted', payload: { steps: cmd.steps },
          causedByRunSeq: cause, idemKey: cmd.idemKey,
        });
        return true;

      case 'qa.decide':
        // qa.decision je akcionablen: sprozi novo redukcijo (qa jo pokaze naprej).
        this.appendSafe({
          kind: 'qa.decision',
          payload: { action: cmd.action, which: cmd.which, reason: cmd.reason },
          causedByRunSeq: cause, idemKey: cmd.idemKey,
        });
        return true;

      case 'run.complete':
        this.writeStep(cmd, cause, 'run.completed', { reason: cmd.reason });
        return false;

      case 'run.declareStuck':
        this.writeStep(cmd, cause, 'run.stuck', { reason: cmd.reason });
        return false;
    }
  }

  /** Zapis `step.completed` + en sledeci dogodek iste skrbi (isto `cause`). */
  private writeStep(cmd: Command, cause: number, kind: EventKind, payload: unknown): void {
    this.appendSafe({ kind: 'step.completed', payload: {}, causedByRunSeq: cause, idemKey: `${cmd.idemKey}:step` });
    // Drzi runs.steps_used usklajen s stevilom dogodkov step.completed. Oba vira
    // resnice stapata enako, zato proracun (v SQL) in stanje (v foldState) ne zaostaneta.
    this.deps.ledger.incrementStep(this.runId);
    this.appendSafe({ kind, payload, causedByRunSeq: cause, idemKey: cmd.idemKey });

    // Koncni status ni ZGOLJ dogodek v dnevniku: mora odpreti pot v runs.status,
    // da se tekoce zanke ne vrti v neskoncnost od dogodka do dogodka.
    if (kind === 'run.completed') this.deps.ledger.setStatus(this.runId, 'completed');
    else if (kind === 'run.stuck') this.deps.ledger.setStatus(this.runId, 'stuck');
    else if (kind === 'run.aborted') this.deps.ledger.setStatus(this.runId, 'aborted');
  }

  private async memoryStore(cmd: Extract<Command, { type: 'memory.store' }>, cause: number): Promise<boolean> {
    try {
      await this.deps.memory.remember(cmd.entry);
      this.writeStep(cmd, cause, 'memory.stored', { key: cmd.entry.key });
    } catch {
      this.writeStep(cmd, cause, 'memory.degraded', { backend: 'memory', code: 'EUNKNOWN' });
    }
    return false;
  }

  private async memoryRecall(cmd: Extract<Command, { type: 'memory.recall' }>, cause: number): Promise<boolean> {
    let hits: MemoryHit[];
    try {
      hits = await this.deps.memory.recall(cmd.query);
    } catch {
      this.writeStep(cmd, cause, 'memory.degraded', { backend: 'memory', code: 'EUNKNOWN' });
      return false;
    }
    // memory.recalled je akcionablen: sprozil bo novo redukcijo.
    this.appendSafe({
      kind: 'memory.recalled', payload: { query: cmd.query, hits },
      causedByRunSeq: cause, idemKey: cmd.idemKey,
    });
    return false;
  }

  private async llmComplete(cmd: Extract<Command, { type: 'llm.complete' }>, cause: number): Promise<boolean> {
    const { llm, ledger, provider, model } = this.deps;
    const ask = cmd.ask;

    // Zapakiraj agentov CompletionAsk v CompletionRequest: provider in model sta
    // znana le tu (klicatelj ju je vtisnil v deps), agent ju nikoli ne vidi.
    const completable = {
      provider,
      model,
      messages: ask.messages,
      temperature: ask.temperature,
      maxTokens: ask.maxTokens,
      attempt: ask.attempt,
    };
    const reqHash = requestHash(completable);

    // Zahtevo zapisemo VEDNO (tudi ob cache zadetku): je del dnevnika in determinizma.
    const requested = this.appendSafe({
      kind: 'llm.requested',
      payload: { provider, model, attempt: ask.attempt, reqHash },
      causedByRunSeq: cause,
      idemKey: `${cmd.idemKey}:request`,
    });
    const reqRunSeq = requested?.runSeq ?? cause;

    // Idempotenca na rezultatu: ce odgovor ali napaka ze obstajata, ne izvajamo
    // omreznega klica ponovno (replay z istim idemKey nastane ob nadaljevanju teka).
    const existing = ledger
      .read(this.runId)
      // Samo USPEH preskocimo; stale `:failed` omogoca, da ponovni zagon retry-ja
      // (pozacana omrezna napaka / timeout) in z njim ne ostane na mrtvi tocki.
      .find((e) => e.idemKey === `${cmd.idemKey}:respond`);
    if (existing) return false;

    // LLM-retry: pozacani omrezni/rate neuspehi (ENETWORK, ERATE) so pogosti pri
    // lokalnih modelih. Enkrat poskusimo z attempt+1 (nov cache kljuc), preden
    // obstane kot llm.failed. Preostala napaka (EAUTH/EUNKNOWN) pade takoj.
    let result;
    const tryAttempt = async (attempt: number): Promise<CompletionResult | null> => {
      try {
        return await llm.complete({ ...completable, attempt });
      } catch (err) {
        const code = llmCode(err);
        if (attempt === 0 && (code === 'ENETWORK' || code === 'ERATE')) {
          return tryAttempt(attempt + 1);
        }
        this.appendSafe({
          kind: 'llm.failed',
          payload: { provider, model, attempt, code },
          causedByRunSeq: reqRunSeq,
          idemKey: `${cmd.idemKey}:failed`,
        });
        return null;
      }
    };
    result = await tryAttempt(ask.attempt);
    if (!result) return false; // tryAttempt je ze zapisal llm.failed.

    this.appendSafe({
      kind: 'llm.responded',
      payload: {
        text: result.text,
        promptTokens: result.usage.promptTokens,
        completionTokens: result.usage.completionTokens,
        usdMicros: result.usage.usdMicros,
        cached: result.cached,
      },
      causedByRunSeq: reqRunSeq,
      idemKey: `${cmd.idemKey}:respond`,
    });
    return false;
  }

  private async fsWrite(cmd: Extract<Command, { type: 'fs.write' }>, cause: number): Promise<boolean> {
    let bytes: Uint8Array;
    try {
      bytes = await this.deps.fs.write(cmd.path, cmd.content);
    } catch (err) {
      this.writeStep(cmd, cause, 'fs.failed', { path: cmd.path, code: fsCode(err) });
      return false;
    }
    this.appendSafe({
      kind: 'artifact.written',
      payload: { path: cmd.path, sha256: sha256Bytes(bytes), bytes: bytes.length },
      causedByRunSeq: cause,
      idemKey: cmd.idemKey,
    });
    return true;
  }

  private async execCommand(
    cmd: Extract<Command, { type: 'cmd.exec' }>,
    cause: number,
  ): Promise<boolean> {
    const { ledger, exec } = this.deps;
    const cwd = posixRelative(cmd.cwd ?? '.');
    const timeoutMs = Math.min(cmd.timeoutMs ?? LIMITS.maxExecTimeoutMs, LIMITS.maxExecTimeoutMs);

    // Arhiviranje dovoljuje odsotnost vticnika (npr. --no-verify/demo).
    if (!exec || this.deps.execDisabled) {
      this.appendSafe({
        kind: 'exec.failed',
        payload: { argv: cmd.argv, cwd, code: 'EACCES', reason: 'izvajanje je onemogoceno' },
        causedByRunSeq: cause,
        idemKey: `${cmd.idemKey}:failed`,
      });
      return false;
    }

    // VARNOSTNA ZAVESA (v runnerju, ne agentu).
    const allow = this.deps.execAllow ?? DEFAULT_EXEC_ALLOW;
    const prog = (cmd.argv[0] ?? '').toLowerCase();
    if (!(allow as readonly string[]).includes(prog) || !cwdSafe(this.deps.execCwdRoot, cwd)) {
      this.appendSafe({
        kind: 'exec.failed',
        payload: { argv: cmd.argv, cwd, code: 'EACCES', reason: `ukaz '${prog}' ni dovoljen` },
        causedByRunSeq: cause,
        idemKey: `${cmd.idemKey}:failed`,
      });
      this.writeStep(cmd, cause, 'step.completed', {});
      return false;
    }

    // Zahtevo zabelezimo (je del dnevnika in determinizma).
    this.appendSafe({
      kind: 'exec.requested',
      payload: { argv: cmd.argv, cwd, timeoutMs },
      causedByRunSeq: cause,
      idemKey: `${cmd.idemKey}:request`,
    });

    // IDEMPOTENCA/REPLAY: rezultat ze v dnevniku? Ne izvedi ponovno.
    const existing = ledger
      .read(this.runId)
      .find((e) => e.idemKey === `${cmd.idemKey}:ran` || e.idemKey === `${cmd.idemKey}:failed`);
    if (existing) return false;

    // Env-filter: posredujemo le izbrane kljuce (ne poljubnega env modela).
    const allowedEnv: Record<string, string> = {};
    for (const k of ALLOWED_ENV_KEYS) {
      if (cmd.env?.[k]) allowedEnv[k] = cmd.env[k];
    }

    let res;
    try {
      res = await exec.run({ argv: cmd.argv, cwd: this.absCwd(cwd), timeoutMs, env: allowedEnv });
    } catch (err) {
      this.appendSafe({
        kind: 'exec.failed',
        payload: { argv: cmd.argv, cwd, code: 'EUNKNOWN', reason: String(err) },
        causedByRunSeq: cause,
        idemKey: `${cmd.idemKey}:failed`,
      });
      this.writeStep(cmd, cause, 'step.completed', {});
      return false;
    }

    const payload: ExecRanPayload = {
      exit: res.code,
      signal: res.signal,
      timedout: res.timedout,
      stdout: truncate(res.stdout, LIMITS.maxCapturedChars),
      stderr: truncate(res.stderr, LIMITS.maxCapturedChars),
      cwd,
    };
    this.appendSafe({
      kind: 'exec.ran',
      payload,
      causedByRunSeq: cause,
      idemKey: `${cmd.idemKey}:ran`,
    });
    this.writeStep(cmd, cause, 'step.completed', {});
    return res.code === 0;
  }

  private async readFile(
    cmd: Extract<Command, { type: 'cmd.read' }>,
    cause: number,
  ): Promise<boolean> {
    const { ledger, fs } = this.deps;
    this.writeStep(cmd, cause, 'step.completed', {});
    let content: Uint8Array;
    try {
      content = await fs.read(cmd.path);
    } catch (err) {
      this.appendSafe({
        kind: 'fs.failed', payload: { path: cmd.path, code: fsCode(err) },
        causedByRunSeq: cause, idemKey: `${cmd.idemKey}:failed`,
      });
      return false;
    }
    this.appendSafe({
      kind: 'read.obtained',
      payload: { path: cmd.path, content: truncate(new TextDecoder().decode(content), LIMITS.maxCapturedChars) },
      causedByRunSeq: cause,
      idemKey: cmd.idemKey,
    });
    return true;
  }

  /** Absolutna pot za izvajanje: koren + relativna cwd. */
  private absCwd(rel: string): string {
    return this.deps.execCwdRoot ? `${this.deps.execCwdRoot}/${rel}` : rel;
  }

  // ─── koncni statusi ─────────────────────────────────────────────────────────

  private declareStuck(reason: string): Promise<void> {
    const { ledger } = this.deps;
    return Promise.resolve().then(() => {
      this.appendSafe({
        actor: 'runner', kind: 'run.stuck', payload: { reason },
        causedByRunSeq: 0, idemKey: `runner:run.stuck:${this.runId}`,
      });
      ledger.setStatus(this.runId, 'stuck');
    });
  }

  private snapshot(): RunOutcome {
    const { ledger } = this.deps;
    const run = ledger.getRun(this.runId)!;
    const artifacts = ledger
      .read(this.runId)
      .filter((e) => e.kind === 'artifact.written')
      .map((e) => (e.payload as { path: string }).path);
    const end = ledger.read(this.runId).findLast(
      (e) => e.kind === 'run.completed' || e.kind === 'run.stuck' || e.kind === 'run.aborted',
    );
    return {
      runId: this.runId,
      status: run.status as RunOutcome['status'],
      reason: end ? (end.payload as { reason: string }).reason : `status ${run.status}`,
      stepsUsed: run.stepsUsed,
      spendMicros: run.spendMicros,
      artifactPath: artifacts[0] ?? null,
      artifactPaths: artifacts,
    };
  }

  // ─── varnost zapisov / idempotenca ──────────────────────────────────────────

  /** Zapise dogodek; ze-obstojeci `idemKey` je uspeh, ne napaka. */
  private appendSafe(ev: {
    actor?: 'runner' | 'human';
    kind: EventKind;
    payload: unknown;
    causedByRunSeq: number;
    idemKey: string;
  }): Event | null {
    const { ledger } = this.deps;
    try {
      return ledger.append({
        runId: this.runId,
        actor: ev.actor ?? 'runner',
        kind: ev.kind,
        payload: ev.payload,
        causedByRunSeq: ev.causedByRunSeq,
        idemKey: ev.idemKey,
      });
    } catch (err) {
      if (err instanceof DuplicateIdemKeyError) return null; // ze narejeno
      throw err;
    }
  }
}

/** Normalizira napako datotečnega sistema (FS) v kodo staleža. */
function fsCode(err: unknown): FailureCode {
  const msg = String((err as Error)?.message ?? err).toLowerCase();
  if (msg.includes('no such file')) return 'ENOENT';
  if (msg.includes('permission') || msg.includes('eacces')) return 'EACCES';
  return 'EUNKNOWN';
}

/** Normalizira napako LLM v kodo staleža. Isto logiko kot openai-compatible. */
function llmCode(err: unknown): FailureCode {
  // Ponudnik ze normalizira napako skozi TypeError ali LastError; tu damo varnostni privzetek.
  const code = (err as { code?: FailureCode })?.code;
  if (code) return code;
  const msg = String((err as Error)?.message ?? '').toLowerCase();
  if (msg.includes('network')) return 'ENETWORK';
  if (msg.includes('auth') || msg.includes('401') || msg.includes('403')) return 'EAUTH';
  if (msg.includes('rate') || msg.includes('429')) return 'ERATE';
  return 'EUNKNOWN';
}

