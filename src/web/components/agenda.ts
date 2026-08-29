// src/web/components/agenda.ts — Agenda pogled (čakalna vrsta naročil).
// Klik na nalogo → kartica (modal) s shranjenimi datotekami/mapami (prenos).
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

function fmtBytes(n: number): string {
  if (!n) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1048576) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}

function escapeHtml(s: string): string {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

interface FilesResp {
  ok: boolean;
  id?: string;
  target?: string;
  goal?: string;
  status?: string;
  root?: string;
  files: Array<{ path: string; dir: boolean; size: number; mtime: number }>;
}

export function initAgenda(): void {
  const list = document.getElementById('agenda-list');
  const input = document.getElementById('agenda-input') as HTMLInputElement | null;
  const addBtn = document.getElementById('agenda-add');
  if (!list) return;

  // ---- Kartica (modal) — shranjene datoteke naloge. ----
  const modal = document.getElementById('agenda-modal');
  const closeCard = (): void => { modal?.classList.add('hidden'); };
  document.getElementById('am-close')?.addEventListener('click', closeCard);
  modal?.addEventListener('click', (e) => { if (e.target === modal) closeCard(); });

  const renderFiles = (res: FilesResp, it: AgendaItem): void => {
    const files = document.getElementById('am-files');
    const rootEl = document.getElementById('am-root');
    if (!files) return;
    if (rootEl) rootEl.textContent = res.root ? `📁 ${res.root}` : '';
    const items = res.files || [];
    if (!items.length) {
      files.innerHTML = `<div class="am-empty">Ni shranjenih datotek — mapa <b>actions/${escapeHtml(it.target || '')}</b> je prazna ali ne obstaja.</div>`;
      return;
    }
    const dlAll = document.getElementById('am-dl-all');
    if (dlAll) dlAll.style.display = '';
    files.innerHTML = items.map(f => {
      const depth = f.path.split('/').length - 1;
      const indent = `style="padding-left:${depth * 16}px"`;
      if (f.dir) return `<div class="am-dir" ${indent}>📁 ${escapeHtml(f.path)}</div>`;
      const href = `/api/agenda/download?id=${encodeURIComponent(it.id)}&file=${encodeURIComponent(f.path)}`;
      return `<a class="am-file" ${indent} href="${href}" download title="${escapeHtml(f.path)}">
        <span>📄 ${escapeHtml(f.path)}</span><span class="am-size">${fmtBytes(f.size)}</span></a>`;
    }).join('');
  };

  const openCard = (it: AgendaItem): void => {
    const title = document.getElementById('am-title');
    const meta = document.getElementById('am-meta');
    const files = document.getElementById('am-files');
    const rootEl = document.getElementById('am-root');
    const dlAll = document.getElementById('am-dl-all') as HTMLAnchorElement | null;
    if (!modal) return;
    if (title) title.textContent = `Naloga · ${it.status}`;
    if (meta) meta.innerHTML =
      `<span><b>cilj:</b> ${escapeHtml(it.target || '—')}</span>` +
      `<span><b>izvedba:</b> ${fmtDur(it.duration_s) || '—'}</span>` +
      `<span><b>sprememba:</b> ${fmtTime(it.updated_at)}</span>`;
    if (rootEl) rootEl.textContent = '';
    if (files) files.innerHTML = '<span class="muted">nalaganje …</span>';
    if (dlAll) { dlAll.style.display = 'none'; dlAll.href = `/api/agenda/download-all?id=${encodeURIComponent(it.id)}`; }
    modal.classList.remove('hidden');
    getJSON<FilesResp>(`/api/agenda/files?id=${encodeURIComponent(it.id)}`)
      .then(res => renderFiles(res, it))
      .catch(() => { if (files) files.innerHTML = '<div class="am-empty">Datoteke niso na voljo.</div>'; });
  };

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
      return `<div class="agenda-item" data-id="${it.id}" title="Klikni za shranjene datoteke">
        <div class="agenda-top"><span class="s ${statusClass(it.status)}">${it.status}</span>
          <span class="agenda-target">${it.target || ''}${claimed}${worker}</span>
          <span class="agenda-time">${when}${dur}</span>
          <button class="agenda-del" data-del="${it.id}" title="Odstrani">✕</button>
        </div>
        <div class="agenda-goal">${String(it.goal || '').replace(/</g, '&lt;')}</div>
      </div>`;
    }).join('');
    // ✕ (odstrani) ne sme odpreti kartice.
    list.querySelectorAll<HTMLButtonElement>('[data-del]').forEach(b => {
      b.addEventListener('click', (e) => {
        e.stopPropagation();
        fetch('/api/agenda/delete', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: b.dataset.del }),
        }).then(load);
      });
    });
    // Klik na nalogo → kartica s shranjenimi datotekami.
    list.querySelectorAll<HTMLElement>('.agenda-item').forEach(el => {
      el.addEventListener('click', () => {
        const it = sorted.find(x => x.id === el.dataset.id);
        if (it) openCard(it);
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
