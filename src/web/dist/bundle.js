// src/web/api.ts
var onUnauthorized = null;
function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}
async function getJSON(path) {
  const r = await fetch(path);
  if (r.status === 401) {
    if (onUnauthorized)
      onUnauthorized();
    throw new Error("unauthorized");
  }
  if (!r.ok)
    throw new Error(`HTTP ${r.status} — ${path}`);
  return r.json();
}
function auth(token) {
  return fetch("/api/auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token })
  }).then((r) => r.ok).catch(() => false);
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
var kpiHistory = [];
function recordSample(m) {
  kpiHistory.push({ ts: Date.now(), tasks: m.tasks, errors: m.errors, nodes: m.nodes });
  if (kpiHistory.length > 30)
    kpiHistory.shift();
}
function deltaStr(prev, cur) {
  if (prev === undefined || cur === undefined || prev === cur)
    return "—";
  const d = cur - prev;
  return d > 0 ? `▲${d}` : `▼${Math.abs(d)}`;
}
function sparkline(vals, color) {
  if (vals.length < 2)
    return "";
  const w = 60, h = 18;
  const min = Math.min(...vals), max = Math.max(...vals);
  const range = max - min || 1;
  const pts = vals.map((v, i) => `${(i / (vals.length - 1) * w).toFixed(1)},${(h - (v - min) / range * (h - 2) - 1).toFixed(1)}`).join(" ");
  return `<svg width="${w}" height="${h}"><polyline points="${pts}" fill="none" stroke="${color}" stroke-width="1.5"/></svg>`;
}
function renderKpis(m) {
  const prev = kpiHistory[kpiHistory.length - 2];
  const fields = [
    ["kpi-tasks", "tasks", "var(--gold)"],
    ["kpi-errors", "errors", "var(--bad)"],
    ["kpi-nodes", "nodes", "var(--accent)"]
  ];
  for (const [id, key, color] of fields) {
    const el = document.getElementById(id);
    if (!el)
      continue;
    const val = m[key];
    el.innerHTML = val === undefined || val === null ? "—" : String(val) + `<span class="kpi-delta">${deltaStr(prev?.[key], val)}</span>`;
    const sp = document.getElementById(id + "-spark");
    if (sp) {
      sp.innerHTML = sparkline(kpiHistory.filter((s) => s[key] !== undefined).map((s) => s[key]), color);
    }
  }
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

// src/web/components/graph.ts
var COLORS = { core: "#ffd166", action: "#4fc3ff", root: "#5e7ba0" };
var W = 900;
var H = 640;
function initGraph() {
  const svg = document.getElementById("graph-svg");
  const tip = document.getElementById("graph-tip");
  if (!svg)
    return;
  fetch("/api/graph").then((r) => r.json()).then((d) => {
    if (!d?.ok || !d.nodes?.length) {
      svg.innerHTML = '<text x="10" y="30" fill="#5e7ba0">ni grafa</text>';
      return;
    }
    const nodes = d.nodes.map((n) => ({ ...n, x: 0, y: 0, vx: 0, vy: 0 }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const links = (d.links || []).map((l) => ({ source: byId.get(l.source), target: byId.get(l.target) })).filter((l) => l.source && l.target);
    const groups = [...new Set(nodes.map((n) => n.group))];
    nodes.forEach((n, i) => {
      const gi = groups.indexOf(n.group);
      const angle = i / Math.max(nodes.length, 1) * Math.PI * 2;
      const r = 70 + gi * 110 + i % 5 * 12;
      n.x = Math.cos(angle) * r;
      n.y = Math.sin(angle) * r;
    });
    for (let it = 0;it < 250; it++) {
      for (let i = 0;i < nodes.length; i++)
        for (let j = i + 1;j < nodes.length; j++) {
          const a = nodes[i], b = nodes[j];
          const dx = b.x - a.x, dy = b.y - a.y;
          const d2 = dx * dx + dy * dy + 1, d3 = Math.sqrt(d2);
          const f = 18000 / d2;
          const fx = dx / d3 * f, fy = dy / d3 * f;
          a.vx -= fx;
          a.vy -= fy;
          b.vx += fx;
          b.vy += fy;
        }
      for (const l of links) {
        const dx = l.target.x - l.source.x, dy = l.target.y - l.source.y;
        const d2 = Math.sqrt(dx * dx + dy * dy) || 1;
        const f = (d2 - 140) * 0.02;
        const fx = dx / d2 * f, fy = dy / d2 * f;
        l.source.vx += fx;
        l.source.vy += fy;
        l.target.vx -= fx;
        l.target.vy -= fy;
      }
      for (const n of nodes) {
        n.vx *= 0.82;
        n.vy *= 0.82;
        n.vx += -n.x * 0.012;
        n.vy += -n.y * 0.012;
        n.x += n.vx;
        n.y += n.vy;
      }
    }
    render(svg, tip, nodes, links);
  }).catch(() => {});
}
function render(svg, tip, nodes, links) {
  svg.setAttribute("viewBox", `${-W / 2} ${-H / 2} ${W} ${H}`);
  const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
  group.setAttribute("id", "graph-main");
  group.innerHTML = links.map((l) => `<line x1="${l.source.x}" y1="${l.source.y}" x2="${l.target.x}" y2="${l.target.y}" stroke="#243a54" stroke-width="1"/>`).join("") + nodes.map((n) => `<circle cx="${n.x}" cy="${n.y}" r="6" fill="${COLORS[n.group] || "#888"}"
      data-id="${n.id}" data-label="${n.label}" data-group="${n.group}"/>`).join("");
  svg.appendChild(group);
  const adj = new Map;
  for (const l of links) {
    (adj.get(l.source.id) || adj.set(l.source.id, new Set).get(l.source.id)).add(l.target.id);
    (adj.get(l.target.id) || adj.set(l.target.id, new Set).get(l.target.id)).add(l.source.id);
  }
  const circles = group.querySelectorAll("circle");
  const lines = group.querySelectorAll("line");
  circles.forEach((c) => {
    c.addEventListener("mouseenter", () => {
      const id = c.dataset.id;
      const neigh = adj.get(id) || new Set;
      circles.forEach((x) => {
        const xid = x.dataset.id;
        x.style.opacity = xid === id || neigh.has(xid) ? "1" : "0.15";
      });
      lines.forEach((l) => {
        const src = l.getAttribute("x1") === c.getAttribute("cx") && l.getAttribute("y1") === c.getAttribute("cy");
        l.style.opacity = "0.5";
      });
      if (tip) {
        tip.textContent = `${c.dataset.label} (${c.dataset.group}) · ${neigh.size} povezav`;
        tip.classList.add("show");
      }
    });
    c.addEventListener("mouseleave", () => {
      circles.forEach((x) => x.style.opacity = "1");
      lines.forEach((x) => x.style.opacity = "0.6");
      if (tip)
        tip.classList.remove("show");
    });
  });
  let tx = 0, ty = 0, scale = 1;
  let dragging = false, sx = 0, sy = 0, stx = 0, sty = 0;
  svg.addEventListener("mousedown", (e) => {
    dragging = true;
    sx = e.clientX;
    sy = e.clientY;
    stx = tx;
    sty = ty;
  });
  window.addEventListener("mousemove", (e) => {
    if (!dragging)
      return;
    tx = stx + (e.clientX - sx) / scale;
    ty = sty + (e.clientY - sy) / scale;
    group.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);
  });
  window.addEventListener("mouseup", () => {
    dragging = false;
  });
  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const d = e.deltaY > 0 ? 0.9 : 1.1;
    scale = Math.min(3, Math.max(0.2, scale * d));
    group.setAttribute("transform", `translate(${tx} ${ty}) scale(${scale})`);
  });
}

// src/web/main.ts
function ready(fn) {
  if (document.readyState !== "loading")
    fn();
  else
    document.addEventListener("DOMContentLoaded", fn);
}
ready(() => {
  const overlay = document.getElementById("login-overlay");
  const loginBtn = document.getElementById("login-btn");
  const loginInput = document.getElementById("login-token");
  const loginMsg = document.getElementById("login-msg");
  const showLogin = (msg) => {
    if (!overlay)
      return;
    overlay.classList.remove("hidden");
    if (msg && loginMsg)
      loginMsg.textContent = msg;
  };
  setUnauthorizedHandler(() => showLogin("Seja je potekla ali ni veljavna — prijavi se."));
  const startApp = () => {
    const fleetEl = document.getElementById("fleet-body");
    const feedEl = document.getElementById("feed");
    const dotEl = document.getElementById("sse-dot");
    const loadKpis = () => fetchMetrics().then((m) => {
      recordSample(m);
      renderKpis(m);
    }).catch(() => {});
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
    initGraph();
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
  };
  fetch("/api/me").then((r) => {
    if (r.ok)
      startApp();
    else
      showLogin();
  }).catch(() => showLogin());
  if (loginBtn && loginInput) {
    const doLogin = async () => {
      const t = loginInput.value.trim();
      if (!t)
        return;
      const ok = await auth(t);
      if (ok) {
        location.reload();
      } else if (loginMsg) {
        loginMsg.textContent = "Napačen token. Preveri ROB_API_TOKEN v .env.";
      }
    };
    loginBtn.addEventListener("click", doLogin);
    loginInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter")
        doLogin();
    });
  }
});
