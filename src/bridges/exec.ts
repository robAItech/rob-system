/**
 * bridges/exec.ts — zmogljivost izvajanja programov (produktni generator).
 *
 * Runner je edini uporabnik tega vticnika. Pogodba je ozka: sibi za spec
 * (argv + cwd + timeout) in vrne strukturiran izhod (exit/signal/stdout/stderr).
 * Vsa varnostna presoja (allowlist, cwd-root, env-filter) je v RUNNERJU — ta
 * vticnik je samo "rocica", ki pozeni proces.
 *
 * Determinizem: omejimo zajem stdout/stderr na `maxCapturedChars`, da payload
 * dogodka ostane skrajsan. Replay nikoli ne zažene procesa ponovno (vid. runner).
 */

/** Rezultat izvedenega programa, brez absolutnih poti in casov. */
export interface ExecResult {
  code: number | null;
  signal: string | null;
  timedout: boolean;
  stdout: string;
  stderr: string;
}

/** Specifikacija enega izvajanja. `cwd` je ABSOLUTNO (runner ga je ze odobril). */
export interface ExecSpec {
  argv: string[];
  cwd: string;
  timeoutMs: number;
  /** Okolje, ki ga v runnerju predhodno filtriramo in dopolnimo. */
  env?: Record<string, string>;
}

/** Pogodba vticnika. `liveExecs` je stevec rezivih izvajanj (replay test). */
export interface ExecLike {
  readonly liveExecs: number;
  run(spec: ExecSpec): Promise<ExecResult>;
}

/** Omeji niz na prvih n znakov. Uporabimo za skrajsanje stdout/stderr v payloadu. */
export function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return `${s.slice(0, n)}... (skrajsano, skupaj ${s.length} znakov)`;
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<string> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
  }
  return Buffer.concat(chunks).toString('utf8');
}

/** Resnicni izvajalec nad Bun.spawn + AbortSignal.timeout. */
export class BunExec implements ExecLike {
  liveExecs = 0;

  async run(spec: ExecSpec): Promise<ExecResult> {
    const { argv, cwd, timeoutMs, env } = spec;
    this.liveExecs += 1;
    const saneArgs = argv.filter((a) => a.length > 0);

    const signal = AbortSignal.timeout(timeoutMs);
    const child = Bun.spawn(saneArgs, {
      cwd,
      env: env as Record<string, string | undefined>,
      stdout: 'pipe',
      stderr: 'pipe',
      signal,
    });

    const [stdout, stderr] = await Promise.all([collect(child.stdout), collect(child.stderr)]);

    // Pocakamo na izhod procesa. signal.aborted pomeni, da je cas tekel - timeout.
    const code = await child.exited;
    const timedout = signal.aborted;
    return {
      code: timedout ? null : code ?? null,
      signal: timedout ? 'SIGTERM' : null,
      timedout,
      stdout,
      stderr,
    };
  }
}

/** Za teste: vticnik, ki nikoli ne izvede nic in vrne uspeh. */
export class NoopExec implements ExecLike {
  liveExecs = 0;
  async run(_spec: ExecSpec): Promise<ExecResult> {
    return { code: 0, signal: null, timedout: false, stdout: '', stderr: '' };
  }
}
