// src/web/components/chat.ts — Pogovor (chat UI prek /api/chat).
// Če sporočilo vsebuje nalogo (naredi/izdelaj/zgradi/build/modul …), jo
// samodejno doda v agendo — worker jo bo zgradil.
//
// Hands-free glasovni pogovor (brez pritiskanja 🎤):
//   1. Ko odpreš Pogovor, mikrofon začne poslušati sam (sl-SI).
//   2. Ko spregovoriš → tekst se samodejno pošlje.
//   3. AI odgovor se prikaže (tekst) IN prebere na glas (POST /api/tts).
//   4. Med govorom avatar premika utnice; ko konča, spet posluša.
//   🎤 gumb preklaplja glasovni način on/off (tihi tipkanje).
import type { ChatReply } from '../../shared/types';
import { initAvatar, type AvatarCtl } from './avatar';

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
  if (!box || !input || !send) return;

  const avatar: AvatarCtl | null = initAvatar();

  // Glasovni način je privzeto VKLOPLJEN — posluša, ko odpreš Pogovor.
  let voiceMode = SpeechRec !== undefined;
  let busy = false;         // čaka na AI odgovor → ne pošiljaj novega glasu
  let rearmTimer = 0;

  const setStatus = (text: string): void => { avatar?.setStatus(text); };
  const setRecording = (on: boolean): void => {
    voiceBtn?.classList.toggle('recording', on);
    avatar?.setListening(on);
    if (on) setStatus('🎤 poslušam — govori …');
    else if (voiceMode) setStatus('pripravljen — govori ali piši');
  };

  const chatVisible = (): boolean => {
    const panel = document.querySelector('[data-view-panel="chat"]');
    return !!panel && (panel as HTMLElement).getBoundingClientRect().height > 0;
  };

  // ---- Mikrofon (Web Speech API) ------------------------------------
  let rec: any = null;
  if (SpeechRec) {
    rec = new SpeechRec();
    rec.lang = 'sl-SI';
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e: any): void => {
      const t = e.results?.[0]?.[0]?.transcript ?? '';
      setRecording(false);
      if (t) {
        input.value = t;
        if (voiceMode && !busy) void ask();   // hands-free: samodejno pošlji
      }
    };
    rec.onerror = (e: any): void => {
      const err = e?.error || '';
      // Blokiran mikrofon → ugasni način (ne ponavljaj v neskončnost).
      if (err === 'not-allowed' || err === 'service-not-allowed') {
        voiceMode = false;
        voiceBtn?.classList.remove('recording');
        setStatus('🚫 mikrofon blokiran — dovoli dostop v brskalniku, pa govori');
        return;
      }
      setRecording(false);
      rearm();   // 'no-speech' / začasna napaka → poskusi znova
    };
    rec.onend = (): void => { setRecording(false); rearm(); };
  } else {
    setStatus('🖥️ govorni vnos ni na voljo v tem brskalniku — piši sporočilo');
    if (voiceBtn) voiceBtn.style.display = 'none';
  }

  const startRec = (): void => {
    if (!rec || !voiceMode || busy || !chatVisible()) return;
    try { rec.start(); setRecording(true); } catch { /* že teče ali mic zaseden */ }
  };
  const rearm = (): void => {
    window.clearTimeout(rearmTimer);
    if (!voiceMode || busy) return;
    rearmTimer = window.setTimeout(() => { if (voiceMode && !busy) startRec(); }, 450);
  };
  const stopRec = (): void => {
    window.clearTimeout(rearmTimer);
    try { rec?.stop?.(); } catch { /* */ }
    setRecording(false);
  };

  // 🎤 gumb: ročni preklop glasovnega načina.
  if (voiceBtn) voiceBtn.addEventListener('click', () => {
    voiceMode = !voiceMode;
    if (voiceMode) startRec();
    else { stopRec(); setStatus('🛑 tihi način — piši ročno'); }
  });

  // Ob preklopu pogleda: odpri Pogovor → začni poslušati; zapusti → ustavi.
  document.querySelectorAll<HTMLButtonElement>('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.dataset.view === 'chat') startRec();
      else stopRec();
    });
  });

  // ---- TTS: AI odgovor preberi na glas (utnice se premikajo) ----------
  const speak = async (text: string): Promise<void> => {
    setStatus('🔊 govorim …');
    try {
      const r = await fetch('/api/tts', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice: 'Charon' }),
      });
      const d = await r.json();
      if (d?.ok && d.base64) {
        const audio = new Audio(`data:${d.mime};base64,${d.base64}`);
        avatar?.setSpeaking(true);
        await new Promise<void>((res) => {
          audio.onended = () => res();
          audio.onerror = () => res();
          audio.play().catch(() => res());
        });
        avatar?.setSpeaking(false);
        setStatus('pripravljen — govori ali piši');
        return;
      }
    } catch { /* TTS ni na voljo */ }
    avatar?.setSpeaking(false);
    setStatus('pripravljen — govori ali piši');
  };

  // ---- Pošiljanje ------------------------------------------------------
  const addMsg = (role: 'user' | 'ai', text: string): void => {
    const d = document.createElement('div');
    d.className = `chat-msg ${role}`;
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  };

  async function ask(): Promise<void> {
    const text = input.value.trim();
    if (!text) return;
    busy = true;
    stopRec();                       // med obdelavo ne poslušaj (brez odmeva)
    addMsg('user', text);
    input.value = '';
    const busyEl = document.createElement('div');
    busyEl.className = 'chat-msg ai chat-typing';
    busyEl.textContent = '…';
    box.appendChild(busyEl);
    box.scrollTop = box.scrollHeight;

    let reply = 'napaka pri povezavi';
    try {
      const r = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, kind: 'chat' }),
      });
      const d: ChatReply = await r.json();
      reply = d.reply ?? (d.error ?? 'napaka');
    } catch { /* offline */ }

    // Naloga v pogovoru → samodejno v agendo.
    if (TASK_RE.test(text)) {
      try {
        const kind = detectKind(text);
        await fetch('/api/agenda', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ goal: text, kind }),
        });
        reply += '\n\n➕ Dodano v agendo (kind=' + kind + ') — worker bo zgradil.';
      } catch {
        reply += '\n\n⚠️ Napaka pri dodajanju v agendo.';
      }
    }
    busyEl.textContent = reply;
    box.scrollTop = box.scrollHeight;

    busy = false;
    // Nadaljuj pogovor: preberi odgovor na glas, nato spet poslušaj.
    if (voiceMode) {
      await speak(reply);
      rearm();
    }
  }

  send.addEventListener('click', () => void ask());
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') void ask(); });
}
