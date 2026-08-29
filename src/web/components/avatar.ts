// src/web/components/avatar.ts — ROB obraz: simulacija utnic (lip-sync) + mežikanje.
// Avatar živi v chat panelu; utnice se premikajo, ko sistem govori (TTS),
// oči mežikajo samodejno. Statusna vrstica kaže stanje (pripravljen/poslušam/govorim).

export interface AvatarCtl {
  setSpeaking(on: boolean): void;   // TTS predvaja → premakni utnice
  setListening(on: boolean): void;  // mikrofon posluša → poudari
  setStatus(text: string): void;    // statusna vrstica pod imenom
}

export function initAvatar(): AvatarCtl | null {
  const svg = document.querySelector<SVGSVGElement>('.avatar-svg');
  const mouth = document.querySelector<SVGEllipseElement>('.avatar-mouth');
  const eyeL = document.querySelector<SVGEllipseElement>('.eye-l');
  const eyeR = document.querySelector<SVGEllipseElement>('.eye-r');
  const status = document.getElementById('avatar-status');
  if (!svg || !mouth || !eyeL || !eyeR) return null;

  // Mežikanje: vsake ~2.5–4.5 s skrči oči za ~140 ms (tudi med govorom).
  let blinkTimer = 0;
  const scheduleBlink = (): void => {
    blinkTimer = window.setTimeout(blink, 2400 + Math.random() * 1800);
  };
  function blink(): void {
    eyeL.setAttribute('ry', '1.2');
    eyeR.setAttribute('ry', '1.2');
    window.setTimeout(() => {
      eyeL.setAttribute('ry', '8');
      eyeR.setAttribute('ry', '8');
    }, 140);
    scheduleBlink();
  }
  scheduleBlink();

  // Utnice: dvojni sinus — govorna kadenca (~6 Hz zlogi + 18 Hz tresljaj).
  let raf = 0;
  function lips(): void {
    const t0 = performance.now();
    const step = (now: number): void => {
      if (!svg.classList.contains('speaking')) { mouth.setAttribute('ry', '3'); return; }
      const t = (now - t0) / 1000;
      const a = 0.5 + 0.5 * Math.sin(t * 6.2) + 0.25 * Math.sin(t * 17.3 + 1.2);
      const open = Math.max(0.4, Math.min(1, a));
      mouth.setAttribute('ry', String(2 + open * 9));
      mouth.setAttribute('rx', String(13 - open * 3));
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }

  return {
    setSpeaking(on: boolean): void {
      svg.classList.toggle('speaking', on);
      if (on) lips();
      else { cancelAnimationFrame(raf); mouth.setAttribute('ry', '3'); }
    },
    setListening(on: boolean): void {
      svg.classList.toggle('listening', on);
    },
    setStatus(text: string): void {
      if (status) status.textContent = text;
    },
  };
}
