// src/web/api.ts
var onUnauthorized = null;
var sessionExpired = false;
function setUnauthorizedHandler(fn) {
  onUnauthorized = fn;
}
function isSessionExpired() {
  return sessionExpired;
}
async function getJSON(path) {
  const r = await fetch(path);
  if (r.status === 401) {
    sessionExpired = true;
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
  const events = [...seed];
  const render = () => {
    feedEl.innerHTML = events.length ? events.map((e) => `<div class="feed-line"><span class="t">${e.t}</span><span class="s ${e.c}">${e.s}</span><span class="m">${e.m}</span></div>`).join("") : '<div class="panel-state">Ni dogodkov še — čakam …</div>';
  };
  const setMsg = (html) => {
    feedEl.innerHTML = html;
  };
  if (seed.length)
    render();
  else
    setMsg('<div class="panel-state"><span class="spinner"></span> povezujem …</div>');
  let es = null;
  try {
    es = new EventSource("/api/stream");
  } catch {
    setMsg('<div class="panel-state err">SSE ni podprt</div>');
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
        render();
        onEvent(d.event);
      }
    } catch {}
  };
  es.onerror = () => {
    if (isSessionExpired()) {
      try {
        es?.close();
      } catch {}
      if (dotEl)
        dotEl.classList.remove("live");
      setMsg('<div class="panel-state err">\uD83D\uDD12 Povezava prekinjena — prijava potrebna.</div>');
      return;
    }
    if (dotEl)
      dotEl.classList.remove("live");
    if (!events.length)
      setMsg('<div class="panel-state err">Povezava prekinjena — poskušam znova …</div>');
  };
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
var shown = new Map;
function countUp(el, key, target, deltaHtml) {
  const from = shown.get(key) ?? 0;
  const dur = 650;
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min(1, (now - t0) / dur);
    const ease = 1 - Math.pow(1 - p, 3);
    const val = Math.round(from + (target - from) * ease);
    el.innerHTML = String(val) + deltaHtml;
    if (p < 1)
      requestAnimationFrame(step);
    else
      shown.set(key, target);
  };
  requestAnimationFrame(step);
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
    const deltaHtml = `<span class="kpi-delta">${deltaStr(prev?.[key], val)}</span>`;
    if (val === undefined || val === null) {
      shown.set(key, 0);
      el.innerHTML = "—";
    } else {
      countUp(el, key, val, deltaHtml);
    }
    const sp = document.getElementById(id + "-spark");
    if (sp) {
      sp.innerHTML = sparkline(kpiHistory.filter((s) => s[key] !== undefined).map((s) => s[key]), color);
    }
  }
}

// src/web/components/state.ts
function setPanelState(el, state, msg, onRetry) {
  if (!el)
    return;
  if (state === "loading") {
    el.innerHTML = `<div class="panel-state"><span class="spinner"></span> nalaganje …</div>`;
  } else if (state === "error") {
    el.innerHTML = `<div class="panel-state err">⚠️ ${msg || "Napaka pri nalaganju"}` + (onRetry ? ` <button class="btn mini" id="st-retry">Ponovi</button>` : "") + `</div>`;
    if (onRetry) {
      const b = el.querySelector("#st-retry");
      if (b)
        b.addEventListener("click", onRetry);
    }
  } else if (state === "empty") {
    el.innerHTML = `<div class="panel-state">${msg || "Ni podatkov"}</div>`;
  }
}

// src/web/components/avatar.ts
function initAvatar() {
  const svg = document.querySelector(".avatar-svg");
  const mouth = document.querySelector(".avatar-mouth");
  const eyeL = document.querySelector(".eye-l");
  const eyeR = document.querySelector(".eye-r");
  const status = document.getElementById("avatar-status");
  if (!svg || !mouth || !eyeL || !eyeR)
    return null;
  let blinkTimer = 0;
  const scheduleBlink = () => {
    blinkTimer = window.setTimeout(blink, 2400 + Math.random() * 1800);
  };
  function blink() {
    eyeL.setAttribute("ry", "1.2");
    eyeR.setAttribute("ry", "1.2");
    window.setTimeout(() => {
      eyeL.setAttribute("ry", "8");
      eyeR.setAttribute("ry", "8");
    }, 140);
    scheduleBlink();
  }
  scheduleBlink();
  let raf = 0;
  function lips() {
    const t0 = performance.now();
    const step = (now) => {
      if (!svg.classList.contains("speaking")) {
        mouth.setAttribute("ry", "3");
        return;
      }
      const t = (now - t0) / 1000;
      const a = 0.5 + 0.5 * Math.sin(t * 6.2) + 0.25 * Math.sin(t * 17.3 + 1.2);
      const open = Math.max(0.4, Math.min(1, a));
      mouth.setAttribute("ry", String(2 + open * 9));
      mouth.setAttribute("rx", String(13 - open * 3));
      raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
  }
  return {
    setSpeaking(on) {
      svg.classList.toggle("speaking", on);
      if (on)
        lips();
      else {
        cancelAnimationFrame(raf);
        mouth.setAttribute("ry", "3");
      }
    },
    setListening(on) {
      svg.classList.toggle("listening", on);
    },
    setStatus(text) {
      if (status)
        status.textContent = text;
    }
  };
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
var SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
function initChat() {
  const box = document.getElementById("chat-box");
  const input = document.getElementById("chat-input");
  const send = document.getElementById("chat-send");
  const voiceBtn = document.getElementById("voice-btn");
  if (!box || !input || !send)
    return;
  const avatar = initAvatar();
  let voiceMode = SpeechRec !== undefined;
  let busy = false;
  let rearmTimer = 0;
  const setStatus = (text) => {
    avatar?.setStatus(text);
  };
  const setRecording = (on) => {
    voiceBtn?.classList.toggle("recording", on);
    avatar?.setListening(on);
    if (on)
      setStatus("\uD83C\uDFA4 poslušam — govori …");
    else if (voiceMode)
      setStatus("pripravljen — govori ali piši");
  };
  const chatVisible = () => {
    const panel = document.querySelector('[data-view-panel="chat"]');
    return !!panel && panel.getBoundingClientRect().height > 0;
  };
  let rec = null;
  if (SpeechRec) {
    rec = new SpeechRec;
    rec.lang = "sl-SI";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (e) => {
      const t = e.results?.[0]?.[0]?.transcript ?? "";
      setRecording(false);
      if (t) {
        input.value = t;
        if (voiceMode && !busy)
          ask();
      }
    };
    rec.onerror = (e) => {
      const err = e?.error || "";
      if (err === "not-allowed" || err === "service-not-allowed") {
        voiceMode = false;
        voiceBtn?.classList.remove("recording");
        setStatus("\uD83D\uDEAB mikrofon blokiran — dovoli dostop v brskalniku, pa govori");
        return;
      }
      setRecording(false);
      rearm();
    };
    rec.onend = () => {
      setRecording(false);
      rearm();
    };
  } else {
    setStatus("\uD83D\uDDA5️ govorni vnos ni na voljo v tem brskalniku — piši sporočilo");
    if (voiceBtn)
      voiceBtn.style.display = "none";
  }
  const startRec = () => {
    if (!rec || !voiceMode || busy || !chatVisible())
      return;
    try {
      rec.start();
      setRecording(true);
    } catch {}
  };
  const rearm = () => {
    window.clearTimeout(rearmTimer);
    if (!voiceMode || busy)
      return;
    rearmTimer = window.setTimeout(() => {
      if (voiceMode && !busy)
        startRec();
    }, 450);
  };
  const stopRec = () => {
    window.clearTimeout(rearmTimer);
    try {
      rec?.stop?.();
    } catch {}
    setRecording(false);
  };
  if (voiceBtn)
    voiceBtn.addEventListener("click", () => {
      voiceMode = !voiceMode;
      if (voiceMode)
        startRec();
      else {
        stopRec();
        setStatus("\uD83D\uDED1 tihi način — piši ročno");
      }
    });
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.dataset.view === "chat")
        startRec();
      else
        stopRec();
    });
  });
  const speak = async (text) => {
    setStatus("\uD83D\uDD0A govorim …");
    try {
      const r = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: "Charon" })
      });
      const d = await r.json();
      if (d?.ok && d.base64) {
        const audio = new Audio(`data:${d.mime};base64,${d.base64}`);
        avatar?.setSpeaking(true);
        await new Promise((res) => {
          audio.onended = () => res();
          audio.onerror = () => res();
          audio.play().catch(() => res());
        });
        avatar?.setSpeaking(false);
        setStatus("pripravljen — govori ali piši");
        return;
      }
    } catch {}
    avatar?.setSpeaking(false);
    setStatus("pripravljen — govori ali piši");
  };
  const addMsg = (role, text) => {
    const d = document.createElement("div");
    d.className = `chat-msg ${role}`;
    d.textContent = text;
    box.appendChild(d);
    box.scrollTop = box.scrollHeight;
  };
  async function ask() {
    const text = input.value.trim();
    if (!text)
      return;
    busy = true;
    stopRec();
    addMsg("user", text);
    input.value = "";
    const busyEl = document.createElement("div");
    busyEl.className = "chat-msg ai chat-typing";
    busyEl.textContent = "…";
    box.appendChild(busyEl);
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
    } catch {}
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
      } catch {
        reply += `

⚠️ Napaka pri dodajanju v agendo.`;
      }
    }
    busyEl.textContent = reply;
    box.scrollTop = box.scrollHeight;
    busy = false;
    if (voiceMode) {
      await speak(reply);
      rearm();
    }
  }
  send.addEventListener("click", () => void ask());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter")
      ask();
  });
}

// src/web/components/agenda.ts
function fmtTime(ts) {
  if (!ts)
    return "";
  const d = new Date(ts * 1000);
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const hh = String(d.getHours()).padStart(2, "0");
  const mi = String(d.getMinutes()).padStart(2, "0");
  return `${dd}.${mm} ${hh}:${mi}`;
}
function fmtDur(s) {
  if (!s && s !== 0)
    return "";
  if (s < 60)
    return `${Math.round(s)}s`;
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${m}m ${r}s`;
}
function fmtBytes(n) {
  if (!n)
    return "0 B";
  if (n < 1024)
    return `${n} B`;
  if (n < 1048576)
    return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1048576).toFixed(1)} MB`;
}
function escapeHtml(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function initAgenda() {
  const list = document.getElementById("agenda-list");
  const input = document.getElementById("agenda-input");
  const addBtn = document.getElementById("agenda-add");
  if (!list)
    return;
  const modal = document.getElementById("agenda-modal");
  const closeCard = () => {
    modal?.classList.add("hidden");
  };
  document.getElementById("am-close")?.addEventListener("click", closeCard);
  modal?.addEventListener("click", (e) => {
    if (e.target === modal)
      closeCard();
  });
  const renderFiles = (res, it) => {
    const files = document.getElementById("am-files");
    const rootEl = document.getElementById("am-root");
    if (!files)
      return;
    if (rootEl)
      rootEl.textContent = res.root ? `\uD83D\uDCC1 ${res.root}` : "";
    const items = res.files || [];
    if (!items.length) {
      files.innerHTML = `<div class="am-empty">Ni shranjenih datotek — mapa <b>actions/${escapeHtml(it.target || "")}</b> je prazna ali ne obstaja.</div>`;
      return;
    }
    const dlAll = document.getElementById("am-dl-all");
    if (dlAll)
      dlAll.style.display = "";
    files.innerHTML = items.map((f) => {
      const depth = f.path.split("/").length - 1;
      const indent = `style="padding-left:${depth * 16}px"`;
      if (f.dir)
        return `<div class="am-dir" ${indent}>\uD83D\uDCC1 ${escapeHtml(f.path)}</div>`;
      const href = `/api/agenda/download?id=${encodeURIComponent(it.id)}&file=${encodeURIComponent(f.path)}`;
      return `<a class="am-file" ${indent} href="${href}" download title="${escapeHtml(f.path)}">
        <span>\uD83D\uDCC4 ${escapeHtml(f.path)}</span><span class="am-size">${fmtBytes(f.size)}</span></a>`;
    }).join("");
  };
  const openCard = (it) => {
    const title = document.getElementById("am-title");
    const meta = document.getElementById("am-meta");
    const files = document.getElementById("am-files");
    const rootEl = document.getElementById("am-root");
    const dlAll = document.getElementById("am-dl-all");
    if (!modal)
      return;
    if (title)
      title.textContent = `Naloga · ${it.status}`;
    if (meta)
      meta.innerHTML = `<span><b>cilj:</b> ${escapeHtml(it.target || "—")}</span>` + `<span><b>izvedba:</b> ${fmtDur(it.duration_s) || "—"}</span>` + `<span><b>sprememba:</b> ${fmtTime(it.updated_at)}</span>`;
    if (rootEl)
      rootEl.textContent = "";
    if (files)
      files.innerHTML = '<span class="muted">nalaganje …</span>';
    if (dlAll) {
      dlAll.style.display = "none";
      dlAll.href = `/api/agenda/download-all?id=${encodeURIComponent(it.id)}`;
    }
    modal.classList.remove("hidden");
    getJSON(`/api/agenda/files?id=${encodeURIComponent(it.id)}`).then((res) => renderFiles(res, it)).catch(() => {
      if (files)
        files.innerHTML = '<div class="am-empty">Datoteke niso na voljo.</div>';
    });
  };
  const statusClass = (s) => s === "done" ? "s-ok" : s === "failed" ? "s-crit" : s === "running" ? "s-run" : "s-warn";
  const render = (items) => {
    if (!items.length) {
      list.innerHTML = '<div class="agenda-empty">Agenda je prazna — dodaj nalogo.</div>';
      return;
    }
    const sorted = [...items].sort((a, b) => {
      const at = a.created_at ?? a.updated_at ?? 0;
      const bt = b.created_at ?? b.updated_at ?? 0;
      return bt - at;
    });
    list.innerHTML = sorted.map((it) => {
      const claimed = it.claimed_by ? ` · ${it.claimed_by}` : "";
      const worker = it.result_worker ? ` · → ${it.result_worker}` : "";
      const when = fmtTime(it.updated_at);
      const dur = it.duration_s ? ` · ${fmtDur(it.duration_s)}` : "";
      return `<div class="agenda-item" data-id="${it.id}" title="Klikni za shranjene datoteke">
        <div class="agenda-top"><span class="s ${statusClass(it.status)}">${it.status}</span>
          <span class="agenda-target">${it.target || ""}${claimed}${worker}</span>
          <span class="agenda-time">${when}${dur}</span>
          <button class="agenda-del" data-del="${it.id}" title="Odstrani">✕</button>
        </div>
        <div class="agenda-goal">${String(it.goal || "").replace(/</g, "&lt;")}</div>
      </div>`;
    }).join("");
    list.querySelectorAll("[data-del]").forEach((b) => {
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        fetch("/api/agenda/delete", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id: b.dataset.del })
        }).then(load);
      });
    });
    list.querySelectorAll(".agenda-item").forEach((el) => {
      el.addEventListener("click", () => {
        const it = sorted.find((x) => x.id === el.dataset.id);
        if (it)
          openCard(it);
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

// src/web/components/chief.ts
function escapeHtml2(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function mdToSafeHtml(md) {
  const out = [];
  for (const raw of md.split(`
`)) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) {
      out.push('<div class="chief-gap"></div>');
      continue;
    }
    const h2 = line.match(/^##\s+(.*)$/);
    if (h2) {
      out.push(`<h4>${escapeHtml2(h2[1])}</h4>`);
      continue;
    }
    const h1 = line.match(/^#\s+(.*)$/);
    if (h1) {
      out.push(`<h3>${escapeHtml2(h1[1])}</h3>`);
      continue;
    }
    if (/^\s*[-*]\s+/.test(line)) {
      out.push(`<div class="chief-li">• ${escapeHtml2(line.replace(/^\s*[-*]\s+/, ""))}</div>`);
      continue;
    }
    out.push(`<div>${escapeHtml2(line)}</div>`);
  }
  return out.join(`
`);
}
function initChief() {
  const digestEl = document.getElementById("chief-digest");
  const metaEl = document.getElementById("chief-meta");
  const input = document.getElementById("chief-input");
  const sendBtn = document.getElementById("chief-send");
  const msgEl = document.getElementById("chief-msg");
  if (!digestEl)
    return;
  const render = (r) => {
    if (metaEl) {
      const n = (r.lessons || []).length;
      metaEl.textContent = n ? `naučeno: ${n} lekcij` : "dnevno poročilo";
    }
    if (!r.digest) {
      digestEl.innerHTML = '<div class="muted">Ni še poročila — zaženi <code>python -m chief --report</code> ali počakaj na dnevni beat.</div>';
      return;
    }
    digestEl.innerHTML = mdToSafeHtml(r.digest);
  };
  const load = () => {
    getJSON("/api/chief").then(render).catch(() => {
      if (digestEl)
        digestEl.innerHTML = '<div class="muted">Chief ni dosegljiv.</div>';
    });
  };
  const send = () => {
    const text = input?.value.trim() ?? "";
    if (!text)
      return;
    if (msgEl) {
      msgEl.textContent = "…";
      msgEl.className = "chief-msg";
    }
    fetch("/api/chief/correct", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text })
    }).then((r) => r.json()).then((r) => {
      if (msgEl) {
        msgEl.textContent = r.ok ? "✅ Popravek shranjen — učenje posodobljeno." : "❌ Popravek ni bil shranjen.";
        msgEl.className = `chief-msg ${r.ok ? "ok" : "err"}`;
      }
      if (input)
        input.value = "";
      setTimeout(load, 400);
    }).catch(() => {
      if (msgEl) {
        msgEl.textContent = "❌ Napaka pri pošiljanju.";
        msgEl.className = "chief-msg err";
      }
    });
  };
  if (sendBtn)
    sendBtn.addEventListener("click", send);
  if (input)
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter")
        send();
    });
  load();
  setInterval(load, 60000);
}

// src/web/components/graph.ts
var COLORS = { core: "#ffd166", action: "#4fc3ff", root: "#5e7ba0" };
var W = 900;
var H = 640;
var DRIFT_AMP = 2.5;
var DRIFT_T = 0.3;
function initGraph() {
  const svg = document.getElementById("graph-svg");
  const tip = document.getElementById("graph-tip");
  const stats = document.getElementById("graph-stats");
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
    render(svg, tip, stats, nodes, links);
  }).catch(() => {});
}
function render(svg, tip, stats, nodes, links) {
  svg.setAttribute("viewBox", `${-W / 2} ${-H / 2} ${W} ${H}`);
  const group = document.createElementNS("http://www.w3.org/2000/svg", "g");
  group.setAttribute("id", "graph-main");
  const degree = new Map;
  for (const l of links) {
    degree.set(l.source.id, (degree.get(l.source.id) || 0) + 1);
    degree.set(l.target.id, (degree.get(l.target.id) || 0) + 1);
  }
  const maxDeg = Math.max(1, ...degree.values());
  const rFor = (id) => 3.5 + (degree.get(id) || 0) / maxDeg * 10;
  const topN = 5;
  const topIds = new Set([...degree.entries()].sort((a, b) => b[1] - a[1]).slice(0, topN).map(([id]) => id));
  const lineMarkup = links.map((l) => `<line x1="${l.source.x}" y1="${l.source.y}" x2="${l.target.x}" y2="${l.target.y}"
       stroke="#243a54" stroke-width="1" data-from="${l.source.id}" data-to="${l.target.id}"/>`).join("");
  const circleMarkup = nodes.map((n) => `<circle cx="${n.x}" cy="${n.y}" r="${rFor(n.id)}" fill="${COLORS[n.group] || "#888"}"
       data-id="${n.id}" data-label="${n.label}" data-group="${n.group}" data-degree="${degree.get(n.id) || 0}"/>`).join("");
  const labelMarkup = nodes.filter((n) => topIds.has(n.id)).map((n) => `<text class="graph-label" x="${n.x}" y="${n.y + 21}" text-anchor="middle"
       fill="${COLORS[n.group] || "#9aa7b5"}" data-id="${n.id}">${String(n.label).replace(/</g, "&lt;")}</text>`).join("");
  group.innerHTML = lineMarkup + circleMarkup + labelMarkup;
  svg.appendChild(group);
  if (stats)
    stats.textContent = `${nodes.length} vozlišč · ${links.length} povezav · max ${maxDeg}°`;
  const adj = new Map;
  for (const l of links) {
    (adj.get(l.source.id) || adj.set(l.source.id, new Set).get(l.source.id)).add(l.target.id);
    (adj.get(l.target.id) || adj.set(l.target.id, new Set).get(l.target.id)).add(l.source.id);
  }
  const circles = group.querySelectorAll("circle");
  const lines = group.querySelectorAll("line");
  const labelEls = new Map;
  group.querySelectorAll("text.graph-label").forEach((t) => {
    labelEls.set(t.dataset.id, t);
  });
  circles.forEach((c) => {
    c.addEventListener("mouseenter", () => {
      const id = c.dataset.id;
      const neigh = adj.get(id) || new Set;
      circles.forEach((x) => {
        const xid = x.dataset.id;
        x.style.opacity = xid === id || neigh.has(xid) ? "1" : "0.12";
      });
      lines.forEach((l) => {
        const from = l.dataset.from;
        const to = l.dataset.to;
        l.style.opacity = from === id || to === id || neigh.has(from) || neigh.has(to) ? "0.8" : "0.08";
      });
      labelEls.forEach((t, lid) => {
        t.style.opacity = lid === id || neigh.has(lid) ? "1" : "0.15";
      });
      if (tip) {
        const deg = c.dataset.degree || "0";
        tip.textContent = `${c.dataset.label} (${c.dataset.group}) · ${deg} povezav`;
        tip.classList.add("show");
      }
    });
    c.addEventListener("mouseleave", () => {
      circles.forEach((x) => x.style.opacity = "1");
      lines.forEach((x) => x.style.opacity = "0.6");
      labelEls.forEach((t) => t.style.opacity = "1");
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
  const phases = new Map(nodes.map((n, i) => [n.id, i * 2.399963 % (Math.PI * 2)]));
  const t0 = performance.now();
  const frame = (now) => {
    const t = (now - t0) / 1000;
    const offset = (id) => {
      const ph = phases.get(id) || 0;
      return [
        Math.sin(t * DRIFT_T + ph) * DRIFT_AMP,
        Math.cos(t * DRIFT_T * 0.77 + ph * 1.7) * DRIFT_AMP
      ];
    };
    nodes.forEach((n, i) => {
      const [ox, oy] = offset(n.id);
      const c = circles[i];
      c.setAttribute("cx", String(n.x + ox));
      c.setAttribute("cy", String(n.y + oy));
      const lab = labelEls.get(n.id);
      if (lab) {
        lab.setAttribute("x", String(n.x + ox));
        lab.setAttribute("y", String(n.y + oy + 21));
      }
    });
    links.forEach((l, j) => {
      const [sx0, sy0] = offset(l.source.id);
      const [tx0, ty0] = offset(l.target.id);
      const el = lines[j];
      el.setAttribute("x1", String(l.source.x + sx0));
      el.setAttribute("y1", String(l.source.y + sy0));
      el.setAttribute("x2", String(l.target.x + tx0));
      el.setAttribute("y2", String(l.target.y + ty0));
    });
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
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
    const loadFleet = () => {
      if (!fleetEl)
        return;
      setPanelState(fleetEl, "loading");
      fetchFleet().then((d) => {
        if (isSessionExpired())
          return;
        if (!d?.ok || !d.agenda) {
          setPanelState(fleetEl, "error", "Napačen odziv serverja", loadFleet);
          return;
        }
        if (!Object.keys(d.workers || {}).length && !d.activity?.length) {
          setPanelState(fleetEl, "empty", "Ni aktivnih workerjev (master / standalone)");
          renderFleet(fleetEl, d);
          return;
        }
        renderFleet(fleetEl, d);
      }).catch(() => {
        if (!isSessionExpired())
          setPanelState(fleetEl, "error", "Master ni dosegljiv", loadFleet);
      });
    };
    loadFleet();
    setInterval(loadFleet, 15000);
    if (feedEl) {
      getJSON("/api/events").then((r) => connectFeed(feedEl, dotEl, () => {}, r.events || [])).catch(() => connectFeed(feedEl, dotEl, () => {}));
    }
    initChat();
    initAgenda();
    initChief();
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
