// portal.js - interface du portail de développement C64 (sans dépendance).
// Les actions appellent l'API de tools/portal.py, qui appelle les outils.
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));
const el = (tag, attrs = {}, ...children) => {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) { if (v) node.addEventListener(k.slice(2), v); }
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
  if (v.prog !== state.lastProg) {
    // Autre programme : infos source et segments à recharger.
    state.lastProg = v.prog;
    code.info = null;
    code.file = null;
    loadSegments();
  }
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
  $("#screen-note").hidden = !(m.available && (m.state || "").startsWith("stopped"));
  $("#monitor-hint").textContent = m.available
    ? `${v.prog || ""} — ${m.state === "running" ? "en cours d'exécution" : m.state}`
    : (v.running && v.monitor ? (m.error || "moniteur occupé") : "Lancez un programme avec la case « Moniteur ».");
  if (m.available && (!wasAvailable || prevState !== m.state)) {
    refreshRegs();
    refreshBreakpoints().then(refreshCode);
    if (!wasAvailable) refreshMemory().then(applyDeepLink);
  }
  if (!m.available && wasAvailable) refreshCode();
  $("#mem-hint").textContent = m.available
    ? (mem.data ? "" : "Cliquez « Lire » ou activez Auto.")
    : "Nécessite un programme lancé avec le moniteur.";
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
    // « checkpoint 1 $0821-$0830 (print) type=exec ... »
    state.bps = lines.map((l) => {
      const m = l.match(/^checkpoint (\d+) \$([0-9a-f]{4})(?:-\$([0-9a-f]{4}))?.*type=(\S+)/);
      return m ? { num: m[1], start: parseInt(m[2], 16), end: parseInt(m[3] || m[2], 16), type: m[4] } : null;
    }).filter(Boolean);
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

function execBpAt(addr) {
  return (state.bps || []).find((b) => b.type.includes("exec") && b.start <= addr && addr <= b.end);
}

async function toggleBreakpoint(addr) {
  const bp = execBpAt(addr);
  if (bp) await monitorAction("delete", [bp.num], null);
  else await monitorAction("break", ["$" + hex4(addr)], null);
}

const hex2 = (n) => n.toString(16).padStart(2, "0");
const hex4 = (n) => n.toString(16).padStart(4, "0");

// --- Vue Code -----------------------------------------------------------------
const code = { mode: "disasm", addr: null, info: null, infoKey: null, file: null, where: null };

function setCodeMode(mode) {
  code.mode = mode;
  $$(".tab[data-code]").forEach((t) => t.classList.toggle("active", t.dataset.code === mode));
  refreshCode();
}

function scrollToRow(view, row) {
  if (!row) return;
  // Centre la ligne dans la vue sans faire défiler la page.
  view.scrollTop = row.offsetTop - view.clientHeight / 2 + row.offsetHeight / 2;
}

async function refreshWhere() {
  const r = await dbg("where");
  const line = r.stdout.trim();
  // « PC=0831 (loop) examples/hello/hello.s:38  jmp loop »
  const m = line.match(/^PC=([0-9a-f]{4})(?: \(([^)]*)\))? (?:(\S+):(\d+)  ?(.*)|\(pas d'info source\))$/);
  code.where = m ? { pc: parseInt(m[1], 16), label: m[2], file: m[3], line: m[4] ? +m[4] : null, text: m[5] } : null;
  const box = $("#code-where");
  if (!code.where) { box.textContent = line || dbgText(r); return; }
  const w = code.where;
  box.replaceChildren(el("b", {}, `PC=$${hex4(w.pc)}`), w.label ? ` (${w.label})` : "",
    w.file ? `  ${w.file}:${w.line}  ` : "  (pas d'info source)",
    w.text ? el("span", {}, w.text) : "");
}

async function refreshCode() {
  const view = $("#code-view");
  if (!state.monitorAvailable) {
    view.replaceChildren(el("div", { class: "muted pad" },
      "Lancez un programme avec la case « Moniteur », puis Pause ou un point d'arrêt."));
    $("#code-where").textContent = "—";
    $("#code-files").hidden = true;
    return;
  }
  try {
    await refreshWhere();
    if (code.mode === "disasm") await renderDisasm(view);
    else await renderSource(view);
  } catch (e) {
    view.replaceChildren(el("div", { class: "muted pad" }, e.message));
  }
}

async function renderDisasm(view) {
  $("#code-files").hidden = true;
  const follow = $("#code-follow").checked || !code.addr;
  const r = await dbg("disasm", follow ? ["pc", "40"] : [code.addr, "40"]);
  if (r.rc !== 0) { view.replaceChildren(el("div", { class: "muted pad" }, dbgText(r))); return; }
  const rows = [];
  let current = null;
  for (const line of r.stdout.split("\n")) {
    let m = line.match(/^ {10}(\S+):$/);
    if (m) {
      rows.push(el("div", { class: "code-row label-row" }, el("span", { class: "gut" }), el("span", { class: "txt" }, m[1] + ":")));
      continue;
    }
    m = line.match(/^([> ])([* ])  ([0-9a-f]{4})  (.{8})  (.*)$/);
    if (!m) continue;
    const addr = parseInt(m[3], 16);
    const [mn, ...rest] = m[5].split(" ");
    const cls = "code-row mapped" + (m[1] === ">" ? " current" : "") + (m[2] === "*" ? " bp" : "");
    const row = el("div", { class: cls, "data-addr": addr },
      el("span", { class: "gut", title: "Point d'arrêt", onclick: () => toggleBreakpoint(addr) }, "●"),
      el("span", { class: "ln addr" }, m[3]),
      el("span", { class: "bytes" }, m[4]),
      el("span", { class: "txt" }, el("span", { class: "mn" }, mn), rest.length ? " " + rest.join(" ") : ""));
    if (m[1] === ">") current = row;
    rows.push(row);
  }
  view.replaceChildren(...rows);
  if (current) scrollToRow(view, current);
}

async function loadCodeInfo() {
  const prog = state.status && state.status.vice.prog;
  if (!prog) return null;
  const key = prog;
  if (code.infoKey === key && code.info && Date.now() - code.infoTime < 5000) return code.info;
  code.info = await api("GET", `/api/codeinfo?prog=${encodeURIComponent(prog)}`);
  code.infoKey = key;
  code.infoTime = Date.now();
  return code.info;
}

const sourceCache = new Map();
async function fetchSource(path, mtime) {
  const key = `${path}@${mtime}`;
  if (!sourceCache.has(key)) {
    const res = await fetch(`/source/${encodeURI(path)}`);
    if (!res.ok) throw new Error(`source ${path} : ${res.status}`);
    sourceCache.set(key, await res.text());
  }
  return sourceCache.get(key);
}

async function renderSource(view) {
  const info = await loadCodeInfo();
  const tabs = $("#code-files");
  if (!info || !info.files.length) {
    tabs.hidden = true;
    view.replaceChildren(el("div", { class: "muted pad" }, "Pas de source du projet pour ce programme."));
    return;
  }
  const w = code.where;
  if ($("#code-follow").checked && w && w.file && info.files.includes(w.file)) code.file = w.file;
  if (!code.file || !info.files.includes(code.file)) code.file = info.files[0];
  tabs.hidden = info.files.length < 2;
  tabs.replaceChildren(...info.files.map((f) => el("button", {
    class: "tab" + (f === code.file ? " active" : ""),
    onclick: () => { code.file = f; $("#code-follow").checked = false; refreshCode(); },
  }, f.split("/").pop())));
  const text = await fetchSource(code.file, info.mtime);
  const map = info.lines[code.file] || {};
  const rows = [];
  let current = null;
  text.replace(/\n$/, "").split("\n").forEach((src, i) => {
    const n = i + 1;
    const range = map[n];
    const isCur = w && w.file === code.file && w.line === n;
    const bp = range && execBpAt(range[0]);
    const cls = "code-row " + (range ? "mapped" : "unmapped") + (isCur ? " current" : "") + (bp ? " bp" : "");
    const parts = src.split(";");
    const txt = el("span", { class: "txt" }, parts[0], parts.length > 1 ? el("span", { class: "cm" }, ";" + parts.slice(1).join(";")) : "");
    const row = el("div", { class: cls, title: range ? `$${hex4(range[0])}-$${hex4(range[1])}` : "" },
      el("span", { class: "gut", onclick: range ? () => toggleBreakpoint(range[0]) : null }, range ? "●" : ""),
      el("span", { class: "ln num" }, String(n)), txt);
    if (isCur) current = row;
    rows.push(row);
  });
  view.replaceChildren(...rows);
  if (current) scrollToRow(view, current);
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
  refreshScreen();
  await refreshBreakpoints();
  refreshCode();
  if (mem.data) refreshMemory();
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

// --- Mémoire ------------------------------------------------------------------
const REGIONS = [
  { name: "Zero page", start: 0x0000, end: 0x00ff, color: "#e0a24a" },
  { name: "Pile", start: 0x0100, end: 0x01ff, color: "#e46a6a" },
  { name: "Système", start: 0x0200, end: 0x03ff, color: "#b07fd6" },
  { name: "Écran", start: 0x0400, end: 0x07ff, color: "#5fc48a" },
  { name: "Programme / RAM", start: 0x0800, end: 0x9fff, color: "#4d6fd6" },
  { name: "BASIC ROM", start: 0xa000, end: 0xbfff, color: "#8a8a8a" },
  { name: "RAM $C000", start: 0xc000, end: 0xcfff, color: "#4d6fd6" },
  { name: "VIC-II", start: 0xd000, end: 0xd3ff, color: "#3fb6c6" },
  { name: "SID", start: 0xd400, end: 0xd7ff, color: "#d6c13f" },
  { name: "Color RAM", start: 0xd800, end: 0xdbff, color: "#d67fb0" },
  { name: "CIA 1", start: 0xdc00, end: 0xdcff, color: "#7fd6c8" },
  { name: "CIA 2", start: 0xdd00, end: 0xddff, color: "#7fb8d6" },
  { name: "E/S extension", start: 0xde00, end: 0xdfff, color: "#999999" },
  { name: "KERNAL ROM", start: 0xe000, end: 0xffff, color: "#8a8a8a" },
];
const regionOf = (a) => REGIONS.find((r) => r.start <= a && a <= r.end);

// Couleur d'un octet sur la carte : 0 très sombre, puis dégradé violet ->
// bleu -> vert -> jaune ; octet modifié depuis la lecture précédente : blanc.
const MAP_COLORS = (() => {
  const stops = [[45, 25, 110], [33, 110, 160], [40, 170, 120], [150, 210, 70], [253, 231, 37]];
  const out = [[11, 10, 18]];
  for (let v = 1; v < 256; v++) {
    const t = ((v - 1) / 254) * (stops.length - 1);
    const i = Math.min(Math.floor(t), stops.length - 2);
    const f = t - i;
    out.push(stops[i].map((c, k) => Math.round(c + (stops[i + 1][k] - c) * f)));
  }
  return out;
})();

const mem = { data: null, prev: null, start: 0x0400, sel: null, dragging: false, busy: false, segments: [] };

function decodeByte(v, mode) {
  if (mode === "ascii") return v >= 32 && v < 127 ? String.fromCharCode(v) : ".";
  if (mode === "petscii") {
    if (v >= 0x20 && v <= 0x5a) return String.fromCharCode(v);
    return { 0x5b: "[", 0x5c: "£", 0x5d: "]", 0x5e: "↑", 0x5f: "←" }[v] || ".";
  }
  const c = v & 0x7f; // codes écran (bit 7 = vidéo inverse)
  if (c === 0) return "@";
  if (c <= 26) return String.fromCharCode(64 + c);
  if (c <= 31) return "[£]↑←"[c - 27];
  if (c <= 63) return String.fromCharCode(c);
  return ".";
}

async function refreshMemory() {
  if (!state.monitorAvailable || mem.busy) return;
  mem.busy = true;
  try {
    const res = await fetch(`/api/ram?bank=${encodeURIComponent($("#mem-bank").value)}`);
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).error || msg; } catch { /* binaire */ }
      throw new Error(msg);
    }
    const data = new Uint8Array(await res.arrayBuffer());
    mem.prev = mem.data && mem.data.length === data.length ? mem.data : null;
    mem.data = data;
    $("#mem-hint").textContent = `lu à ${new Date().toLocaleTimeString("fr-FR")}`;
    drawMap();
    renderHex();
  } catch (e) {
    $("#mem-hint").textContent = e.message;
  } finally {
    mem.busy = false;
  }
}

function focusLen() { return parseInt($("#mem-rows").value, 10) * 16; }

function drawMap() {
  const cv = $("#mem-map");
  const ctx = cv.getContext("2d");
  const img = ctx.createImageData(256, 256);
  const d = mem.data;
  if (d) {
    for (let i = 0; i < 65536; i++) {
      const changed = mem.prev && mem.prev[i] !== d[i];
      const c = changed ? [255, 255, 255] : MAP_COLORS[d[i]];
      img.data[i * 4] = c[0];
      img.data[i * 4 + 1] = c[1];
      img.data[i * 4 + 2] = c[2];
      img.data[i * 4 + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  // Fenêtre de focus et sélection.
  const outline = (a, b, style, fill) => {
    for (let row = a >> 8; row <= b >> 8; row++) {
      const x0 = row === a >> 8 ? a & 0xff : 0;
      const x1 = row === b >> 8 ? b & 0xff : 255;
      if (fill) { ctx.fillStyle = style; ctx.fillRect(x0, row, x1 - x0 + 1, 1); }
    }
    if (!fill) {
      ctx.strokeStyle = style;
      ctx.lineWidth = 1;
      ctx.strokeRect(-0.5, (a >> 8) - 0.5, 257, (b >> 8) - (a >> 8) + 2);
    }
  };
  outline(mem.start, Math.min(0xffff, mem.start + focusLen() - 1), "rgba(255,170,60,.95)", false);
  if (mem.sel) {
    const [a, b] = selRange();
    outline(a, b, "rgba(143,131,230,.75)", true);
  }
}

function selRange() {
  return mem.sel ? [Math.min(mem.sel.a, mem.sel.b), Math.max(mem.sel.a, mem.sel.b)] : null;
}

function renderHex() {
  const view = $("#hex-view");
  const d = mem.data;
  if (!d) { view.replaceChildren(el("div", { class: "muted pad" }, "—")); return; }
  const mode = $("#mem-decode").value;
  const sel = selRange();
  const rows = [];
  for (let r = 0; r < focusLen() / 16; r++) {
    const base = mem.start + r * 16;
    if (base > 0xffff) break;
    const hx = el("span", { class: "hx" });
    const tx = el("span", { class: "tx" });
    for (let c = 0; c < 16; c++) {
      const a = base + c;
      const v = d[a];
      let cls = v === 0 ? "zero" : "";
      if (mem.prev && mem.prev[a] !== v) cls += " chg";
      if (sel && a >= sel[0] && a <= sel[1]) cls += " sel";
      hx.append(el("span", { class: cls, "data-a": a }, hex2(v)));
      tx.append(el("span", { class: cls, "data-a": a }, decodeByte(v, mode)));
    }
    rows.push(el("div", { class: "hex-row" }, el("span", { class: "ad" }, hex4(base)), hx, tx));
  }
  view.replaceChildren(...rows);
}

function gotoMem(addr, select) {
  addr = Math.max(0, Math.min(0xffff, addr));
  mem.start = Math.min(addr & 0xfff0, 0x10000 - focusLen());
  if (select) mem.sel = { a: addr, b: addr };
  drawMap();
  renderHex();
  if (select) renderSelection();
}

async function resolveAddr(text) {
  const t = text.trim();
  if (/^\$[0-9a-f]+$/i.test(t)) return parseInt(t.slice(1), 16);
  if (/^0x[0-9a-f]+$/i.test(t)) return parseInt(t.slice(2), 16);
  if (/^\d+$/.test(t)) return parseInt(t, 10);
  const r = await dbg("label", [t]);
  const lines = r.stdout.trim().split("\n").filter(Boolean);
  const exact = lines.find((l) => l.split(" = ")[0].toLowerCase() === t.replace(/^\./, "").toLowerCase());
  const line = exact || lines[0];
  if (!line) throw new Error(`label inconnu : ${t}`);
  return parseInt(line.split("$")[1], 16);
}

async function renderSelection() {
  const box = $("#mem-selection");
  const sel = selRange();
  if (!sel || !mem.data) { box.hidden = true; return; }
  box.hidden = false;
  const [a, b] = sel;
  const bytes = Array.from(mem.data.slice(a, b + 1));
  const n = bytes.length;
  const MAX = 64;
  const cut = (arr) => arr.slice(0, MAX);
  const more = n > MAX ? " …" : "";
  const mode = $("#mem-decode").value;
  const region = regionOf(a);
  $("#sel-range").textContent = `$${hex4(a)}${n > 1 ? `–$${hex4(b)}` : ""} · ${n} octet${n > 1 ? "s" : ""}` +
    (region ? ` · ${region.name}` : "");
  const words = [];
  for (let i = 0; i + 1 < Math.min(n, MAX); i += 2) words.push("$" + hex4(bytes[i] | (bytes[i + 1] << 8)));
  const items = [
    ["Hexa", cut(bytes).map(hex2).join(" ") + more],
    ["Décimal", cut(bytes).join(" ") + more],
    ["Texte", "« " + cut(bytes).map((v) => decodeByte(v, mode)).join("") + " »" + more],
  ];
  if (n >= 2) items.push(["Mots 16 bits", words.join(" ") + more]);
  if (n === 1) items.push(["Binaire", bytes[0].toString(2).padStart(8, "0")]);
  if (n === 2) items.push(["Pointeur", `$${hex4(bytes[0] | (bytes[1] << 8))} (${bytes[0] | (bytes[1] << 8)})`]);
  const dl = $("#sel-values");
  dl.replaceChildren(...items.flatMap(([k, v]) => [el("dt", {}, k), el("dd", {}, v)]));
  // Label exact au début de la sélection (s'il existe).
  try {
    const r = await dbg("label", [String(a)]);
    if (r.rc === 0 && r.stdout.trim()) {
      dl.prepend(el("dt", {}, "Label"), el("dd", {}, r.stdout.trim().split("\n").map((l) => l.split(" = ")[0]).join(", ")));
    }
  } catch { /* sans label */ }
}

function wireMemory() {
  const regionSel = $("#mem-region");
  const fillRegions = () => {
    const opts = [el("option", { value: "" }, "—")];
    for (const r of REGIONS) opts.push(el("option", { value: r.start }, `${r.name} ($${hex4(r.start)})`));
    for (const s of mem.segments) opts.push(el("option", { value: s.start }, `${s.prog} ${s.name} ($${hex4(s.start)})`));
    regionSel.replaceChildren(...opts);
    const legend = $("#map-legend");
    legend.replaceChildren(...REGIONS.map((r) => el("button", { onclick: () => gotoMem(r.start, false), title: `$${hex4(r.start)}-$${hex4(r.end)}` },
      el("i", { style: `background:${r.color}` }), r.name)),
      ...mem.segments.map((s) => el("button", { onclick: () => { mem.sel = { a: s.start, b: s.end }; gotoMem(s.start, false); renderSelection(); }, title: `$${hex4(s.start)}-$${hex4(s.end)}` },
        el("i", { style: "background:var(--accent)" }), `${s.prog} ${s.name}`)));
  };
  wireMemory.fillRegions = fillRegions;
  fillRegions();
  regionSel.addEventListener("change", () => { if (regionSel.value !== "") gotoMem(+regionSel.value, false); });
  $("#mem-refresh").addEventListener("click", refreshMemory);
  $("#mem-bank").addEventListener("change", () => { mem.prev = null; mem.data = null; refreshMemory(); });
  $("#mem-decode").addEventListener("change", () => { renderHex(); renderSelection(); });
  $("#mem-rows").addEventListener("change", () => gotoMem(mem.start, false));
  for (const b of $$("[data-mem-step]")) {
    b.addEventListener("click", () => gotoMem(Math.max(0, mem.start + parseInt(b.dataset.memStep, 10)), false));
  }
  $("#mem-goto").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      gotoMem(await resolveAddr($("#mem-addr").value), true);
    } catch (err) {
      notice(err.message);
    }
  });

  const cv = $("#mem-map");
  const addrAt = (e) => {
    const r = cv.getBoundingClientRect();
    const x = Math.min(255, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * 256)));
    const y = Math.min(255, Math.max(0, Math.floor(((e.clientY - r.top) / r.height) * 256)));
    return y * 256 + x;
  };
  cv.addEventListener("mousemove", (e) => {
    const a = addrAt(e);
    const v = mem.data ? mem.data[a] : null;
    const reg = regionOf(a);
    $("#map-info").textContent = `$${hex4(a)}` + (v != null ? ` = $${hex2(v)} (${v})` : "") + (reg ? ` · ${reg.name}` : "");
  });
  cv.addEventListener("click", (e) => gotoMem(addrAt(e), true));

  const view = $("#hex-view");
  const cellAddr = (e) => {
    const s = e.target.closest("[data-a]");
    return s ? parseInt(s.dataset.a, 10) : null;
  };
  view.addEventListener("mousedown", (e) => {
    const a = cellAddr(e);
    if (a == null) return;
    mem.sel = { a, b: a };
    mem.dragging = true;
    renderHex();
    e.preventDefault();
  });
  view.addEventListener("mouseover", (e) => {
    if (!mem.dragging) return;
    const a = cellAddr(e);
    if (a != null && a !== mem.sel.b) { mem.sel.b = a; renderHex(); }
  });
  document.addEventListener("mouseup", () => {
    if (!mem.dragging) return;
    mem.dragging = false;
    drawMap();
    renderSelection();
  });
  view.addEventListener("dblclick", async (e) => {
    const a = cellAddr(e);
    if (a == null || !mem.data) return;
    const v = prompt(`Nouvelle valeur pour $${hex4(a)} (actuelle $${hex2(mem.data[a])}) :`, "$" + hex2(mem.data[a]));
    if (v == null || !v.trim()) return;
    await monitorAction("poke", ["$" + hex4(a), v.trim()], null);
    await refreshMemory();
  });
  view.addEventListener("wheel", (e) => {
    if (!mem.data) return;
    e.preventDefault();
    gotoMem(Math.max(0, mem.start + (e.deltaY > 0 ? 16 : -16) * 2), false);
  }, { passive: false });

  const selText = () => {
    const s = selRange();
    return s ? Array.from(mem.data.slice(s[0], s[1] + 1)) : [];
  };
  const copy = async (text) => {
    try { await navigator.clipboard.writeText(text); notice("Copié dans le presse-papiers.", "info"); }
    catch { notice("Copie impossible (presse-papiers indisponible)."); }
  };
  $("#sel-copy-hex").addEventListener("click", () => copy(selText().map(hex2).join(" ")));
  $("#sel-copy-text").addEventListener("click", () => copy(selText().map((v) => decodeByte(v, $("#mem-decode").value)).join("")));
  $("#sel-watch").addEventListener("click", () => {
    const s = selRange();
    if (s) monitorAction("watch", ["$" + hex4(s[0]), "$" + hex4(s[1])], null);
  });
  $("#sel-disasm").addEventListener("click", () => {
    const s = selRange();
    if (!s) return;
    code.addr = "$" + hex4(s[0]);
    $("#code-follow").checked = false;
    setCodeMode("disasm");
    $("#card-monitor").scrollIntoView({ behavior: "smooth", block: "start" });
  });
}

// Point d'entrée du programme : début du segment STARTUP (C) ou CODE (asm),
// soit $080D pour les programmes avec en-tête BASIC « SYS 2061 ».
async function entryPoint() {
  const info = await loadCodeInfo().catch(() => null);
  const segs = info ? info.segments.filter((s) => (s.name === "STARTUP" || s.name === "CODE") && s.start >= 0x0801) : [];
  return segs.length ? Math.min(...segs.map((s) => s.start)) : 0x080d;
}

async function restartStepping() {
  if (!state.monitorAvailable) { notice("Moniteur indisponible."); return; }
  const btn = $("#restart-step");
  btn.disabled = true;
  try {
    const entry = await entryPoint();
    const regs = await dbg("regs");
    const pc = parseInt((regs.stdout.match(/PC=([0-9a-f]{4})/) || [])[1] || "0", 16);
    if (pc >= 0xa000) {
      // Revenu au BASIC (PC en ROM) : RUN relance proprement le programme.
      const bp = await dbg("break", ["$" + hex4(entry)]);
      const num = (bp.stdout.match(/checkpoint (\d+)/) || [])[1];
      await dbg("type", ["run\\n"]);
      const w = await dbg("wait", ["5"]);
      if (num) await dbg("delete", [num]);
      if (w.rc !== 0) throw new Error("le programme ne s'est pas arrêté sur son point d'entrée : " + dbgText(w));
    } else {
      // Programme en cours (boucle) : on replace le PC au début.
      const r = await dbg("jump", ["$" + hex4(entry)]);
      if (r.rc !== 0) throw new Error(dbgText(r));
    }
    $("#code-follow").checked = true;
    code.addr = null;
  } catch (e) {
    notice(e.message);
  } finally {
    btn.disabled = false;
  }
  await refreshStatus();
  refreshRegs();
  refreshScreen();
  await refreshBreakpoints();
  refreshCode();
}

async function loadSegments() {
  try {
    const info = await loadCodeInfo();
    mem.segments = info ? info.segments.filter((s) => s.end >= s.start && s.name !== "LOADADDR" && s.name !== "NULL")
      .map((s) => ({ ...s, prog: info.prog })) : [];
  } catch {
    mem.segments = [];
  }
  if (wireMemory.fillRegions) wireMemory.fillRegions();
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
          title: "Utiliser cette adresse (points d'arrêt, code, mémoire)",
          onclick: () => { for (const id of ["#bp-addr", "#code-addr", "#mem-addr"]) $(id).value = name; },
        }, `${name} ${addr}`));
      }
    } catch (err) {
      notice(err.message);
    }
  });
  for (const t of $$(".tab[data-code]")) t.addEventListener("click", () => setCodeMode(t.dataset.code));
  $("#code-follow").addEventListener("change", () => {
    if ($("#code-follow").checked) code.addr = null;
    refreshCode();
  });
  $("#code-goto").addEventListener("submit", (e) => {
    e.preventDefault();
    const a = $("#code-addr").value.trim();
    if (!a) return;
    code.addr = a;
    $("#code-follow").checked = false;
    setCodeMode("disasm");
  });
  $("#code-refresh").addEventListener("click", refreshCode);
  $("#restart-step").addEventListener("click", restartStepping);
  $("#type-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const t = $("#type-text").value;
    if (!t && !$("#type-return").checked) return;
    monitorAction("type", [t + ($("#type-return").checked ? "\\n" : "")]);
    $("#type-text").value = "";
  });
  wireMemory();
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
// Une erreur JS ne doit pas passer inaperçue : on l'affiche dans la page.
window.addEventListener("error", (e) => notice(`Erreur dans la page : ${e.message}`));
window.addEventListener("unhandledrejection", (e) => notice(`Erreur dans la page : ${e.reason && e.reason.message || e.reason}`));

// Liens directs : #mem=0400-040f (zone mémoire sélectionnée), #code=source.
function parseDeepLink() {
  const p = new URLSearchParams(location.hash.slice(1));
  const link = {};
  const m = (p.get("mem") || "").match(/^\$?([0-9a-f]{1,4})(?:-\$?([0-9a-f]{1,4}))?$/i);
  if (m) link.mem = [parseInt(m[1], 16), parseInt(m[2] || m[1], 16)];
  if (["source", "disasm"].includes(p.get("code"))) link.code = p.get("code");
  return link;
}

async function applyDeepLink() {
  const link = state.deepLink;
  if (!link || !state.monitorAvailable) return;
  state.deepLink = null;
  if (link.code) setCodeMode(link.code);
  if (link.mem) {
    await refreshMemory();
    gotoMem(link.mem[0], false);
    mem.sel = { a: link.mem[0], b: link.mem[1] };
    drawMap();
    renderHex();
    renderSelection();
    $("#card-memory").scrollIntoView({ block: "start" });
  }
}

async function main() {
  state.deepLink = parseDeepLink();
  wire();
  await loadMeta();
  await Promise.all([refreshStatus(), refreshPrograms(), refreshSync()]);
  setScreenMode("image");
  refreshLog();
  setInterval(refreshStatus, 2000);
  setInterval(refreshPrograms, 15000);
  setInterval(() => {
    if ($("#screen-auto").checked && state.monitorAvailable && !document.hidden) refreshScreen();
    if ($("#mem-auto").checked && state.monitorAvailable && !document.hidden) refreshMemory();
  }, 1000);
  drawMap();
  // Dernière tâche connue (rechargement de page pendant une tâche).
  try {
    const { jobs } = await api("GET", "/api/jobs");
    if (jobs.length && !state.job) followJob(jobs[0]);
  } catch { /* rien */ }
}

main();
