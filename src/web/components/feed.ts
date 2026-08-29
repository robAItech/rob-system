// src/web/components/feed.ts — SSE živi tok dogodkov (EventSource).
import type { EventLine, LiveEvent } from '../../shared/types';

export function connectFeed(
  feedEl: HTMLElement,
  dotEl: HTMLElement | null,
  onEvent: (e: EventLine) => void,
  seed: EventLine[] = [],
): void {
  const render = (events: EventLine[]): void => {
    feedEl.innerHTML = events.map(e =>
      `<div class="feed-line"><span class="t">${e.t}</span><span class="s ${e.c}">${e.s}</span><span class="m">${e.m}</span></div>`
    ).join('') || '<div class="feed-empty">čakam na dogodke …</div>';
  };
  const events: EventLine[] = [...seed];
  if (seed.length) render(events);

  let es: EventSource | null = null;
  try { es = new EventSource('/api/stream'); } catch { return; }
  es.onopen = () => { if (dotEl) dotEl.classList.add('live'); };
  es.onmessage = (ev) => {
    try {
      const d: LiveEvent = JSON.parse(ev.data);
      if (d.type === 'event' && d.event) {
        events.unshift(d.event);
        events.length = Math.min(events.length, 12);
        render(events);
        onEvent(d.event);
      }
    } catch { /* */ }
  };
  es.onerror = () => { /* EventSource sam reconnect-a */ };
}
