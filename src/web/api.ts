// src/web/api.ts — tipiziran API client (server.ts kontrakt iz shared/types).
import type { FleetStatus, SystemMetrics, AgendaCounts, FleetSecurityStatus } from '../shared/types';

let onUnauthorized: (() => void) | null = null;
let sessionExpired = false;

export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

export function isSessionExpired(): boolean {
  return sessionExpired;
}

export function resetSessionExpired(): void {
  sessionExpired = false;
}

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (r.status === 401) {
    sessionExpired = true;
    if (onUnauthorized) onUnauthorized();   // prikaži login
    throw new Error('unauthorized');
  }
  if (!r.ok) throw new Error(`HTTP ${r.status} — ${path}`);
  return r.json() as Promise<T>;
}

export function auth(token: string): Promise<boolean> {
  return fetch('/api/auth', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  }).then(r => r.ok).catch(() => false);
}

export const fetchFleet = () => getJSON<FleetStatus>('/api/fleet');
export const fetchMetrics = () => getJSON<SystemMetrics>('/api/metrics');

export interface AgendaResponse { ok: boolean; items: Array<Record<string, unknown>>; }
export const fetchAgenda = () => getJSON<AgendaResponse>('/api/agenda');

export const fetchFleetSecurity = () => getJSON<FleetSecurityStatus>('/api/fleet-security');

// Human-readable starost iz unix timestampa.
export function ageAgo(ts?: number): string {
  if (!ts) return '—';
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 90) return 'zdaj';
  if (s < 3600) return `pred ${(s / 60 | 0)} min`;
  return `pred ${(s / 3600 | 0)} h`;
}
