// portal.js - interface du portail de développement C64 (sans dépendance).
// Les actions appellent l'API de tools/portal.py, qui appelle les outils.
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) node.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) node.append(c instanceof Node ? c : document.createTextNode(c));
  return node;
};

const state = {
  status: null,
  programs: [],
  meta: null,
  job: null,          // tâche suivie
  jobNext: 0,
  monitorAvailable: false,
  monitorState: null,
  screenMode: "image",
  liveBusy: false,
};

// --- API ----------------------------------------------------------------------
async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (method === "POST") {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body || {});
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch { data = { error: res.statusText }; }
  if (!res.ok) {
    const err = new Error((data && data.error) || res.statusText);
    err.status = res.status;
    throw err;
  }
  return data;
}

function notice(msg, kind = "error") {
  const n = $("#notice");
  if (!msg) { n.hidden = true; return; }
  n.textContent = msg;
  n.className = "notice" + (kind === "info" ? " info" : "");
  n.hidden = false;
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => { n.hidden = true; }, kind === "info" ? 4000 : 9000);
}

// --- Tâches -------------------------------------------------------------------
async function startJob(url, body) {
  try {
    const { job } = await api("POST", url, body);
    followJob(job);
  } catch (e) {
    notice(e.message);
  }
}

function followJob(job) {
  state.job = job;
  state.jobNext = 0;
  $("#job-output").textContent = "";
  $("#job-files").replaceChildren();
  renderJobHead(job);
  pollJob();
}

function renderJobHead(job) {
  $("#job-title").textContent = job ? job.title : "Aucune tâche";
  const badge = $("#job-state");
  const labels = { running: "en cours", ok: "réussie", failed: "échec" };
  badge.textContent = job ? labels[job.state] || job.state : "";
  badge.className = "badge " + (job ? job.state : "");
}

async function pollJob() {
  const job = state.job;
  if (!job) return;
  try {
    const j = await api("GET", `/api/jobs/${job.id}?since=${state.jobNext}`);
    if (state.job !== job) return;
    if (j.lines.length) {
      const out = $("#job-output");
      const atBottom = out.scrollTop + out.clientHeight >= out.scrollHeight - 20;
      out.textContent += (out.textContent ? "\n" : "") + j.lines.join("\n");
      if (atBottom) out.scrollTop = out.scrollHeight;
    }
    state.jobNext = j.next;
    Object.assign(job, j);
    renderJobHead(job);
    if (j.state === "running") {
      setTimeout(pollJob, 400);
    } else {
      renderJobFiles(j.files);
      refreshPrograms();
      refreshStatus();
      if (j.state === "failed") notice(`« ${j.title} » a échoué (code ${j.rc}).`);
    }
  } catch (e) {
    setTimeout(pollJob, 1500);
  }
}

function renderJobFiles(files) {
  const box = $("#job-files");
  box.replaceChildren();
  for (const f of files || []) {
    const url = `/files/${f}?t=${Date.now()}`;
    if (f.endsWith(".png")) {
      box.append(el("a", { href: url, target: "_blank", title: f },
        el("img", { src: url, width: 384, height: 272, alt: f })));
    } else {
      box.append(el("a", { href: url + "&download=1", class: "btn ghost small" }, f));
    }
  }
}

// --- État général -------------------------------------------------------------
function setChip(id, text, cls) {
  const c = $(id);
  c.textContent = text;
  c.className = "chip " + (cls || "");
}

async function refreshStatus() {
  let s;
  try {
    s = await api("GET", "/api/status");
  } catch (e) {
    setChip("#chip-vice", "Portail injoignable", "err");
    return;
  }
  state.status = s;
  $("#git").textContent = s.git ? `dernier commit : ${s.git}` : "";
  const v = s.vice;
  if (v.running && v.state === "starting") {
    setChip("#chip-vice", `VICE : ${v.prog || "?"} (démarrage…)`, "busy");
  } else if (v.running) {
    const mode = v.mode === "headless" ? "invisible" : "visible";
    setChip("#chip-vice", `VICE : ${v.prog || "?"} (${mode}${v.warp ? ", warp" : ""})`, "ok");
  } else {
    setChip("#chip-vice", "VICE : arrêté", "");
  }
  const m = s.monitor;
  const wasAvailable = state.monitorAvailable;
  const prevState = state.monitorState;
  state.monitorAvailable = !!m.available;
  state.monitorState = m.state;
  if (m.available) {
    const stopped = (m.state || "").startsWith("stopped");
    setChip("#chip-monitor", "Moniteur : " + (stopped ? m.state.replace("stopped", "arrêté") : "en cours"),
      stopped ? "warn" : "ok");
  } else if (v.running && v.monitor) {
    setChip("#chip-monitor", "Moniteur : occupé/injoignable", "warn");
  } else {
    setChip("#chip-monitor", "Moniteur : inactif", "");
  }
  if (s.job && s.job.state === "running") setChip("#chip-job", "Tâche : " + s.job.title, "busy");
  else setChip("#chip-job", "Tâche : aucune", "");
  // Une tâche lancée ailleurs (autre onglet) : on la suit aussi.
  if (s.job && s.job.state === "running" && (!state.job || state.job.id !== s.job.id)) {
    followJob(s.job);
  }

  $("#card-monitor").classList.toggle("monitor-off", !m.available);
  $("#monitor-hint").textContent = m.available
    ? `${v.prog || ""} — ${m.state === "running" ? "en cours d'exécution" : m.state}`
    : (v.running && v.monitor ? (m.error || "moniteur occupé") : "Lancez un programme avec la case « Moniteur ».");
  if (m.available && (!wasAvailable || prevState !== m.state)) {
    refreshRegs();
    refreshBreakpoints();
  }
  if (!m.available) {
    $("#live").hidden = true;
    $("#live-empty").hidden = state.screenMode !== "image";
    $("#regs").textContent = "—";
  }
  renderProgramsRunning();
}

// --- Programmes ---------------------------------------------------------------
async function refreshPrograms() {
  try {
    const { programs } = await api("GET", "/api/programs");
    state.programs = programs;
    renderPrograms();
  } catch (e) {
    notice("Liste des programmes : " + e.message);
  }
}

function fmtSize(n) { return n == null ? "" : `${n} o`; }
function fmtTime(t) {
  if (!t) return "";
  const d = new Date(t * 1000);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderPrograms() {
  const tbody = $("#programs");
  tbody.replaceChildren();
  if (!state.programs.length) {
    tbody.append(el("tr", {}, el("td", { colspan: 3, class: "muted" }, "Aucun programme (src/ ou examples/)")));
    return;
  }
  for (const p of state.programs) {
    const built = p.built
      ? el("span", {}, `${fmtSize(p.size)} · ${fmtTime(p.mtime)}`, el("br"),
          el("span", { class: "muted small" }, `${p.labels} labels`))
      : el("span", { class: "muted" }, "non compilé");
    const actions = el("div", { class: "actions" },
      el("button", { class: "btn small", onclick: () => launch(p.name) }, "Lancer"),
      el("button", { class: "btn small ghost", onclick: () => capture(p.name) }, "Capture"),
      el("button", { class: "btn small ghost", onclick: () => showSources(p) }, "Sources"),
      p.built ? el("a", { class: "btn small ghost", href: `/files/${p.name}.prg?download=1` }, ".prg") : "");
    tbody.append(el("tr", { "data-prog": p.name },
      el("td", { class: "name" }, p.name, el("span", { class: "running-tag" })),
      el("td", {}, built),
      el("td", {}, actions)));
  }
  renderProgramsRunning();
}

function renderProgramsRunning() {
  const v = state.status && state.status.vice;
  for (const tr of $$("#programs tr[data-prog]")) {
    const tag = $(".running-tag", tr);
    if (tag) tag.textContent = v && v.running && v.prog === tr.dataset.prog ? "● en cours" : "";
  }
}

function launch(prog) {
  startJob("/api/launch", {
    prog,
    mode: $("#opt-mode").value,
    warp: $("#opt-warp").checked,
    monitor: $("#opt-monitor").checked,
  });
}

function capture(prog) {
  startJob("/api/capture", {
    prog,
    cycles: parseInt($("#opt-cycles").value, 10) || 5000000,
    warp: true,
  });
}

async function showSources(p) {
  const box = $("#sources");
  $("#sources-title").textContent = p.name;
  const tabs = $("#sources-tabs");
  tabs.replaceChildren();
  const body = $("#sources-body");
  body.textContent = p.sources.length ? "" : "Aucun fichier source.";
  box.hidden = false;
  const open = async (path, btn) => {
    $$(".tab", tabs).forEach((t) => t.classList.toggle("active", t === btn));
    try {
      const res = await fetch(`/source/${encodeURI(path)}`);
      body.textContent = res.ok ? await res.text() : `Erreur ${res.status}`;
    } catch (e) {
      body.textContent = e.message;
    }
  };
  p.sources.forEach((path, i) => {
    const btn = el("button", { class: "tab", onclick: () => open(path, btn) }, path.split("/").pop());
    tabs.append(btn);
    if (i === 0) open(path, btn);
  });
  box.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// --- Moniteur -----------------------------------------------------------------
async function dbg(cmd, args = []) {
  return api("POST", "/api/dbg", { cmd, args });
}

function dbgText(r) {
  return [r.stdout.trimEnd(), r.stderr.trimEnd()].filter(Boolean).join("\n") || `(code ${r.rc})`;
}

async function refreshRegs() {
  if (!state.monitorAvailable) return;
  try {
    const r = await dbg("regs");
    const box = $("#regs");
    if (r.rc !== 0) { box.textContent = dbgText(r); return; }
    const line = r.stdout.trim();
    const parts = line.match(/(\w+)=(\S+)/g) || [];
    box.replaceChildren(...parts.map((p) => {
      const [k, v] = p.split("=");
      return el("span", { class: "r" }, el("b", {}, k), " ", v);
    }));
    const st = state.monitorState || "";
    const stopped = st.startsWith("stopped");
    box.append(el("span", { class: "state " + (stopped ? "stopped" : "running") },
      stopped ? "arrêté" : "en cours"));
  } catch (e) {
    $("#regs").textContent = e.message;
  }
}

async function refreshBreakpoints() {
  if (!state.monitorAvailable) return;
  const list = $("#bp-list");
  try {
    const r = await dbg("list");
    list.replaceChildren();
    const lines = r.stdout.trim().split("\n").filter((l) => l.startsWith("checkpoint"));
    if (!lines.length) list.append(el("li", { class: "muted" }, "aucun"));
    for (const l of lines) {
      const num = l.split(" ")[1];
      list.append(el("li", {},
        el("span", {}, l.replace(/^checkpoint \d+ /, `#${num} `)),
        el("button", { class: "btn small ghost", onclick: () => monitorAction("delete", [num]) }, "Supprimer")));
    }
  } catch (e) {
    list.replaceChildren(el("li", { class: "muted" }, e.message));
  }
}

async function monitorAction(cmd, args = [], out = "#dbg-output") {
  if (cmd === "quit" && !confirm("Arrêter VICE ?")) return;
  try {
    const r = await dbg(cmd, args);
    if (out) $(out).textContent = `$ dbg.py ${[cmd, ...args].join(" ")}\n${dbgText(r)}`;
    if (r.rc !== 0 && out !== "#dbg-output") notice(dbgText(r));
  } catch (e) {
    notice(e.message);
  }
  await refreshStatus();
  refreshRegs();
  refreshBreakpoints();
  refreshScreen();
}

function setScreenMode(mode) {
  state.screenMode = mode;
  $$(".tab[data-screen]").forEach((t) => t.classList.toggle("active", t.dataset.screen === mode));
  $("#screen-text").hidden = mode !== "text";
  $("#live").hidden = mode !== "image" || !state.monitorAvailable;
  $("#live-empty").hidden = mode !== "image" || state.monitorAvailable;
  refreshScreen();
}

async function refreshScreen() {
  if (!state.monitorAvailable) return;
  if (state.screenMode === "text") {
    try {
      const r = await dbg("screen", $("#screen-lower").checked ? ["--lower"] : []);
      $("#screen-text").textContent = r.rc === 0
        ? r.stdout.trimEnd().split("\n").map((l) => l.replace(/^\d\d\|/, "").replace(/\|$/, "")).join("\n")
        : dbgText(r);
    } catch (e) {
      $("#screen-text").textContent = e.message;
    }
    return;
  }
  if (state.liveBusy) return;
  state.liveBusy = true;
  const img = $("#live");
  const url = `/live.png?t=${Date.now()}`;
  const probe = new Image();
  probe.onload = () => {
    img.src = probe.src;
    img.hidden = state.screenMode !== "image";
    $("#live-empty").hidden = true;
    $("#screen-save").href = probe.src;
    state.liveBusy = false;
  };
  probe.onerror = () => {
    state.liveBusy = false;
  };
  probe.src = url;
}

// --- Journaux, cohérence, méta ----------------------------------------------
async function refreshLog() {
  const name = $("#log-select").value;
  try {
    const r = await api("GET", `/api/logs?name=${encodeURIComponent(name)}&lines=300`);
    const out = $("#log-output");
    out.textContent = r.text || `(${r.path} vide ou absent)`;
    out.scrollTop = out.scrollHeight;
  } catch (e) {
    notice(e.message);
  }
}

async function refreshSync() {
  try {
    const r = await api("GET", "/api/selfcheck");
    setChip("#chip-sync", r.ok ? "Cohérence : OK" : `Cohérence : ${r.problems.length} écart(s)`, r.ok ? "ok" : "err");
    $("#sync-summary").replaceChildren(r.ok
      ? el("p", { class: "sync-ok" }, "Le portail est en phase avec les outils.")
      : el("div", {}, el("p", { class: "sync-bad" }, "Écarts entre les outils et le portail :"),
          el("ul", { class: "problems" }, r.problems.map((p) => el("li", {}, p)))));
    const box = $("#sync-details");
    box.replaceChildren();
    for (const [tool, d] of Object.entries(r.details)) {
      const rows = [];
      const items = d.flags || d.targets || d.commands || [];
      for (const it of items) {
        const used = d.used && d.used[it];
        const excl = d.excluded && d.excluded[it];
        const doc = d.documented && d.documented[it];
        let tag = used ? el("span", { class: "tag used" }, "exposé")
          : excl ? el("span", { class: "tag excluded" }, "exclu")
          : d.commands ? el("span", { class: "tag used" }, "console") : el("span", { class: "tag" }, "?");
        const why = used || excl || (doc ? `${doc[0]} — ${doc[1]}`.replace(/^ — /, "") : "");
        rows.push(el("tr", {}, el("td", {}, it), el("td", {}, tag), el("td", { class: "muted" }, why)));
      }
      box.append(el("details", {}, el("summary", {}, `${tool} (${items.length})`), el("table", {}, rows)));
    }
  } catch (e) {
    setChip("#chip-sync", "Cohérence : ?", "warn");
  }
}

async function loadMeta() {
  try {
    const m = await api("GET", "/api/meta");
    state.meta = m;
    const sel = $("#dbg-cmd");
    sel.replaceChildren(...m.dbg.map((c) => el("option", { value: c.name }, c.name)));
    sel.value = "mem";
    updateDbgHelp();
    $("#test-select").replaceChildren(...m.tests.map((t) => el("option", { value: t }, t)));
    $("#log-select").replaceChildren(...m.logs.map((l) => el("option", { value: l }, l)));
    if (m.logs.includes("vice")) $("#log-select").value = "vice";
    $("#opt-cycles").value = m.defaults.cycles;
  } catch (e) {
    notice("Méta-données : " + e.message);
  }
}

function updateDbgHelp() {
  const name = $("#dbg-cmd").value;
  const c = state.meta && state.meta.dbg.find((x) => x.name === name);
  $("#dbg-help").textContent = c ? `${c.name} ${c.args}  —  ${c.help}` : "";
  $("#dbg-args").placeholder = c && c.args ? c.args : "(sans argument)";
}

// --- Branchements ---------------------------------------------------------------
function wire() {
  const actions = {
    build: () => startJob("/api/build"),
    test: () => startJob("/api/test"),
    "test-one": () => startJob("/api/test", { name: $("#test-select").value }),
    clean: () => confirm("Arrêter VICE et supprimer build/ ?") && startJob("/api/clean"),
    "install-check": () => startJob("/api/install-check"),
    stop: () => stopVice(false),
    "stop-all": () => stopVice(true),
  };
  for (const b of $$("[data-action]")) b.addEventListener("click", () => actions[b.dataset.action]());

  for (const b of $$("[data-dbg]")) {
    b.addEventListener("click", () => {
      const cmd = b.dataset.dbg;
      monitorAction(cmd, cmd === "wait" ? ["10"] : []);
    });
  }
  for (const t of $$(".tab[data-screen]")) t.addEventListener("click", () => setScreenMode(t.dataset.screen));
  $("#screen-refresh").addEventListener("click", refreshScreen);
  $("#screen-lower").addEventListener("change", refreshScreen);
  $("#sources-close").addEventListener("click", () => { $("#sources").hidden = true; });

  $("#bp-form").addEventListener("submit", (e) => e.preventDefault());
  for (const b of $$("#bp-form button")) {
    b.addEventListener("click", () => {
      const addr = $("#bp-addr").value.trim();
      if (addr) monitorAction(b.dataset.kind, addr.split(/\s+/));
    });
  }
  $("#mem-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const addr = $("#mem-addr").value.trim();
    if (addr) monitorAction("mem", [addr, String($("#mem-len").value || 64)], "#mem-output");
  });
  $("#poke-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const addr = $("#poke-addr").value.trim();
    const vals = $("#poke-vals").value.trim().split(/[\s,]+/).filter(Boolean);
    if (addr && vals.length) monitorAction("poke", [addr, ...vals], "#mem-output");
  });
  $("#label-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = $("#label-q").value.trim();
    const box = $("#label-results");
    if (!q) return;
    try {
      const r = await dbg("label", [q]);
      box.replaceChildren();
      if (r.rc !== 0) { box.append(el("span", { class: "muted" }, dbgText(r))); return; }
      for (const line of r.stdout.trim().split("\n").slice(0, 200)) {
        const [name, addr] = line.split(" = ");
        box.append(el("button", {
          title: "Utiliser cette adresse",
          onclick: () => { for (const id of ["#bp-addr", "#mem-addr", "#poke-addr"]) $(id).value = name; },
        }, `${name} ${addr}`));
      }
    } catch (err) {
      notice(err.message);
    }
  });
  $("#dbg-cmd").addEventListener("change", updateDbgHelp);
  $("#dbg-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const args = $("#dbg-args").value.trim().split(/\s+/).filter(Boolean);
    runConsole($("#dbg-cmd").value, args);
  });
  $("#log-select").addEventListener("change", refreshLog);
  $("#log-refresh").addEventListener("click", refreshLog);
  $("#sync-refresh").addEventListener("click", refreshSync);
}

async function runConsole(cmd, args) {
  if (cmd === "quit" && !confirm("Arrêter VICE ?")) return;
  const out = $("#dbg-output");
  out.textContent = `$ dbg.py ${[cmd, ...args].join(" ")}\n…`;
  try {
    const r = await dbg(cmd, args);
    out.textContent = `$ dbg.py ${[cmd, ...args].join(" ")}\n${dbgText(r)}`;
    for (const f of r.files || []) {
      out.append("\n", el("a", { href: `/files/${f}?download=1` }, `Télécharger ${f}`));
    }
  } catch (e) {
    out.textContent = e.message;
  }
  refreshStatus();
}

async function stopVice(all) {
  try {
    const r = await api("POST", "/api/stop", { all });
    notice(r.output.trim() || "VICE arrêté", "info");
  } catch (e) {
    notice(e.message);
  }
  refreshStatus();
}

// --- Démarrage -----------------------------------------------------------------
async function main() {
  wire();
  await loadMeta();
  await Promise.all([refreshStatus(), refreshPrograms(), refreshSync()]);
  setScreenMode("image");
  refreshLog();
  setInterval(refreshStatus, 2000);
  setInterval(refreshPrograms, 15000);
  setInterval(() => {
    if ($("#screen-auto").checked && state.monitorAvailable && !document.hidden) refreshScreen();
  }, 1000);
  // Dernière tâche connue (rechargement de page pendant une tâche).
  try {
    const { jobs } = await api("GET", "/api/jobs");
    if (jobs.length && !state.job) followJob(jobs[0]);
  } catch { /* rien */ }
}

main();
