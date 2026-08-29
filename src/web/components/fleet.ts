// src/web/components/fleet.ts — Fleet ops komponenta.
import type { FleetStatus, EventLine } from '../../shared/types';
import { ageAgo } from '../api';

function memoryLabel(memory: Record<string, number>): string {
  return Object.entries(memory || {})
    .map(([k, v]) => `${k.replace(/_/g, ' ')} ${v}`)
    .join(' · ');
}

export function renderFleet(el: HTMLElement, d: FleetStatus): void {
  const { workers = {}, agenda = {} as FleetStatus['agenda'], memory = {}, backup = {}, daemon = {} } = d;
  const mem = memoryLabel(memory);
  const state = daemon?.state || '—';
  const backupAge = ageAgo(backup?.backed_up_at ?? undefined);
  const pending = (agenda.pending ?? 0), running = (agenda.running ?? 0);

  let html = `<div class="fleet-row"><span>agenda</span><b>${pending} čaka · ${running} teče</b></div>`;
  if (mem) html += `<div class="fleet-row"><span>spomin</span><span>${mem}</span></div>`;
  html += `<div class="fleet-row"><span>daemon</span><span>${state}</span></div>`;
  html += `<div class="fleet-row"><span>backup git</span><span>${backupAge}</span></div>`;

  const names = Object.keys(workers || {});
  if (names.length) {
    names.forEach(w => {
      const wd = workers[w] || {};
      html += `<div class="fleet-row"><span>● ${w}</span><span>${ageAgo(wd.last_seen)} · ${(wd.tasks || []).length} nalog</span></div>`;
    });
  } else {
    html += `<div class="fleet-row" style="color:var(--faint)">— ni aktivnih workerjev (master / standalone)</div>`;
  }

  const act: EventLine[] = d.activity || [];
  if (act.length) {
    html += `<div class="fleet-section">Zadnja aktivnost</div>` +
      act.map(a => `<div class="fleet-row slim"><span class="s ${a.c}">${a.s}</span><span class="m">${a.t} ${a.m}</span></div>`).join('');
  }
  el.innerHTML = html;
}
