// src/web/components/chief.ts — Chief of Staff pogled.
// Pokaže dnevno poročilo (.rob_ai/chief/latest.md) + naučene lekcije in omogoči
// popravek lastnika (POST /api/chief/correct → append_correction → lekcija).
// Varno renderiranje: ves tekst gredo skozi escapeHtml (nikoli raw innerHTML
// iz poročila — poročilo je lahko poljuben tekst).
import { getJSON } from '../api';

function escapeHtml(s: string): string {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

interface ChiefResp {
  ok: boolean;
  digest?: string;
  lessons?: Array<{ date?: string; lesson?: string }>;
  history?: Array<{ date?: string; ok?: number; failed?: number }>;
}

/** Lahka, varna pretvorba markdown vrstic poročila v HTML (naslovi/kulice). */
function mdToSafeHtml(md: string): string {
  const out: string[] = [];
  for (const raw of md.split('\n')) {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { out.push('<div class="chief-gap"></div>'); continue; }
    const h2 = line.match(/^##\s+(.*)$/);
    if (h2) { out.push(`<h4>${escapeHtml(h2[1])}</h4>`); continue; }
    const h1 = line.match(/^#\s+(.*)$/);
    if (h1) { out.push(`<h3>${escapeHtml(h1[1])}</h3>`); continue; }
    if (/^\s*[-*]\s+/.test(line)) {
      out.push(`<div class="chief-li">• ${escapeHtml(line.replace(/^\s*[-*]\s+/, ''))}</div>`);
      continue;
    }
    out.push(`<div>${escapeHtml(line)}</div>`);
  }
  // Odstrani markdown **poudarek** (ne znašamo ga v obliki — samo čist tekst).
  return out.join('\n').replace(/\*\*/g, '');
}

export function initChief(): void {
  const digestEl = document.getElementById('chief-digest');
  const metaEl = document.getElementById('chief-meta');
  const input = document.getElementById('chief-input') as HTMLInputElement | null;
  const sendBtn = document.getElementById('chief-send');
  const msgEl = document.getElementById('chief-msg');
  if (!digestEl) return;

  const render = (r: ChiefResp): void => {
    if (metaEl) {
      const n = (r.lessons || []).length;
      metaEl.textContent = n ? `naučeno: ${n} lekcij` : 'dnevno poročilo';
    }
    if (!r.digest) {
      digestEl.innerHTML = '<div class="muted">Ni še poročila — zaženi <code>python -m chief --report</code> ali počakaj na dnevni beat.</div>';
      return;
    }
    digestEl.innerHTML = mdToSafeHtml(r.digest);
  };

  const load = (): void => {
    getJSON<ChiefResp>('/api/chief')
      .then(render)
      .catch(() => { if (digestEl) digestEl.innerHTML = '<div class="muted">Chief ni dosegljiv.</div>'; });
  };

  const send = (): void => {
    const text = input?.value.trim() ?? '';
    if (!text) return;
    if (msgEl) { msgEl.textContent = '…'; msgEl.className = 'chief-msg'; }
    fetch('/api/chief/correct', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    })
      .then(r => r.json())
      .then((r: { ok?: boolean }) => {
        if (msgEl) { msgEl.textContent = r.ok ? '✅ Popravek shranjen — učenje posodobljeno.' : '❌ Popravek ni bil shranjen.'; msgEl.className = `chief-msg ${r.ok ? 'ok' : 'err'}`; }
        if (input) input.value = '';
        setTimeout(load, 400);
      })
      .catch(() => { if (msgEl) { msgEl.textContent = '❌ Napaka pri pošiljanju.'; msgEl.className = 'chief-msg err'; } });
  };

  if (sendBtn) sendBtn.addEventListener('click', send);
  if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') send(); });

  load();
  setInterval(load, 60000);   // osveži digest vsako minuto
}
