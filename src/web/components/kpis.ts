// src/web/components/kpis.ts — KPI vrstica (realni podatki + trend).
// Zgodovina vzorcev → delta (▲/▼) + mini sparkline.
import type { SystemMetrics } from '../../shared/types';

export interface Sample { ts: number; tasks?: number; errors?: number; nodes?: number; }
// Ime kpiHistory — `history` v browserju kolidira z globalnim window.history!
const kpiHistory: Sample[] = [];

export function recordSample(m: SystemMetrics): void {
  kpiHistory.push({ ts: Date.now(), tasks: m.tasks, errors: m.errors, nodes: m.nodes });
  if (kpiHistory.length > 30) kpiHistory.shift();
}

function deltaStr(prev: number | undefined, cur: number | undefined): string {
  if (prev === undefined || cur === undefined || prev === cur) return '—';
  const d = cur - prev;
  return d > 0 ? `▲${d}` : `▼${Math.abs(d)}`;
}

function sparkline(vals: number[], color: string): string {
  if (vals.length < 2) return '';
  const w = 60, h = 18;
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = (max - min) || 1;
  const pts = vals.map((v, i) =>
    `${((i / (vals.length - 1)) * w).toFixed(1)},${(h - ((v - min) / range) * (h - 2) - 1).toFixed(1)}`).join(' ');
  return `<svg width="${w}" height="${h}"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
}

export function renderKpis(m: SystemMetrics): void {
  const prev = kpiHistory[kpiHistory.length - 2];
  const fields = [
    ['kpi-tasks', 'tasks', 'var(--gold)'],
    ['kpi-errors', 'errors', 'var(--bad)'],
    ['kpi-nodes', 'nodes', 'var(--accent)'],
  ] as const;
  for (const [id, key, color] of fields) {
    const el = document.getElementById(id);
    if (!el) continue;
    const val = m[key];
    el.innerHTML = (val === undefined || val === null)
      ? '—'
      : String(val) + `<span class="kpi-delta">${deltaStr(prev?.[key], val)}</span>`;
    const sp = document.getElementById(id + '-spark');
    if (sp) {
      sp.innerHTML = sparkline(
        kpiHistory.filter(s => s[key] !== undefined).map(s => s[key]!),
        color,
      );
    }
  }
}
