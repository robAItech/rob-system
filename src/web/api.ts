// src/web/api.ts — tipiziran API client (server.ts kontrakt iz shared/types).
import type { FleetStatus, SystemMetrics, AgendaCounts } from '../shared/types';

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`HTTP ${r.status} — ${path}`);
  return r.json() as Promise<T>;
}

export const fetchFleet = () => getJSON<FleetStatus>('/api/fleet');
export const fetchMetrics = () => getJSON<SystemMetrics>('/api/metrics');

export interface AgendaResponse { ok: boolean; items: Array<Record<string, unknown>>; }
export const fetchAgenda = () => getJSON<AgendaResponse>('/api/agenda');

// Human-readable starost iz unix timestampa.
export function ageAgo(ts?: number): string {
  if (!ts) return '—';
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 90) return 'zdaj';
  if (s < 3600) return `pred ${(s / 60 | 0)} min`;
  return `pred ${(s / 3600 | 0)} h`;
}
