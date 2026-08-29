// src/web/components/feed.ts — SSE živi tok dogodkov + higiena.
// Ob 401 ustavi reconnect (EventSource se ne sme neskončno vrteti); jasna
// sporočila: "ni dogodkov" / "prekinjeno" / "prijava potrebna".
import type { EventLine, LiveEvent } from '../../shared/types';
import { isSessionExpired } from '../api';

export function connectFeed(
  feedEl: HTMLElement,
  dotEl: HTMLElement | null,
  onEvent: (e: EventLine) => void,
  seed: EventLine[] = [],
): void {
  const events: EventLine[] = [...seed];

  const render = (): void => {
    feedEl.innerHTML = events.length
      ? events.map(e =>
          `<div class="feed-line"><span class="t">${e.t}</span><span class="s ${e.c}">${e.s}</span><span class="m">${e.m}</span></div>`
        ).join('')
      : '<div class="panel-state">Ni dogodkov še — čakam …</div>';
  };
  const setMsg = (html: string): void => { feedEl.innerHTML = html; };

  if (seed.length) render();
  else setMsg('<div class="panel-state"><span class="spinner"></span> povezujem …</div>');

  let es: EventSource | null = null;
  try { es = new EventSource('/api/stream'); } catch { setMsg('<div class="panel-state err">SSE ni podprt</div>'); return; }

  es.onopen = () => { if (dotEl) dotEl.classList.add('live'); };

  es.onmessage = (ev) => {
    try {
      const d: LiveEvent = JSON.parse(ev.data);
      if (d.type === 'event' && d.event) {
        events.unshift(d.event);
        events.length = Math.min(events.length, 12);
        render();
        onEvent(d.event);
      }
    } catch { /* neveljaven frame */ }
  };

  es.onerror = () => {
    if (isSessionExpired()) {
      // Seja je potekla → NE reconnect, jasno sporočilo.
      try { es?.close(); } catch { /* */ }
      if (dotEl) dotEl.classList.remove('live');
      setMsg('<div class="panel-state err">🔒 Povezava prekinjena — prijava potrebna.</div>');
      return;
    }
    // Začasna prekinitev → EventSource bo sam poskusil; pokaži stanje.
    if (dotEl) dotEl.classList.remove('live');
    if (!events.length) setMsg('<div class="panel-state err">Povezava prekinjena — poskušam znova …</div>');
  };
}
