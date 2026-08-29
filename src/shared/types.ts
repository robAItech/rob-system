// src/shared/types.ts — DELJENI tipi med server.ts in web clientom.
// Contract safety: server in client importata iste tipe → ni shape-mismatch-a
// (razred napak, ki je prej povzročil "fleet panel nalaganje …").

export interface EventLine {
  t: string;   // "HH:MM:SS"
  s: string;   // status label: TASK | TICK | CLAIM | RESULT | …
  c: string;   // css class: s-ok | s-crit | s-run | s-warn
  m: string;   // message
}

export interface AgendaCounts {
  pending: number;
  running: number;
  done: number;
  failed: number;
  total: number;
}

export interface FleetWorker {
  last_seen?: number;
  tasks?: unknown[];
}

export interface FleetStatus {
  ok: boolean;
  workers: Record<string, FleetWorker>;
  agenda: AgendaCounts;
  memory: Record<string, number>;
  backup: { backed_up_at?: number | null };
  activity: EventLine[];
  daemon: { state: string | null; heartbeat_ts?: number | null; current_tasks?: unknown | null };
}

export interface SystemMetrics {
  tasks?: number;
  errors?: number;
  nodes?: number;
  llmOnline?: boolean;
}

export interface LiveEvent {
  type: string;          // connected | heartbeat | event
  ts?: number;
  event?: EventLine;     // type === 'event'
}

export interface AgendaItem {
  id: string;
  goal: string;
  target?: string;
  kind?: string;
  status: string;
  claimed_by?: string;
  result_worker?: string;
  created_at?: number;
  updated_at?: number;
  duration_s?: number;   // čas izvedbe (worker zapiše ob končanju)
}

export interface ChatReply {
  ok: boolean;
  reply?: string;
  error?: string;
}
