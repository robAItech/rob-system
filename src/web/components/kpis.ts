// src/web/components/kpis.ts — KPI vrstica (realni podatki, nič hardcoded).
import type { SystemMetrics } from '../../shared/types';

function setVal(id: string, v: number | string | undefined): void {
  const el = document.getElementById(id);
  if (el) el.textContent = (v === undefined || v === null) ? '—' : String(v);
}

export function renderKpis(m: SystemMetrics): void {
  setVal('kpi-tasks', m.tasks);
  setVal('kpi-errors', m.errors);
  setVal('kpi-nodes', m.nodes);
}
