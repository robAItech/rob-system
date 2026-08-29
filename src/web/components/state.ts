// src/web/components/state.ts — stanja panelov (loading/error/empty/data).
// Neskončen "nalaganje …" je bug, ne stanje: vsak panel ima jasno stanje.

export type PanelState = 'loading' | 'error' | 'empty' | 'data';

export function setPanelState(
  el: HTMLElement | null,
  state: PanelState,
  msg?: string,
  onRetry?: () => void,
): void {
  if (!el) return;
  if (state === 'loading') {
    el.innerHTML = `<div class="panel-state"><span class="spinner"></span> nalaganje …</div>`;
  } else if (state === 'error') {
    el.innerHTML = `<div class="panel-state err">⚠️ ${msg || 'Napaka pri nalaganju'}` +
      (onRetry ? ` <button class="btn mini" id="st-retry">Ponovi</button>` : '') + `</div>`;
    if (onRetry) {
      const b = el.querySelector('#st-retry');
      if (b) b.addEventListener('click', onRetry);
    }
  } else if (state === 'empty') {
    el.innerHTML = `<div class="panel-state">${msg || 'Ni podatkov'}</div>`;
  }
  // state === 'data' → klicatelj renderira vsebino sam.
}
