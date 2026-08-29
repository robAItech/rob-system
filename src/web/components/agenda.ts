// src/web/components/agenda.ts — Agenda pogled (čakalna vrsta naročil).
import type { AgendaItem } from '../../shared/types';
import { getJSON } from '../api';

// Unix ts (s) → "dd.mm HH:MM".
function fmtTime(ts?: number): string {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm} ${hh}:${mi}`;
}

// Trajanje izvedbe (s) → "1m 23s" | "42s".
function fmtDur(s?: number): string {
  if (!s && s !== 0) return '';
  if (s < 60) return `${Math.round(s)}s`;
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${m}m ${r}s`;
}

export function initAgenda(): void {
  const list = document.getElementById('agenda-list');
  const input = document.getElementById('agenda-input') as HTMLInputElement | null;
  const addBtn = document.getElementById('agenda-add');
  if (!list) return;

  const statusClass = (s: string): string =>
    s === 'done' ? 's-ok' : s === 'failed' ? 's-crit' : s === 'running' ? 's-run' : 's-warn';

  const render = (items: AgendaItem[]): void => {
    if (!items.length) { list.innerHTML = '<div class="agenda-empty">Agenda je prazna — dodaj nalogo.</div>'; return; }
    // Zadnje naročilo na vrhu: sortiraj po času nastanka (padajoče).
    const sorted = [...items].sort((a, b) => {
      const at = a.created_at ?? a.updated_at ?? 0;
      const bt = b.created_at ?? b.updated_at ?? 0;
      return bt - at;
    });
    list.innerHTML = sorted.map(it => {
      const claimed = it.claimed_by ? ` · ${it.claimed_by}` : '';
      const worker = it.result_worker ? ` · → ${it.result_worker}` : '';
      // Čas zadnje spremembe + trajanje izvedbe (worker zapiše ob končanju).
      const when = fmtTime(it.updated_at);
      const dur = it.duration_s ? ` · ${fmtDur(it.duration_s)}` : '';
      return `<div class="agenda-item" data-id="${it.id}">
        <div class="agenda-top"><span class="s ${statusClass(it.status)}">${it.status}</span>
          <span class="agenda-target">${it.target || ''}${claimed}${worker}</span>
          <span class="agenda-time">${when}${dur}</span>
          <button class="agenda-del" data-del="${it.id}" title="Odstrani">✕</button>
        </div>
        <div class="agenda-goal">${String(it.goal || '').replace(/</g, '&lt;')}</div>
      </div>`;
    }).join('');
    list.querySelectorAll<HTMLButtonElement>('[data-del]').forEach(b => {
      b.addEventListener('click', () => {
        fetch('/api/agenda/delete', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: b.dataset.del }),
        }).then(load);
      });
    });
  };

  const load = (): void => {
    getJSON<{ ok: boolean; items: AgendaItem[] }>('/api/agenda')
      .then(r => render(r.items || [])).catch(() => { /* */ });
  };

  const add = (): void => {
    const goal = input?.value.trim() ?? '';
    if (!goal) return;
    fetch('/api/agenda', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal, kind: 'python' }),
    }).then(() => { if (input) input.value = ''; load(); });
  };

  if (addBtn) addBtn.addEventListener('click', add);
  if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') add(); });

  load();
  setInterval(load, 15000);
}
