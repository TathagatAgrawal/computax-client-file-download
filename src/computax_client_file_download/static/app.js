/* CompuTax file downloader UI. Talks to the local server's /api endpoints. */
"use strict";

const $ = (id) => document.getElementById(id);

// The session token arrives once in the URL; keep it for reloads, then hide it.
const TOKEN = (() => {
  const t = new URLSearchParams(location.search).get("t");
  if (t) {
    sessionStorage.setItem("token", t);
    history.replaceState(null, "", "/");
  }
  return sessionStorage.getItem("token") || "";
})();

const state = {
  rootSet: false,
  root: "",
  rangeFor: null, // client ID the range selects were last filled for
  clients: [],
  client: null, // selected client summary
  detail: null, // per-year availability for the selected client
  years: new Set(),
  activeIndex: -1,
  results: [],
  lastReport: null,
  stopped: false,
};

async function api(method, path, body) {
  let res;
  try {
    res = await fetch(path, {
      method,
      headers: { "X-Session-Token": TOKEN, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    showStopped();
    throw new Error("The app is not running.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `Request failed (${res.status}).`);
  return data;
}

function showStopped() {
  state.stopped = true;
  $("stopped").hidden = false;
  for (const id of ["setup", "form", "results"]) $(id).hidden = true;
}

function showSection(name) {
  if (state.stopped) return;
  for (const id of ["setup", "form", "results"]) $(id).hidden = id !== name;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child != null) node.append(child);
  }
  return node;
}

// Text with the matched characters wrapped in <mark>, built without innerHTML.
function highlighted(text, positions) {
  const frag = document.createDocumentFragment();
  const marks = new Set(positions || []);
  let run = "";
  let runMarked = false;
  const flush = () => {
    if (run) frag.append(runMarked ? el("mark", {}, run) : document.createTextNode(run));
    run = "";
  };
  [...text].forEach((ch, i) => {
    const m = marks.has(i);
    if (m !== runMarked) {
      flush();
      runMarked = m;
    }
    run += ch;
  });
  flush();
  return frag;
}

function yearSpan(years) {
  if (!years.length) return "no years";
  const first = years[0];
  const last = years[years.length - 1];
  const span = first === last ? `${first}` : `${first}–${last}`;
  return `${span} · ${years.length} year${years.length === 1 ? "" : "s"}`;
}

function clientLabel(c) {
  return c.name ? `${c.id} — ${c.name}` : c.id;
}

/* ---------- Native folder dialog ---------- */

async function pickFolder(purpose, input, waitEl, button) {
  button.disabled = true;
  waitEl.hidden = false;
  try {
    const { path } = await api("POST", "/api/pick-folder", { purpose, initial: input.value.trim() });
    if (path) {
      input.value = path;
      input.dispatchEvent(new Event("input"));
    }
  } catch (err) {
    alert(err.message);
  } finally {
    button.disabled = false;
    waitEl.hidden = true;
  }
}

document.addEventListener("click", (e) => {
  if (e.target.matches("[data-cancel-dialog]")) {
    e.preventDefault();
    api("POST", "/api/pick-folder/cancel").catch(() => {});
  }
});

/* ---------- Setup ---------- */

let validateTimer = null;
let validateSeq = 0;

async function validateRoot() {
  const seq = ++validateSeq;
  const root = $("root-input").value;
  const msg = $("root-msg");
  $("root-continue").disabled = true;
  if (!root.trim()) {
    msg.textContent = "";
    return;
  }
  try {
    const check = await api("POST", "/api/validate-root", { root });
    if (seq !== validateSeq) return;
    msg.textContent = (check.ok ? "✓ " : "") + check.message;
    msg.className = "msg " + (check.ok ? "ok" : "error");
    $("root-continue").disabled = !check.ok;
  } catch (err) {
    msg.textContent = err.message;
    msg.className = "msg error";
  }
}

function openSetup(prefill) {
  $("root-input").value = prefill || "";
  $("root-msg").textContent = "";
  $("root-cancel").hidden = !state.rootSet;
  showSection("setup");
  if (prefill) validateRoot();
  $("root-input").focus();
}

$("root-input").addEventListener("input", () => {
  clearTimeout(validateTimer);
  validateTimer = setTimeout(validateRoot, 300);
});
$("root-browse").addEventListener("click", () => pickFolder("root", $("root-input"), $("root-wait"), $("root-browse")));
$("root-cancel").addEventListener("click", () => showSection("form"));
$("root-continue").addEventListener("click", async () => {
  try {
    const s = await api("PUT", "/api/settings", { root: $("root-input").value });
    setSource(s.root);
    state.rootSet = true;
    clearClient();
    await loadClients();
    showSection("form");
  } catch (err) {
    $("root-msg").textContent = err.message;
    $("root-msg").className = "msg error";
  }
});

/* ---------- Client list ---------- */

function setSource(root) {
  state.root = root || "";
  const parts = state.root.split(/[\\/]/).filter(Boolean);
  $("source-path").textContent = parts.length > 2 ? `…/${parts.slice(-2).join("/")}` : state.root;
  $("source-path").title = state.root;
}

async function loadClients() {
  const data = await api("GET", "/api/clients");
  applyClients(data);
}

let namesPoll = null;

function applyClients(data) {
  state.clients = data.clients;
  const named = data.clients.filter((c) => c.name).length;
  $("client-hint").textContent = data.names_ready
    ? `${data.clients.length} clients · search by ID or name`
    : `${data.clients.length} clients · loading names…`;
  if (!data.names_ready) {
    clearTimeout(namesPoll);
    namesPoll = setTimeout(() => loadClients().catch(() => {}), 1000);
  } else if (named === 0) {
    $("client-hint").textContent = `${data.clients.length} clients · search by ID`;
  }
  if (state.client) {
    const fresh = state.clients.find((c) => c.id.toUpperCase() === state.client.id.toUpperCase());
    if (fresh) {
      state.client = fresh;
      if (document.activeElement !== $("client-input")) $("client-input").value = clientLabel(fresh);
    } else {
      clearClient();
    }
  }
  if (!$("client-list").hidden) renderList();
}

function renderList() {
  const list = $("client-list");
  const query = $("client-input").value;
  const showAll = state.client && query === clientLabel(state.client);
  state.results = Fuzzy.search(state.clients, showAll ? "" : query);
  list.replaceChildren();
  if (!state.results.length) {
    list.append(el("li", { class: "empty" }, "No matching client"));
  }
  state.results.forEach((r, i) => {
    const c = r.client;
    const idNode = el("span", { class: "cid" }, highlighted(c.id, r.field === "id" ? r.positions : []));
    const nameNode = c.name
      ? el("span", { class: "cname" }, highlighted(c.name, r.field === "name" ? r.positions : []))
      : el("span", { class: "cname missing" }, "(name not found)");
    const alias = r.field === "alias" ? el("span", { class: "alias" }, "formerly ", highlighted(r.alias, r.positions)) : null;
    const li = el(
      "li",
      { role: "option", id: `opt-${i}` },
      el("span", {}, idNode, nameNode, alias),
      el("span", { class: "meta" }, yearSpan(c.years)),
    );
    li.addEventListener("mousedown", (e) => e.preventDefault());
    li.addEventListener("click", () => selectClient(c));
    list.append(li);
  });
  state.activeIndex = state.results.length ? 0 : -1;
  if (showAll) state.activeIndex = state.results.findIndex((r) => r.client === state.client);
  highlightActive();
  list.hidden = false;
  $("client-input").setAttribute("aria-expanded", "true");
}

function highlightActive() {
  const items = $("client-list").querySelectorAll("li[role=option]");
  items.forEach((li, i) => li.classList.toggle("active", i === state.activeIndex));
  const active = items[state.activeIndex];
  if (active) {
    active.scrollIntoView({ block: "nearest" });
    $("client-input").setAttribute("aria-activedescendant", active.id);
  }
}

function closeList() {
  $("client-list").hidden = true;
  $("client-input").setAttribute("aria-expanded", "false");
}

$("client-input").addEventListener("input", renderList);
$("client-input").addEventListener("focus", (e) => {
  e.target.select();
  renderList();
});
$("client-input").addEventListener("blur", () => {
  closeList();
  if (state.client) $("client-input").value = clientLabel(state.client);
});
$("client-input").addEventListener("keydown", (e) => {
  const listOpen = !$("client-list").hidden;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (!listOpen) return renderList();
    const n = state.results.length;
    if (!n) return;
    state.activeIndex = (state.activeIndex + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
    highlightActive();
  } else if (e.key === "Enter" && listOpen) {
    e.preventDefault();
    const r = state.results[state.activeIndex];
    if (r) selectClient(r.client);
  } else if (e.key === "Escape") {
    closeList();
  }
});

async function selectClient(c) {
  state.client = c;
  state.years = new Set();
  $("client-input").value = clientLabel(c);
  closeList();
  $("client-input").blur();
  state.detail = null;
  renderYears();
  try {
    const detail = await api("GET", `/api/clients/${encodeURIComponent(c.id)}`);
    if (state.client === c) {
      state.detail = detail;
      renderYears();
    }
  } catch (err) {
    $("form-error").textContent = err.message;
  }
}

function clearClient() {
  state.client = null;
  state.detail = null;
  state.years = new Set();
  state.rangeFor = null;
  $("client-input").value = "";
  renderYears();
}

/* ---------- Years ---------- */

function yearAvailable(year) {
  if (!state.detail) return true;
  const y = state.detail.years[String(year)];
  return Boolean(y && (y.itrv.length || y.computation.length));
}

function yearTooltip(year) {
  if (!state.detail) return "";
  const y = state.detail.years[String(year)];
  if (!y) return "";
  const files = [...y.itrv, ...y.computation];
  const lines = files.length ? files : ["No ITRV or Computation file found"];
  return [...lines, ...y.warnings].join("\n");
}

function renderYears() {
  const field = $("years-field");
  const chips = $("year-chips");
  chips.replaceChildren();
  if (!state.client) {
    field.hidden = true;
    updateSummary();
    return;
  }
  field.hidden = false;
  const years = state.client.years;
  for (const year of years) {
    const classes = ["chip"];
    if (state.years.has(year)) classes.push("on");
    if (!yearAvailable(year)) classes.push("unavailable");
    const chip = el("button", { type: "button", class: classes.join(" "), title: yearTooltip(year) }, String(year));
    chip.setAttribute("aria-pressed", String(state.years.has(year)));
    chip.addEventListener("click", () => {
      if (state.years.has(year)) state.years.delete(year);
      else state.years.add(year);
      renderYears();
    });
    chips.append(chip);
  }
  if (state.rangeFor !== state.client.id) {
    state.rangeFor = state.client.id;
    for (const id of ["range-from", "range-to"]) {
      $(id).replaceChildren(...years.map((y) => el("option", { value: String(y) }, String(y))));
    }
    $("range-from").value = String(years[0]);
    $("range-to").value = String(years[years.length - 1]);
  }
  updateSummary();
}

$("range-add").addEventListener("click", () => {
  let a = Number($("range-from").value);
  let b = Number($("range-to").value);
  if (a > b) [a, b] = [b, a];
  for (const y of state.client.years) if (y >= a && y <= b) state.years.add(y);
  renderYears();
});
$("years-all").addEventListener("click", () => {
  state.years = new Set(state.client.years);
  renderYears();
});
$("years-none").addEventListener("click", () => {
  state.years = new Set();
  renderYears();
});

/* ---------- Destination and copy ---------- */

$("dest-input").addEventListener("input", updateSummary);
$("dest-browse").addEventListener("click", () => pickFolder("dest", $("dest-input"), $("dest-wait"), $("dest-browse")));

function joinPath(dir, name) {
  const sep = dir.includes("\\") && !dir.includes("/") ? "\\" : "/";
  return dir.replace(/[\\/]+$/, "") + sep + name;
}

function updateSummary() {
  $("form-error").textContent = "";
  const dest = $("dest-input").value.trim();
  const n = state.years.size;
  let text = "";
  if (!state.client) text = "Choose a client.";
  else if (!n) text = "Choose at least one year.";
  else if (!dest) text = "Choose where to save the files.";
  else text = `${n} year${n === 1 ? "" : "s"} selected → files go into ${joinPath(dest, state.client.id)}`;
  $("copy-summary").textContent = text;
  $("copy-btn").disabled = !(state.client && n && dest);
}

$("copy-btn").addEventListener("click", async () => {
  const btn = $("copy-btn");
  btn.disabled = true;
  btn.textContent = "Copying…";
  try {
    const report = await api("POST", "/api/copy", {
      id: state.client.id,
      years: [...state.years].sort((a, b) => a - b),
      dest: $("dest-input").value.trim(),
    });
    renderResults(report);
  } catch (err) {
    $("form-error").textContent = err.message;
  } finally {
    btn.textContent = "Copy files";
    updateSummary();
  }
});

/* ---------- Results ---------- */

const STATUS_TEXT = {
  copied: "✓",
  exists: "= already there, left unchanged",
  blocked: "⚠ not saved (folder in the way)",
  error: "✗ failed",
};

function fileCell(items) {
  const td = el("td");
  if (!items.length) {
    td.append(el("div", { class: "st-missing" }, "✗ not found"));
    return td;
  }
  for (const item of items) {
    const status = STATUS_TEXT[item.status];
    const text = item.status === "copied" ? `${status} ${item.name}` : `${item.name} ${status}`;
    td.append(el("div", { class: `st-${item.status}` }, item.error ? `${text}: ${item.error}` : text));
  }
  return td;
}

function renderResults(report) {
  state.lastReport = report;
  const t = report.totals;
  const written = t.copied;
  const missing = report.years.filter((y) => !y.itrv.length || !y.computation.length).length;
  const who = report.name ? `${report.id} — ${report.name}` : report.id;
  const banner = $("results-banner");
  const extras = [];
  if (t.exists) extras.push(`${t.exists} already there, left unchanged`);
  if (t.blocked) extras.push(`${t.blocked} not saved`);
  if (t.error) extras.push(`${t.error} failed`);
  if (missing) extras.push(`${missing} year${missing === 1 ? "" : "s"} with missing files`);
  banner.textContent =
    `${written && !missing && !t.error && !t.blocked ? "✓" : "⚠"} Copied ${written} file${written === 1 ? "" : "s"} for ${who} to ${report.dest_root}` +
    (extras.length ? ` (${extras.join(", ")})` : "");
  banner.className = "banner" + (t.error ? " bad" : missing || t.blocked || !written ? " warn" : "");
  const body = $("results-body");
  body.replaceChildren();
  for (const y of report.years) {
    body.append(el("tr", {}, el("td", {}, String(y.year)), fileCell(y.itrv), fileCell(y.computation)));
    for (const w of y.warnings) {
      body.append(el("tr", {}, el("td"), el("td", { colspan: "2", class: "st-warning" }, `⚠ ${w}`)));
    }
  }
  $("open-folder").disabled = !written && !t.exists;
  showSection("results");
}

$("open-folder").addEventListener("click", () => {
  api("POST", "/api/open", { path: state.lastReport.dest_root }).catch((err) => alert(err.message));
});
$("start-over").addEventListener("click", () => {
  clearClient();
  showSection("form");
  $("client-input").focus();
});

/* ---------- Header actions ---------- */

$("change-root").addEventListener("click", () => openSetup(state.root));
$("rescan").addEventListener("click", async () => {
  const btn = $("rescan");
  btn.textContent = "rescanning…";
  try {
    applyClients(await api("POST", "/api/rescan"));
    if (state.client) await selectClientKeepingYears(state.client);
  } catch (err) {
    $("form-error").textContent = err.message;
  } finally {
    btn.textContent = "rescan";
  }
});
$("quit").addEventListener("click", async () => {
  await api("POST", "/api/quit").catch(() => {});
  showStopped();
  $("stopped").textContent = "The app has stopped. You can close this tab.";
});

async function selectClientKeepingYears(c) {
  const keep = state.years;
  await selectClient(c);
  state.years = new Set([...keep].filter((y) => c.years.includes(y)));
  renderYears();
}

/* ---------- Heartbeat and startup ---------- */

function heartbeat() {
  if (!state.stopped) api("POST", "/api/heartbeat").catch(() => {});
}
setInterval(heartbeat, 15000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") heartbeat();
});

(async function start() {
  try {
    const s = await api("GET", "/api/settings");
    heartbeat();
    $("dest-input").value = s.default_dest;
    if (s.root_valid) {
      state.rootSet = true;
      setSource(s.root);
      await loadClients();
      showSection("form");
      updateSummary();
    } else {
      openSetup(s.root_hint);
    }
  } catch (err) {
    if (!state.stopped) {
      $("stopped").hidden = false;
      $("stopped").textContent = err.message;
    }
  }
})();
