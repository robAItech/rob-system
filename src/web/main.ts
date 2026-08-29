// src/web/main.ts — Command Center v2: modularna vstopna točka.
// Bun build → src/web/dist/bundle.js; server.ts služi /command.
import { fetchFleet, fetchMetrics, getJSON } from './api';
import { renderFleet } from './components/fleet';
import { connectFeed } from './components/feed';
import { renderKpis, recordSample } from './components/kpis';
import { initChat } from './components/chat';
import { initAgenda } from './components/agenda';
import { initGraph } from './components/graph';
import type { EventLine } from '../shared/types';

function ready(fn: () => void): void {
  if (document.readyState !== 'loading') fn();
  else document.addEventListener('DOMContentLoaded', fn);
}

ready(() => {
  const fleetEl = document.getElementById('fleet-body');
  const feedEl = document.getElementById('feed');
  const dotEl = document.getElementById('sse-dot');

  // KPI — realni podatki iz /api/metrics + trend (delta, sparkline).
  const loadKpis = () => fetchMetrics()
    .then(m => { recordSample(m); renderKpis(m); })
    .catch(() => { /* */ });
  loadKpis();
  setInterval(loadKpis, 15000);

  // Fleet ops panel — /api/fleet.
  const loadFleet = () => fetchFleet().then(d => fleetEl && renderFleet(fleetEl, d)).catch(() => { /* */ });
  loadFleet();
  setInterval(loadFleet, 15000);

  // SSE živi tok dogodkov — najprej seed zadnjih iz /api/events, nato živo.
  if (feedEl) {
    getJSON<{ ok: boolean; events: EventLine[] }>('/api/events')
      .then(r => connectFeed(feedEl, dotEl, () => { /* */ }, r.events || []))
      .catch(() => connectFeed(feedEl, dotEl, () => { /* */ }));
  }

  // Pogovor + Agenda + Graf (komponente).
  initChat();
  initAgenda();
  initGraph();

  // Navigacija med pogledi.
  document.querySelectorAll<HTMLButtonElement>('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const v = btn.dataset.view;
      document.querySelectorAll<HTMLElement>('[data-view-panel]').forEach(p => {
        p.classList.toggle('hidden', p.dataset.viewPanel !== v);
      });
    });
  });
});
