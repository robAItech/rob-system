// src/web/components/chat.ts — Pogovor (chat UI prek /api/chat).
// Če sporočilo vsebuje nalogo (naredi/izdelaj/zgradi/build/modul …), jo
// samodejno doda v agendo — worker jo bo zgradil.
import type { ChatReply } from '../../shared/types';

const TASK_RE = /(?:naredi|izdelaj|zgradi|napiši|ustvari|build|razvij|implement|create|make|modul|module)\b/i;
// Markdown/poročila: dokumenti, analize, predlogi, specifikacije, README …
const MD_RE = /(?:markdown|poročilo|dokument|analiza|predlog|specifikacija|\bspec\b|readme|primerjava|sintetiziraj|opis\b|povzetek)/i;
// Spletne strani / UI / HTML.
const HTML_RE = /(?:spletno\s+stran|html|stran|ui|dashboard|zastavi\s+ogled|landing\s+page)/i;

function detectKind(text: string): string {
  if (MD_RE.test(text)) return 'markdown';
  if (HTML_RE.test(text)) return 'html';
  return 'python';
}

export function initChat(): void {
  const box = document.getElementById('chat-box');
  const input = document.getElementById('chat-input') as HTMLInputElement | null;
  const send = document.getElementById('chat-send');
  if (!box || !input || !send) return;

  const addMsg = (role: 'user' | 'ai', text: string): void => {
    const d = document.createElement('div');
    d.className = `chat-msg ${role}`;
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  };

  const ask = async (): Promise<void> => {
    const text = input.value.trim();
    if (!text) return;
    addMsg('user', text);
    input.value = '';
    const busy = document.createElement('div');
    busy.className = 'chat-msg ai chat-typing';
    busy.textContent = '…';
    box.appendChild(busy);
    box.scrollTop = box.scrollHeight;
    let reply = 'napaka pri povezavi';
    try {
      const r = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, kind: 'chat' }),
      });
      const d: ChatReply = await r.json();
      reply = d.reply ?? (d.error ?? 'napaka');
    } catch (e) { /* offline */ }

    // Naloga v pogovoru → samodejno v agendo.
    if (TASK_RE.test(text)) {
      try {
        const kind = detectKind(text);
        await fetch('/api/agenda', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ goal: text, kind }),
        });
        reply += '\n\n➕ Dodano v agendo (kind=' + kind + ') — worker bo zgradil.';
      } catch (e) {
        reply += '\n\n⚠️ Napaka pri dodajanju v agendo.';
      }
    }
    busy.textContent = reply;
    box.scrollTop = box.scrollHeight;
  };

  send.addEventListener('click', ask);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
}
