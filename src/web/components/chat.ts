// src/web/components/chat.ts — Pogovor (chat UI prek /api/chat).
import type { ChatReply } from '../../shared/types';

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
    try {
      const r = await fetch('/api/chat', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, kind: 'chat' }),
      });
      const d: ChatReply = await r.json();
      busy.textContent = d.reply ?? (d.error ?? 'napaka');
    } catch (e) {
      busy.textContent = 'napaka pri povezavi';
    }
    box.scrollTop = box.scrollHeight;
  };

  send.addEventListener('click', ask);
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter') ask(); });
}
