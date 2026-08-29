// src/web/components/agenda.ts — Agenda pogled (čakalna vrsta naročil).
import type { AgendaItem } from '../../shared/types';
import { getJSON } from '../api';

export function initAgenda(): void {
  const list = document.getElementById('agenda-list');
  const input = document.getElementById('agenda-input') as HTMLInputElement | null;
  const addBtn = document.getElementById('agenda-add');
  if (!list) return;

  const statusClass = (s: string): string =>
    s === 'done' ? 's-ok' : s === 'failed' ? 's-crit' : s === 'running' ? 's-run' : 's-warn';

  const render = (items: AgendaItem[]): void => {
    if (!items.length) { list.innerHTML = '<div class="agenda-empty">Agenda je prazna — dodaj nalogo.</div>'; return; }
    list.innerHTML = items.map(it => {
      const claimed = it.claimed_by ? ` · ${it.claimed_by}` : '';
      const worker = it.result_worker ? ` · → ${it.result_worker}` : '';
      return `<div class="agenda-item" data-id="${it.id}">
        <div class="agenda-top"><span class="s ${statusClass(it.status)}">${it.status}</span>
          <span class="agenda-target">${it.target || ''}${claimed}${worker}</span>
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
