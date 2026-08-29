// src/web/components/chat.ts — Pogovor (chat UI prek /api/chat).
// Če sporočilo vsebuje nalogo (naredi/izdelaj/zgradi/build/modul …), jo
// samodejno doda v agendo — worker jo bo zgradil.
// Glasovni vnos: Web Speech API (webkitSpeechRecognition, sl-SI) → v input.
// TTS: AI odgovor prek POST /api/tts {text, voice} → {ok, voice, mime, base64} → predvajaj.
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

// Zagon govora: Web Speech API ni v vseh browserjih → guard.
const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;

export function initChat(): void {
  const box = document.getElementById('chat-box');
  const input = document.getElementById('chat-input') as HTMLInputElement | null;
  const send = document.getElementById('chat-send');
  const voiceBtn = document.getElementById('voice-btn') as HTMLButtonElement | null;
  const voiceStatus = document.getElementById('voice-status') as HTMLDivElement | null;
  if (!box || !input || !send) return;

  // --- Glasovni vnos (mikrofon → input). ---
  const setRecording = (on: boolean): void => {
    voiceBtn?.classList.toggle('recording', on);
    if (voiceStatus) {
      voiceStatus.classList.toggle('hidden', !on);
      voiceStatus.textContent = on ? '🎤 poslušam … govori.' : '';
    }
  };
  let rec: any = null;
  if (voiceBtn && SpeechRec) {
    rec = new SpeechRec();
    rec.lang = 'sl-SI';
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e: any): void => {
      const t = e.results?.[0]?.[0]?.transcript ?? '';
      if (t) { input.value = t; input.focus(); }
      setRecording(false);
    };
    rec.onerror = (): void => setRecording(false);
    rec.onend = (): void => setRecording(false);
    voiceBtn.addEventListener('click', () => {
      if (voiceBtn.classList.contains('recording')) { rec.stop(); setRecording(false); }
      else { try { rec.start(); setRecording(true); } catch { /* mic zaseden */ } }
    });
  } else if (voiceBtn) {
    voiceBtn.style.display = 'none';   // brskalnik nima Speech API → skrij gumb.
  }

  // --- TTS: AI odgovor preberi na glas. ---
  const speak = async (text: string): Promise<void> => {
    try {
      const r = await fetch('/api/tts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: 'Charon' }),
      });
      const d = await r.json();
      if (d?.ok && d.base64) {
        new Audio(`data:${d.mime};base64,${d.base64}`).play().catch(() => { /* glas tiho */ });
      }
    } catch { /* TTS ni nujen — brez govora gre dalje */ }
  };

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
    speak(reply);   // preberi odgovor na glas.
  };

  send.addEventListener('click', ask);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
}
