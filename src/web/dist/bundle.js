// src/web/api.ts
async function getJSON(path) {
  const r = await fetch(path);
  if (!r.ok)
    throw new Error(`HTTP ${r.status} — ${path}`);
  return r.json();
}
var fetchFleet = () => getJSON("/api/fleet");
var fetchMetrics = () => getJSON("/api/metrics");
function ageAgo(ts) {
  if (!ts)
    return "—";
  const s = Math.max(0, Math.floor(Date.now() / 1000 - ts));
  if (s < 90)
    return "zdaj";
  if (s < 3600)
    return `pred ${s / 60 | 0} min`;
  return `pred ${s / 3600 | 0} h`;
}

// src/web/components/fleet.ts
function memoryLabel(memory) {
  return Object.entries(memory || {}).map(([k, v]) => `${k.replace(/_/g, " ")} ${v}`).join(" · ");
}
function renderFleet(el, d) {
  const { workers = {}, agenda = {}, memory = {}, backup = {}, daemon = {} } = d;
  const mem = memoryLabel(memory);
  const state = daemon?.state || "—";
  const backupAge = ageAgo(backup?.backed_up_at ?? undefined);
  const pending = agenda.pending ?? 0, running = agenda.running ?? 0;
  let html = `<div class="fleet-row"><span>agenda</span><b>${pending} čaka · ${running} teče</b></div>`;
  if (mem)
    html += `<div class="fleet-row"><span>spomin</span><span>${mem}</span></div>`;
  html += `<div class="fleet-row"><span>daemon</span><span>${state}</span></div>`;
  html += `<div class="fleet-row"><span>backup git</span><span>${backupAge}</span></div>`;
  const names = Object.keys(workers || {});
  if (names.length) {
    names.forEach((w) => {
      const wd = workers[w] || {};
      html += `<div class="fleet-row"><span>● ${w}</span><span>${ageAgo(wd.last_seen)} · ${(wd.tasks || []).length} nalog</span></div>`;
    });
  } else {
    html += `<div class="fleet-row" style="color:var(--faint)">— ni aktivnih workerjev (master / standalone)</div>`;
  }
  const act = d.activity || [];
  if (act.length) {
    html += `<div class="fleet-section">Zadnja aktivnost</div>` + act.map((a) => `<div class="fleet-row slim"><span class="s ${a.c}">${a.s}</span><span class="m">${a.t} ${a.m}</span></div>`).join("");
  }
  el.innerHTML = html;
}

// src/web/components/feed.ts
function connectFeed(feedEl, dotEl, onEvent, seed = []) {
  const render = (events2) => {
    feedEl.innerHTML = events2.map((e) => `<div class="feed-line"><span class="t">${e.t}</span><span class="s ${e.c}">${e.s}</span><span class="m">${e.m}</span></div>`).join("") || '<div class="feed-empty">čakam na dogodke …</div>';
  };
  const events = [...seed];
  if (seed.length)
    render(events);
  let es = null;
  try {
    es = new EventSource("/api/stream");
  } catch {
    return;
  }
  es.onopen = () => {
    if (dotEl)
      dotEl.classList.add("live");
  };
  es.onmessage = (ev) => {
    try {
      const d = JSON.parse(ev.data);
      if (d.type === "event" && d.event) {
        events.unshift(d.event);
        events.length = Math.min(events.length, 12);
        render(events);
        onEvent(d.event);
      }
    } catch {}
  };
  es.onerror = () => {};
}

// src/web/components/kpis.ts
function setVal(id, v) {
  const el = document.getElementById(id);
  if (el)
    el.textContent = v === undefined || v === null ? "—" : String(v);
}
function renderKpis(m) {
  setVal("kpi-tasks", m.tasks);
  setVal("kpi-errors", m.errors);
  setVal("kpi-nodes", m.nodes);
}

// src/web/main.ts
function ready(fn) {
  if (document.readyState !== "loading")
    fn();
  else
    document.addEventListener("DOMContentLoaded", fn);
}
ready(() => {
  const fleetEl = document.getElementById("fleet-body");
  const feedEl = document.getElementById("feed");
  const dotEl = document.getElementById("sse-dot");
  const loadKpis = () => fetchMetrics().then(renderKpis).catch(() => {});
  loadKpis();
  setInterval(loadKpis, 15000);
  const loadFleet = () => fetchFleet().then((d) => fleetEl && renderFleet(fleetEl, d)).catch(() => {});
  loadFleet();
  setInterval(loadFleet, 15000);
  if (feedEl) {
    getJSON("/api/events").then((r) => connectFeed(feedEl, dotEl, () => {}, r.events || [])).catch(() => connectFeed(feedEl, dotEl, () => {}));
  }
});
