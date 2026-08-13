/**
 * hermes/types.ts — skupni tipi celotnega sistema.
 *
 * POMEMBNO: to je EDINA datoteka, ki jo smejo uvoziti agenti (`src/agents/*.ts`).
 * Zato tu ne sme biti nobene zmoznosti: nobenega uvoza, nobenega dostopa do `Bun`,
 * `fetch`, `process`, `Date` ali `Math.random`. Sam tipi in ciste konstante.
 * `tests/agent-purity.test.ts` to uveljavlja na ravni izvorne kode.
 */

// ─── identitete ──────────────────────────────────────────────────────────────

/** Vloge, ki jih lahko ima agent. Namenoma ozje od `Actor`. */
export type AgentRole =
  | 'architect'
  | 'engineer'
  | 'planner'
  | 'builder'
  | 'qa'
  | 'screenshot';

/** Kdorkoli lahko zapise dogodek: agent, runner ali clovek. */
export type Actor = AgentRole | 'runner' | 'human';

export type RunStatus = 'running' | 'completed' | 'stuck' | 'aborted';

// ─── dogodki ─────────────────────────────────────────────────────────────────

/**
 * Vse vrste dogodkov mejnika 1.
 *
 * `graph.*` je namenoma odsoten: graphify je v skeletu samo vmesnik brez izvedbe,
 * zato zanj ni ne ukaza ne dogodka. Vstopi sele, ko bo prvi resnicni tek pokazal,
 * da je izbira konteksta ozko grlo.
 */
export const ALL_EVENT_KINDS = [
  // zivljenjski cikel teka
  'run.started',
  'task.submitted',
  'step.completed',
  'run.completed',
  'run.stuck',
  'run.aborted',
  // agenti
  'decision.made',
  'agent.thought',
  // vticniki, uspeh
  'llm.requested',
  'llm.responded',
  'memory.stored',
  'memory.recalled',
  'artifact.written',
  // vticniki, neuspeh
  'llm.failed',
  'memory.degraded',
  'fs.failed',
  // vticniki, izvajanje (produktni generator)
  'exec.requested',
  'exec.ran',
  'exec.failed',
  // plan / delo / odlocitve QA
  'plan.submitted',
  'read.obtained',
  'qa.decision',
] as const;

/**
 * Izpeljano iz `ALL_EVENT_KINDS`, da `CHECK` omejitev v SQL ne more odplavati od tipa.
 * Dodaj vrsto na enem mestu in oboje ostane usklajeno.
 */
export type EventKind = (typeof ALL_EVENT_KINDS)[number];

export const ALL_ACTORS = [
  'architect', 'engineer', 'planner', 'builder', 'qa', 'screenshot', 'runner', 'human',
] as const;
export const ALL_RUN_STATUSES = ['running', 'completed', 'stuck', 'aborted'] as const;

/**
 * Dogodki, ki se vrnejo v vrsto in jih agenti vidijo.
 *
 * Vse ostalo (`llm.requested`, `agent.thought`, `step.completed`, `memory.stored`,
 * `artifact.written`, `run.*`) je zgolj zapis in NE sprozi novega kroga redukcije.
 * Brez tega seznama se vrsta hrani sama in tek se nikoli ne ustavi.
 */
export const ACTIONABLE_KINDS: readonly EventKind[] = [
  'task.submitted',
  'decision.made',
  'llm.responded',
  'llm.failed',
  'memory.recalled',
  'plan.submitted',
  'exec.ran',
  'exec.failed',
  'read.obtained',
  'qa.decision',
] as const;

export interface Event {
  /** Globalno, monotono. NI del identitete in NI vkljuceno v `hashEvents`. */
  seq: number;
  /** NI vkljucen v `hashEvents`, ker se ob replayu in forku spremeni. */
  runId: string;
  /** Identiteta znotraj teka, od 0 naprej. Fork jo podeduje nespremenjeno. */
  runSeq: number;
  /** NI vkljucen v `hashEvents`, ker je stenska ura. */
  ts: string;
  actor: Actor;
  kind: EventKind;
  payload: unknown;
  /** Lokalno na tek. Globalni `seq` bi cez fork kazal v starsevski tek. */
  causedByRunSeq: number | null;
  idemKey: string;
}

/** Kar preda klicatelj. Ledger sam dodeli `seq`, `runSeq` in `ts`. */
export interface NewEvent {
  runId: string;
  actor: Actor;
  kind: EventKind;
  payload: unknown;
  causedByRunSeq: number | null;
  idemKey: string;
}

export interface RunMeta {
  stepBudget?: number;
  note?: string;
}

// ─── disciplina payloada ─────────────────────────────────────────────────────

/**
 * Payloadi so del `hashEvents`, zato ne smejo vsebovati nicesar nedeterministicnega:
 * brez casovnih zigov, brez absolutnih poti, brez identifikatorjev odgovora ponudnika,
 * brez plavajocih vejic za denar. Denar je v celih mikrodolarjih (1 USD = 1_000_000).
 * Poti so relativne in POSIX normalizirane. Napake so normalizirane kode, ne sporocila OS.
 */
export type FailureCode = 'EACCES' | 'ENOENT' | 'ENETWORK' | 'EAUTH' | 'ERATE' | 'EUNKNOWN';

export interface TaskSubmittedPayload { task: string }
export interface DecisionMadePayload { question: string; choice: string; rationale: string }
export interface ThoughtPayload { text: string }
export interface LLMRequestedPayload { provider: string; model: string; attempt: number; reqHash: string }
export interface LLMRespondedPayload {
  text: string;
  promptTokens: number;
  completionTokens: number;
  usdMicros: number;
  cached: boolean;
}
export interface LLMFailedPayload { provider: string; model: string; attempt: number; code: FailureCode }
export interface ArtifactWrittenPayload { path: string; sha256: string; bytes: number }
export interface FsFailedPayload { path: string; code: FailureCode }
export interface MemoryRecalledPayload { query: string; hits: MemoryHit[] }
export interface MemoryStoredPayload { key: string }
export interface MemoryDegradedPayload { backend: string; code: FailureCode }
export interface RunEndedPayload { reason: string }

// ─── vticnik: izvajanje / plan / QA (produktni generator) ───────────────────

/** Korak v workplanu, kot ga opise planner in ga izvaja builder+qa. */
export interface WorkStep {
  id: string;
  label: string;
  status: 'todo' | 'doing' | 'done' | 'failed';
  /** Relativna pot do glavnega artefakta koraka (npr. out/plan.md, app/main.ts). */
  path?: string;
  /** Ukaz(zi) preveritve, ki ga za to korak izvaja qa (argv). */
  verify?: string[];
}

export interface PlanSubmittedPayload {
  steps: WorkStep[];
}

/** Izhod izvedenega programa. Vsi deli so deterministični, dolgi izhod skrajsan. */
export interface ExecRanPayload {
  exit: number | null;
  signal: string | null;
  timedout: boolean;
  stdout: string;
  stderr: string;
  /** posixRelative normiliziran cwd, v katerem je tek izvedla. */
  cwd: string;
}

export interface ExecRequestedPayload {
  argv: string[];
  cwd: string;
  timeoutMs: number;
}

export interface ExecFailedPayload {
  argv: string[];
  cwd: string;
  code: FailureCode;
  reason: string;
}

export interface ReadObtainedPayload {
  path: string;
  content: string;
}

export type QaAction = 'verify' | 'fix' | 'retry' | 'complete' | 'skip';
export interface QaDecisionPayload {
  action: QaAction;
  /** Referenca koraka, na katerega se odlocitev nanaša. */
  which: string | null;
  reason: string;
}

// ─── vticnik: LLM ────────────────────────────────────────────────────────────

export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
}

/**
 * Kar agent ZNA povedati: vsebina vprasanja.
 *
 * Agent namenoma ne pozna ne ponudnika ne modela, ker bi za to moral brati okolje,
 * to pa je zmoznost, ki je cist reduktor nima. Runner ju doda in sestavi
 * `CompletionRequest`.
 */
export interface CompletionAsk {
  messages: ChatMessage[];
  temperature?: number;
  maxTokens?: number;
  /** Ponovni poskus je NOV kljuc predpomnilnika. Brez tega se zataknjen tek ne izvlece. */
  attempt: number;
}

export interface CompletionRequest extends CompletionAsk {
  /** Del zgoscene vrednosti. Sicer ista zahteva na DeepSeek in OpenAI trci. */
  provider: string;
  model: string;
}

export interface CompletionResult {
  text: string;
  usage: { promptTokens: number; completionTokens: number; usdMicros: number };
  cached: boolean;
}

export interface LLMProvider {
  readonly name: string;
  complete(req: CompletionRequest): Promise<CompletionResult>;
}

// ─── vticnik: spomin ─────────────────────────────────────────────────────────

export interface MemoryEntry { key: string; text: string; tags?: string[] }
export interface MemoryHit { key: string; text: string; score: number }

export interface MemoryStore {
  remember(entry: MemoryEntry): Promise<void>;
  recall(query: string, limit?: number): Promise<MemoryHit[]>;
  /** Nikoli ne vrze. Ob nedosegljivosti vrne `ok: false`. */
  health(): Promise<{ ok: boolean; backend: string; detail?: FailureCode }>;
}

// ─── vticnik: graf kode (samo rezervacija imena za mejnik 2) ─────────────────

export interface CodeGraph {
  index(root: string): Promise<{ files: number; symbols: number }>;
  relevant(task: string, limit?: number): Promise<{ path: string; score: number }[]>;
}

// ─── ukazi ───────────────────────────────────────────────────────────────────

/**
 * Skupna polja vsakega ukaza.
 *
 * `becauseOf` je izbirno pripisovanje vzroka. Brez njega runner privzame runSeq
 * sprozilnega dogodka, kar da zvezdo namesto verige. Agent, ki zapise artefakt
 * zaradi neke odlocitve, naj `becauseOf` nastavi na runSeq tiste odlocitve, sicer
 * `provenance()` ne more vrniti verige ideja -> odlocitev -> artefakt.
 */
interface CommandBase {
  idemKey: string;
  becauseOf?: number;
}

export type Command =
  | (CommandBase & { type: 'llm.complete'; ask: CompletionAsk })
  | (CommandBase & { type: 'memory.store'; entry: MemoryEntry })
  | (CommandBase & { type: 'memory.recall'; query: string })
  | (CommandBase & { type: 'fs.write'; path: string; content: string })
  | (CommandBase & { type: 'decision.record'; question: string; choice: string; rationale: string })
  | (CommandBase & { type: 'log.thought'; text: string })
  | (CommandBase & { type: 'run.complete'; reason: string })
  | (CommandBase & { type: 'run.declareStuck'; reason: string })
  // produktni generator: izvajanje in branje
  | (CommandBase & { type: 'cmd.exec'; argv: string[]; cwd?: string; env?: Record<string, string>; timeoutMs?: number })
  | (CommandBase & { type: 'cmd.read'; path: string; reason?: string })
  // produktni generator: načrt dela in odločitev QA (se zapiše v dnevnik)
  | (CommandBase & { type: 'plan.record'; steps: WorkStep[] })
  | (CommandBase & { type: 'qa.decide'; action: QaAction; which: string | null; reason: string });

// ─── stanje in agenti ────────────────────────────────────────────────────────

export interface RunState {
  runId: string;
  task: string | null;
  /** `runSeq` je tu zato, da ga agent lahko poda kot `becauseOf`. */
  decisions: { runSeq: number; question: string; choice: string; rationale: string }[];
  artifacts: { path: string; sha256: string }[];
  lastLLM: { runSeq: number; text: string } | null;
  /** Izpeljano iz stevila dogodkov `step.completed`, ne iz mutirane spremenljivke. */
  stepsUsed: number;
  eventsCount: number;
  finished: boolean;
  // produktni generator
  /** Nacrt dela, kot ga posreduje planner (plan.submitted). */
  workplan: WorkStep[];
  lastRead: { runSeq: number; path: string; content: string } | null;
  lastExec: {
    runSeq: number;
    kind: 'exit' | 'signal' | 'timedout' | 'error';
    code: number | null;
    stdout: string;
    stderr: string;
  } | null;
  /** Stevci stanj izvajanj; qa jih bere za omejevanje poskusov. */
  executionHealth: { exit: number; signal: number; timedout: number; error: number };
  qaLast: { runSeq: number; action: QaAction; which: string | null; reason: string } | null;
}

export interface Agent {
  readonly role: AgentRole;
  /** CISTA funkcija. Brez I/O, brez ure, brez nakljucja, brez branja okolja. */
  reduce(state: RunState, event: Event): Command[];
}

/**
 * Deterministicna izpeljava kljuca idempotence.
 *
 * Namenoma navaden niz in ne zgoscena vrednost: `Bun.CryptoHasher` bi bil zmoznost,
 * agenti pa je ne smejo imeti. Enolicnost znotraj teka zagotavlja `UNIQUE (run_id, idem_key)`.
 */
export function idemKeyFor(role: AgentRole, triggerRunSeq: number, commandIndex: number): string {
  return `${role}:${triggerRunSeq}:${commandIndex}`;
}
