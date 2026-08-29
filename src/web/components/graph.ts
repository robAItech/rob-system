// src/web/components/graph.ts — realen arhitekturni graf iz /api/graph.
// Interaktivni SVG: force-layout, hover → poudari sosede, pan/zoom, tooltip.
// v2: velikost pike = degree, labeli za top vozlišča, legenda + idle drift (graf živi).
interface GNode { id: string; label: string; group: string; x: number; y: number; vx: number; vy: number; }
interface GLink { source: GNode; target: GNode; }

const COLORS: Record<string, string> = { core: '#ffd166', action: '#4fc3ff', root: '#5e7ba0' };
const W = 900, H = 640;
// Amplituda + hitrost "idle drift" — graf počasi plava okoli ravnovesne lege.
const DRIFT_AMP = 2.5, DRIFT_T = 0.3;

export function initGraph(): void {
  const svg = document.getElementById('graph-svg') as unknown as SVGSVGElement | null;
  const tip = document.getElementById('graph-tip') as HTMLDivElement | null;
  const stats = document.getElementById('graph-stats') as HTMLSpanElement | null;
  if (!svg) return;

  fetch('/api/graph').then(r => r.json()).then((d: any) => {
    if (!d?.ok || !d.nodes?.length) { svg.innerHTML = '<text x="10" y="30" fill="#5e7ba0">ni grafa</text>'; return; }
    const nodes: GNode[] = d.nodes.map((n: any) => ({ ...n, x: 0, y: 0, vx: 0, vy: 0 }));
    const byId = new Map(nodes.map(n => [n.id, n]));
    const links: GLink[] = (d.links || [])
      .map((l: any) => ({ source: byId.get(l.source), target: byId.get(l.target) }))
      .filter((l: GLink) => l.source && l.target);

    // Začetne pozicije: radialno po skupinah (core v sredini, action/root zunaj).
    const groups = [...new Set(nodes.map(n => n.group))];
    nodes.forEach((n, i) => {
      const gi = groups.indexOf(n.group);
      const angle = (i / Math.max(nodes.length, 1)) * Math.PI * 2;
      const r = 70 + gi * 110 + (i % 5) * 12;
      n.x = Math.cos(angle) * r; n.y = Math.sin(angle) * r;
    });

    // Enostaven force-layout (fiksne iteracije, ob nalaganju).
    for (let it = 0; it < 250; it++) {
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = b.x - a.x, dy = b.y - a.y;
        const d2 = dx * dx + dy * dy + 1, d = Math.sqrt(d2);
        const f = 18000 / d2;
        const fx = dx / d * f, fy = dy / d * f;
        a.vx -= fx; a.vy -= fy; b.vx += fx; b.vy += fy;
      }
      for (const l of links) {
        const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (d - 140) * 0.02;
        const fx = dx / d * f, fy = dy / d * f;
        l.source.vx += fx; l.source.vy += fy; l.target.vx -= fx; l.target.vy -= fy;
      }
      for (const n of nodes) {
        n.vx *= 0.82; n.vy *= 0.82;
        n.vx += -n.x * 0.012; n.vy += -n.y * 0.012;
        n.x += n.vx; n.y += n.vy;
      }
    }
    render(svg, tip, stats, nodes, links);
  }).catch(() => { /* */ });
}

function render(svg: SVGSVGElement, tip: HTMLDivElement | null, stats: HTMLSpanElement | null,
  nodes: GNode[], links: GLink[]): void {
  svg.setAttribute('viewBox', `${-W / 2} ${-H / 2} ${W} ${H}`);
  const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  group.setAttribute('id', 'graph-main');

  // Stopnja vozlišča (degree) → velikost pike + labeli za top vozlišča.
  const degree = new Map<string, number>();
  for (const l of links) {
    degree.set(l.source.id, (degree.get(l.source.id) || 0) + 1);
    degree.set(l.target.id, (degree.get(l.target.id) || 0) + 1);
  }
  const maxDeg = Math.max(1, ...degree.values());
  const rFor = (id: string): number => 3.5 + ((degree.get(id) || 0) / maxDeg) * 10;   // 3.5 … 13.5
  // Top 5 vozlišč po povezavah dobi besedilni label (vidna arhitektura na prvi pogled).
  const topN = 5;
  const topIds = new Set(
    [...degree.entries()].sort((a, b) => b[1] - a[1]).slice(0, topN).map(([id]) => id),
  );

  // Vrstni red: povezave → krogi → labeli (labeli vedno na vrhu).
  const lineMarkup = links.map(l =>
    `<line x1="${l.source.x}" y1="${l.source.y}" x2="${l.target.x}" y2="${l.target.y}"
       stroke="#243a54" stroke-width="1" data-from="${l.source.id}" data-to="${l.target.id}"/>`
  ).join('');
  const circleMarkup = nodes.map(n =>
    `<circle cx="${n.x}" cy="${n.y}" r="${rFor(n.id)}" fill="${COLORS[n.group] || '#888'}"
       data-id="${n.id}" data-label="${n.label}" data-group="${n.group}" data-degree="${degree.get(n.id) || 0}"/>`
  ).join('');
  const labelMarkup = nodes.filter(n => topIds.has(n.id)).map(n =>
    `<text class="graph-label" x="${n.x}" y="${n.y + 21}" text-anchor="middle"
       fill="${COLORS[n.group] || '#9aa7b5'}" data-id="${n.id}">${String(n.label).replace(/</g, '&lt;')}</text>`
  ).join('');
  group.innerHTML = lineMarkup + circleMarkup + labelMarkup;
  svg.appendChild(group);

  if (stats) stats.textContent = `${nodes.length} vozlišč · ${links.length} povezav · max ${maxDeg}°`;

  // Sosedi za poudarjanje + referenca na elemente za drift.
  const adj = new Map<string, Set<string>>();
  for (const l of links) {
    (adj.get(l.source.id) || adj.set(l.source.id, new Set()).get(l.source.id)!).add(l.target.id);
    (adj.get(l.target.id) || adj.set(l.target.id, new Set()).get(l.target.id)!).add(l.source.id);
  }
  const circles = group.querySelectorAll('circle');
  const lines = group.querySelectorAll('line');
  const labelEls = new Map<string, SVGTextElement>();
  group.querySelectorAll<SVGTextElement>('text.graph-label').forEach(t => {
    labelEls.set(t.dataset.id!, t);
  });

  circles.forEach(c => {
    c.addEventListener('mouseenter', () => {
      const id = (c as SVGElement).dataset.id!;
      const neigh = adj.get(id) || new Set();
      circles.forEach(x => {
        const xid = (x as SVGElement).dataset.id!;
        (x as SVGElement).style.opacity = (xid === id || neigh.has(xid)) ? '1' : '0.12';
      });
      lines.forEach(l => {
        const from = (l as SVGElement).dataset.from!;
        const to = (l as SVGElement).dataset.to!;
        (l as SVGElement).style.opacity = (from === id || to === id || neigh.has(from) || neigh.has(to)) ? '0.8' : '0.08';
      });
      labelEls.forEach((t, lid) => {
        (t as SVGElement).style.opacity = (lid === id || neigh.has(lid)) ? '1' : '0.15';
      });
      if (tip) {
        const deg = (c as SVGElement).dataset.degree || '0';
        tip.textContent = `${(c as SVGElement).dataset.label} (${(c as SVGElement).dataset.group}) · ${deg} povezav`;
        tip.classList.add('show');
      }
    });
    c.addEventListener('mouseleave', () => {
      circles.forEach(x => (x as SVGElement).style.opacity = '1');
      lines.forEach(x => (x as SVGElement).style.opacity = '0.6');
      labelEls.forEach(t => (t as SVGElement).style.opacity = '1');
      if (tip) tip.classList.remove('show');
    });
  });

  // Pan (drag po ozadju) + zoom (kolo).
  let tx = 0, ty = 0, scale = 1;
  let dragging = false, sx = 0, sy = 0, stx = 0, sty = 0;
  svg.addEventListener('mousedown', (e) => { dragging = true; sx = e.clientX; sy = e.clientY; stx = tx; sty = ty; });
  window.addEventListener('mousemove', (e) => {
    if (!dragging) return;
    tx = stx + (e.clientX - sx) / scale; ty = sty + (e.clientY - sy) / scale;
    group.setAttribute('transform', `translate(${tx} ${ty}) scale(${scale})`);
  });
  window.addEventListener('mouseup', () => { dragging = false; });
  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    const d = e.deltaY > 0 ? 0.9 : 1.1;
    scale = Math.min(3, Math.max(0.2, scale * d));
    group.setAttribute('transform', `translate(${tx} ${ty}) scale(${scale})`);
  });

  // Idle drift — graf počasi diha okoli ravnovesnih leg (sinusne nihaje).
  const phases = new Map(nodes.map((n, i) => [n.id, (i * 2.399963) % (Math.PI * 2)]));
  const t0 = performance.now();
  const frame = (now: number): void => {
    const t = (now - t0) / 1000;
    const offset = (id: string): [number, number] => {
      const ph = phases.get(id) || 0;
      return [
        Math.sin(t * DRIFT_T + ph) * DRIFT_AMP,
        Math.cos(t * DRIFT_T * 0.77 + ph * 1.7) * DRIFT_AMP,
      ];
    };
    nodes.forEach((n, i) => {
      const [ox, oy] = offset(n.id);
      const c = circles[i] as SVGElement;
      c.setAttribute('cx', String(n.x + ox));
      c.setAttribute('cy', String(n.y + oy));
      const lab = labelEls.get(n.id);
      if (lab) {
        lab.setAttribute('x', String(n.x + ox));
        lab.setAttribute('y', String(n.y + oy + 21));
      }
    });
    links.forEach((l, j) => {
      const [sx0, sy0] = offset(l.source.id);
      const [tx0, ty0] = offset(l.target.id);
      const el = lines[j] as SVGLineElement;
      el.setAttribute('x1', String(l.source.x + sx0));
      el.setAttribute('y1', String(l.source.y + sy0));
      el.setAttribute('x2', String(l.target.x + tx0));
      el.setAttribute('y2', String(l.target.y + ty0));
    });
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}
