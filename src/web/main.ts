// src/web/main.ts — Command Center v2: modularna vstopna točka.
// Boot check (/api/me) → login overlay, če ni seje; šele nato data init.
import { fetchFleet, fetchMetrics, getJSON, setUnauthorizedHandler, auth, isSessionExpired } from './api';
import { renderFleet } from './components/fleet';
import { connectFeed } from './components/feed';
import { renderKpis, recordSample } from './components/kpis';
import { setPanelState } from './components/state';
import { initChat } from './components/chat';
import { initAgenda } from './components/agenda';
import { initGraph } from './components/graph';
import type { EventLine } from '../shared/types';

function ready(fn: () => void): void {
  if (document.readyState !== 'loading') fn();
  else document.addEventListener('DOMContentLoaded', fn);
}

ready(() => {
  const overlay = document.getElementById('login-overlay');
  const loginBtn = document.getElementById('login-btn') as HTMLButtonElement | null;
  const loginInput = document.getElementById('login-token') as HTMLInputElement | null;
  const loginMsg = document.getElementById('login-msg') as HTMLDivElement | null;

  const showLogin = (msg?: string): void => {
    if (!overlay) return;
    overlay.classList.remove('hidden');
    if (msg && loginMsg) loginMsg.textContent = msg;
  };
  // Globalni 401 interceptor — če seja poteče med delom, prikaži login.
  setUnauthorizedHandler(() => showLogin('Seja je potekla ali ni veljavna — prijavi se.'));

  const startApp = (): void => {
    const fleetEl = document.getElementById('fleet-body');
    const feedEl = document.getElementById('feed');
    const dotEl = document.getElementById('sse-dot');

    // KPI — realni podatki + trend (delta, sparkline).
    const loadKpis = () => fetchMetrics()
      .then(m => { recordSample(m); renderKpis(m); })
      .catch(() => { /* 401 → interceptor prikaže login */ });
    loadKpis();
    setInterval(loadKpis, 15000);

    // Fleet ops panel — state machine: loading → data | error | empty.
    const loadFleet = (): void => {
      if (!fleetEl) return;
      setPanelState(fleetEl, 'loading');
      fetchFleet()
        .then(d => {
          if (isSessionExpired()) return;             // login overlay že pokrit
          if (!d?.ok || !d.agenda) { setPanelState(fleetEl, 'error', 'Napačen odziv serverja', loadFleet); return; }
          if (!Object.keys(d.workers || {}).length && !d.activity?.length) {
            setPanelState(fleetEl, 'empty', 'Ni aktivnih workerjev (master / standalone)');
            renderFleet(fleetEl, d);                  // vseeno pokaži spomin/backup
            return;
          }
          renderFleet(fleetEl, d);
        })
        .catch(() => { if (!isSessionExpired()) setPanelState(fleetEl, 'error', 'Master ni dosegljiv', loadFleet); });
    };
    loadFleet();
    setInterval(loadFleet, 15000);

    // SSE živi tok — seed zadnjih iz /api/events, nato živo.
    if (feedEl) {
      getJSON<{ ok: boolean; events: EventLine[] }>('/api/events')
        .then(r => connectFeed(feedEl, dotEl, () => { /* */ }, r.events || []))
        .catch(() => connectFeed(feedEl, dotEl, () => { /* */ }));
    }

    // Pogovor + Agenda + Graf.
    initChat();
    initAgenda();
    initGraph();

    // Navigacija.
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
  };

  // Boot check: /api/me → 200 = prijavljen; 401 = login.
  fetch('/api/me').then(r => {
    if (r.ok) startApp();
    else showLogin();
  }).catch(() => showLogin());

  // Login.
  if (loginBtn && loginInput) {
    const doLogin = async (): Promise<void> => {
      const t = loginInput.value.trim();
      if (!t) return;
      const ok = await auth(t);
      if (ok) {
        location.reload();   // zdaj s session cookie → startApp
      } else if (loginMsg) {
        loginMsg.textContent = 'Napačen token. Preveri ROB_API_TOKEN v .env.';
      }
    };
    loginBtn.addEventListener('click', doLogin);
    loginInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
  }
});
