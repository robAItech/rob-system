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

// src/web/components/chat.ts
var TASK_RE = /(?:naredi|izdelaj|zgradi|napiši|ustvari|build|razvij|implement|create|make|modul|module)\b/i;
var MD_RE = /(?:markdown|poročilo|dokument|analiza|predlog|specifikacija|\bspec\b|readme|primerjava|sintetiziraj|opis\b|povzetek)/i;
var HTML_RE = /(?:spletno\s+stran|html|stran|ui|dashboard|zastavi\s+ogled|landing\s+page)/i;
function detectKind(text) {
  if (MD_RE.test(text))
    return "markdown";
  if (HTML_RE.test(text))
    return "html";
  return "python";
}
function initChat() {
  const box = document.getElementById("chat-box");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("chat-send");
  if (!box || !input || !send)
    return;
  const addMsg = (role, text) => {
    const d = document.createElement("div");
    d.className = `chat-msg ${role}`;
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  };
  const ask = async () => {
    const text = input.value.trim();
    if (!text)
      return;
    addMsg("user", text);
    input.value = "";
    const busy = document.createElement("div");
    busy.className = "chat-msg ai chat-typing";
    busy.textContent = "…";
    box.appendChild(busy);
    box.scrollTop = box.scrollHeight;
    let reply = "napaka pri povezavi";
    try {
      const r = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, kind: "chat" })
      });
      const d = await r.json();
      reply = d.reply ?? (d.error ?? "napaka");
    } catch (e) {}
    if (TASK_RE.test(text)) {
      try {
        const kind = detectKind(text);
        await fetch("/api/agenda", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ goal: text, kind })
        });
        reply += `

➕ Dodano v agendo (kind=` + kind + ") — worker bo zgradil.";
      } catch (e) {
        reply += `

⚠️ Napaka pri dodajanju v agendo.`;
      }
    }
    busy.textContent = reply;
    box.scrollTop = box.scrollHeight;
  };
  send.addEventListener("click", ask);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter")
      ask();
  });
}

// src/web/components/agenda.ts
function initAgenda() {
  const list = document.getElementById("agenda-list");
  const input = document.getElementById("agenda-input");
  const addBtn = document.getElementById("agenda-add");
  if (!list)
    return;
  const statusClass = (s) => s === "done" ? "s-ok" : s === "failed" ? "s-crit" : s === "running" ? "s-run" : "s-warn";
  const render = (items) => {
    if (!items.length) {
      list.innerHTML = '<div class="agenda-empty">Agenda je prazna — dodaj nalogo.</div>';
      return;
    }
    list.innerHTML = items.map((it) => {
      const claimed = it.claimed_by ? ` · ${it.claimed_by}` : "";
      const worker = it.result_worker ? ` · → ${it.result_worker}` : "";
      return `<div class="agenda-item" data-id="${it.id}">
        <div class="agenda-top"><span class="s ${statusClass(it.status)}">${it.status}</span>
          <span class="agenda-target">${it.target || ""}${claimed}${worker}</span>
          <button class="agenda-del" data-del="${it.id}" title="Odstrani">✕</button>
        </div>
        <div class="agenda-goal">${String(it.goal || "").replace(/</g, "&lt;")}</div>
      </div>`;
    }).join("");
    list.querySelectorAll("[data-del]").forEach((b) => {
      b.addEventListener("click", () => {
        fetch("/api/agenda/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: b.dataset.del })
        }).then(load);
      });
    });
  };
  const load = () => {
    getJSON("/api/agenda").then((r) => render(r.items || [])).catch(() => {});
  };
  const add = () => {
    const goal = input?.value.trim() ?? "";
    if (!goal)
      return;
    fetch("/api/agenda", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ goal, kind: "python" })
    }).then(() => {
      if (input)
        input.value = "";
      load();
    });
  };
  if (addBtn)
    addBtn.addEventListener("click", add);
  if (input)
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter")
        add();
    });
  load();
  setInterval(load, 15000);
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
  initChat();
  initAgenda();
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const v = btn.dataset.view;
      document.querySelectorAll("[data-view-panel]").forEach((p) => {
        p.classList.toggle("hidden", p.dataset.viewPanel !== v);
      });
    });
  });
});
