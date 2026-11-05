// Renders the server's `state` and posts the person's actions. No rules live here: the server
// validates labels, picks the next item and writes the file.
let passId = ""; // the pass this page walks, from #/pass/<id>
const passPath = () => "/api/pass/" + encodeURIComponent(passId);
const app = document.getElementById("app");
const head = document.getElementById("head");
const statusEl = document.getElementById("status");
let state = null;
let shown = null; // id of the item the selection and the note belong to
let selected = [];
// shortcut: the draft lives only until the row changes (Skip or Back drops it), keep drafts per row if people ask.
let note = ""; // the draft note for the shown item; survives a re-render
let saved = null; // {id, labels} of the last save, for the status line
let busy = false; // a request is in flight
let error = "";

const FOCUS =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 " +
  "dark:focus-visible:outline-blue-400";
const BTN =
  "min-h-11 rounded-lg border border-zinc-300 bg-white px-4 py-2 font-medium text-zinc-900 " +
  "hover:bg-zinc-100 disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 " +
  "dark:hover:bg-zinc-800 " +
  FOCUS;
const PRIMARY =
  "min-h-11 rounded-lg border border-zinc-900 bg-zinc-900 px-4 py-2 font-semibold text-white " +
  "hover:bg-zinc-700 disabled:opacity-60 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900 " +
  "dark:hover:bg-zinc-300 " +
  FOCUS;
const OPTION =
  "flex min-h-14 w-full cursor-pointer items-center gap-3 rounded-lg border-2 p-2 text-left " + FOCUS;
const OPTION_ON = " border-blue-700 bg-blue-50 dark:border-blue-400 dark:bg-blue-950";
const OPTION_OFF = " border-zinc-300 bg-white hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800";
const KEY =
  "flex size-7 shrink-0 items-center justify-center rounded-md border border-zinc-300 bg-zinc-100 " +
  "font-mono text-sm dark:border-zinc-600 dark:bg-zinc-800";
const CARD =
  "rounded-lg border border-zinc-300 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900";
const MUTED = "text-zinc-600 dark:text-zinc-400";

function el(tag, cls, text, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  return e;
}

// `onOk` runs after a successful call and before the re-render.
async function call(method, path, body, onOk) {
  if (busy) return false; // a held-down or double-clicked key must not act twice
  busy = true;
  let ok = false;
  try {
    const r = await fetch(path, {
      method,
      headers: { "X-Goldlabel": "1", "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) {
      error = data.error || "request failed (" + r.status + ")";
    } else {
      error = "";
      state = data;
      ok = true;
      if (onOk) onOk();
    }
  } catch (e) {
    error = "Cannot reach the labelling server. Has it been stopped?";
  }
  busy = false;
  render();
  return ok;
}

const load = () => call("GET", passPath());
const back = () => call("POST", passPath() + "/back");
const skip = () => call("POST", passPath() + "/skip");
const save = () => {
  if (!selected.length) return;
  const id = state.item.id;
  const labels = selected;
  return call("POST", "/api/label", { pass: passId, id, labels, note }, () => (saved = { id, labels }));
};
const done = async () => {
  if (await call("POST", passPath() + "/done")) {
    head.replaceChildren();
    statusEl.hidden = true;
    app.replaceChildren(
      el("h1", "text-xl font-semibold", "All saved"),
      el("p", MUTED, "The labelling session has ended. You can close this tab."),
    );
    state = null;
  }
};

function choose(name) {
  if (state.mode !== "multi") {
    selected = [name]; // one label is the whole answer: save it and move on
    return save();
  }
  if (selected.includes(name)) selected = selected.filter((n) => n !== name);
  else if (name === "off_topic") selected = [name];
  else selected = selected.filter((n) => n !== "off_topic").concat(name);
  render();
}

const typing = () => document.activeElement && document.activeElement.id === "note";

function statusText() {
  if (typing()) return "Typing a note: the number keys are paused. Esc returns to the labels, Ctrl+Enter saves.";
  if (saved) return "Saved row " + saved.id + " as " + saved.labels.join(", ") + ". Press ← to go back.";
  return state.mode === "multi"
    ? "Choose every label that fits, then press Enter."
    : "Click a label or press its number. It saves and the next row opens.";
}

function setStatus() {
  const text = statusText();
  if (statusEl.textContent !== text) statusEl.textContent = text; // same text: no repeat announcement
}

function header() {
  const bar = el("div", "h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800");
  const fill = el("div", "h-2 bg-zinc-900 dark:bg-zinc-100");
  fill.style.width = (state.total ? (100 * state.done) / state.total : 0) + "%";
  bar.append(fill);
  const line = el("div", "flex flex-wrap items-center gap-x-8 gap-y-2");
  const title = el("h1", "text-lg font-semibold", "Label");
  title.prepend(el("span", "font-normal " + MUTED, "goldlabel / "));
  const progress = el("div", "flex min-w-64 flex-1 items-center gap-3");
  progress.append(bar, el("p", "whitespace-nowrap tabular-nums " + MUTED, state.done + " / " + state.total + " labelled"));
  line.append(title, progress);
  return line;
}

function counts() {
  const table = el("table", "w-full text-left");
  const cap = el("caption", "pb-2 text-left text-sm font-medium " + MUTED, "Labelled so far");
  const body = el("tbody");
  for (const l of state.labels) {
    const tr = el("tr", "border-t border-zinc-200 dark:border-zinc-800");
    tr.append(el("th", "py-2 pr-2 font-normal", l.name, { scope: "row" }), el("td", "py-2 text-right tabular-nums", String(state.counts[l.name] || 0)));
    body.append(tr);
  }
  table.append(cap, body);
  const box = el("section", CARD);
  box.append(table);
  return box;
}

function finished() {
  const box = el("section", CARD + " flex flex-col gap-3");
  box.append(
    el("h2", "text-lg font-semibold", "All rows are labelled"),
    el("p", MUTED, state.done + " of " + state.total + " rows in " + state.sample + " have labels. Press Done to end the session, or go back to change one."),
  );
  const row = el("div", "flex flex-wrap gap-2");
  const b = el("button", BTN, "Back  ←", { type: "button" });
  b.onclick = back;
  const d = el("button", PRIMARY, "Done", { type: "button" });
  d.onclick = done;
  row.append(b, d);
  box.append(row);
  return box;
}

function textCard() {
  const box = el("section", CARD + " flex flex-col gap-4 p-5 lg:p-8", undefined, { "aria-label": "Item to label" });
  box.append(
    el("p", "text-sm tabular-nums " + MUTED, "Row " + state.position + " of " + state.total + " in " + state.sample + " · id " + state.item.id),
    el("p", "max-w-[68ch] whitespace-pre-wrap break-words text-xl leading-relaxed", state.item.text),
  );
  return box;
}

function options() {
  const multi = state.mode === "multi";
  const group = el("fieldset", "flex flex-col gap-2");
  group.append(
    el("legend", "mb-2 text-sm font-medium " + MUTED, multi ? "Choose every label that fits" : "Choose one label: it saves and moves on"),
  );
  state.labels.forEach((l, i) => {
    const on = selected.includes(l.name);
    const b = el("button", OPTION + (on ? OPTION_ON : OPTION_OFF), undefined, { type: "button", "aria-pressed": String(on) });
    const text = el("span", "min-w-0 flex-1 break-words");
    text.append(el("span", "block font-medium", l.name));
    if (l.description) text.append(el("span", "block text-sm " + MUTED, l.description));
    b.append(el("span", KEY, i < 9 ? String(i + 1) : ""), text);
    if (on) b.append(el("span", "pr-1 font-semibold text-blue-700 dark:text-blue-300", "✓", { "aria-hidden": "true" }));
    b.onclick = () => choose(l.name);
    group.append(b);
  });
  return group;
}

function noteField() {
  const box = el("div", "flex flex-col gap-1");
  box.append(el("label", "text-sm font-medium", "Note for this row (optional, key N)", { for: "note" }));
  const t = el("textarea", "rounded-lg border border-zinc-400 bg-white p-2 dark:border-zinc-600 dark:bg-zinc-950 " + FOCUS, undefined, {
    id: "note",
    rows: "3",
    placeholder: "Why was this one hard? Edge cases noted here help when you tune the prompt.",
  });
  t.value = note;
  t.oninput = () => (note = t.value);
  t.onfocus = t.onblur = setStatus;
  box.append(t, el("p", "text-sm " + MUTED, "Saved with the label. Skipping or going back does not keep an unsaved note."));
  return box;
}

function panel() {
  const multi = state.mode === "multi";
  const box = el("section", CARD + " flex flex-col gap-4 lg:sticky lg:top-4");
  const nav = el("div", "grid grid-cols-2 gap-2");
  const b = el("button", BTN, "← Back", { type: "button" });
  b.onclick = back;
  const s = el("button", BTN, "Skip (S)", { type: "button" });
  s.onclick = skip;
  nav.append(b, s);
  if (multi) {
    const n = el("button", PRIMARY + " col-span-2", "Save and next (Enter)", { type: "button" });
    n.disabled = !selected.length;
    n.onclick = save;
    nav.append(n);
  }
  box.append(
    options(),
    noteField(),
    nav,
    el(
      "p",
      "border-t border-zinc-200 pt-3 text-sm dark:border-zinc-800 " + MUTED,
      multi
        ? "Keys: 1-9 choose, Enter save and next, ← back, S skip, N note."
        : "Keys: 1-9 label and next, ← back, S skip, N note.",
    ),
  );
  return box;
}

function ended() {
  const box = el("section", CARD + " flex flex-col gap-3");
  box.append(
    el("h2", "text-lg font-semibold", "This pass has ended"),
    el("p", MUTED, "The server that ran it was stopped, or the link is from an earlier session."),
    el("a", LINK, "Open the dataset list", { href: "#/" }),
  );
  return box;
}

function render() {
  if (!state) {
    if (error) app.replaceChildren(ended());
    return;
  }
  if (!state.finished && shown !== state.item.id) {
    shown = state.item.id;
    selected = state.item.labels || [];
    note = state.item.note || "";
  }
  head.replaceChildren(header());
  statusEl.hidden = false;
  setStatus();
  const parts = [];
  if (error) parts.push(el("p", "rounded-lg border border-red-700 p-3 text-red-800 dark:border-red-400 dark:text-red-300", "Error: " + error, { role: "alert" }));
  if (state.finished) parts.push(finished());
  else {
    const grid = el("div", "flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_26rem] lg:items-start lg:gap-6");
    grid.append(textCard(), panel());
    parts.push(grid);
  }
  parts.push(counts());
  app.replaceChildren(...parts);
}

document.addEventListener("keydown", (e) => {
  if (!state || e.repeat) return; // a held key must not label the rows that follow
  if (typing()) {
    // typing in the note: only Esc and Ctrl/Cmd+Enter act, everything else edits text
    if (e.key === "Escape") document.activeElement.blur();
    else if ((e.ctrlKey || e.metaKey) && e.key === "Enter") save();
    else return;
    e.preventDefault();
    return;
  }
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const onButton = document.activeElement && document.activeElement.tagName === "BUTTON";
  if (state.finished) {
    if (e.key === "ArrowLeft") back();
    return;
  }
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= Math.min(9, state.labels.length)) choose(state.labels[n - 1].name);
  else if (e.key === "ArrowLeft") back();
  else if (e.key === "s" || e.key === "S") skip();
  else if (e.key === "n" || e.key === "N") document.getElementById("note").focus();
  else if (e.key === "ArrowRight" || (e.key === "Enter" && !onButton)) save();
  else return;
  e.preventDefault();
});

// --- browse views: datasets, samples and rows ---------------------------------------------------

const LINK =
  "text-blue-700 underline underline-offset-2 hover:text-blue-900 dark:text-blue-300 " +
  "dark:hover:text-blue-100 " +
  FOCUS;
const CELL = "border-t border-zinc-200 py-2 pr-4 dark:border-zinc-800";

async function getJson(path) {
  const r = await fetch(path, { headers: { "X-Goldlabel": "1" } });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || "request failed (" + r.status + ")");
  return data;
}

const enc = encodeURIComponent;
const dsHref = (d) => "#/d/" + enc(d);
const sampleHref = (d, s) => dsHref(d) + "/s/" + enc(s);
const rowHref = (d, id) => dsHref(d) + "/r/" + enc(id);

function crumbs(parts) {
  const nav = el("nav", "flex flex-wrap items-center gap-2 " + MUTED, undefined, { "aria-label": "Breadcrumb" });
  nav.append(el("span", undefined, "goldlabel /"));
  parts.forEach(([text, href], i) => {
    if (i) nav.append(el("span", undefined, "/", { "aria-hidden": "true" }));
    nav.append(href ? el("a", LINK, text, { href }) : el("span", "font-semibold text-zinc-900 dark:text-zinc-100", text, { "aria-current": "page" }));
  });
  return nav;
}

function table(caption, heads, rows) {
  const t = el("table", "w-full border-collapse text-left");
  t.append(el("caption", "pb-2 text-left text-sm font-medium " + MUTED, caption));
  const tr = el("tr");
  heads.forEach((h) => tr.append(el("th", "pb-2 pr-4 text-sm font-medium " + MUTED, h, { scope: "col" })));
  const thead = el("thead");
  thead.append(tr);
  t.append(thead);
  const body = el("tbody");
  rows.forEach((cells) => {
    const row = el("tr");
    cells.forEach((c) => {
      const td = el("td", CELL + " tabular-nums");
      td.append(c);
      row.append(td);
    });
    body.append(row);
  });
  t.append(body);
  return t;
}

const text = (s) => document.createTextNode(String(s));

function datasetCard(d, linkTitle) {
  const box = el("section", CARD + " flex flex-col gap-3", undefined, { "aria-label": "Dataset " + d.title });
  const title = el("h2", "text-lg font-semibold");
  title.append(linkTitle ? el("a", LINK, d.title, { href: dsHref(d.name) }) : text(d.title));
  box.append(title);
  if (d.error) {
    box.append(el("p", "rounded-lg border border-red-700 p-3 text-red-800 dark:border-red-400 dark:text-red-300", "Error: " + d.error, { role: "alert" }));
    return box;
  }
  if (!d.taxonomy) {
    box.append(el("p", MUTED, "No taxonomy is stored in this file yet, so the labels offered are the ones already used. gl.label stores one."));
  }
  box.append(
    table(
      "Samples in " + d.title,
      ["Sample", "Rows", "Labelled", "Pending"],
      d.samples.map((s) => {
        const a = el("a", LINK, s.name, { href: sampleHref(d.name, s.name) });
        return [a, text(s.rows), text(s.labelled), text(s.pending)];
      }),
    ),
  );
  return box;
}

async function datasetsView() {
  head.replaceChildren(crumbs([["Datasets"]]));
  const list = await getJson("/api/datasets");
  if (!list.length) return [el("p", MUTED, "No gold dataset in this folder yet. Make one with gl.Gold and gold.draw_sample.")];
  return list.map((d) => datasetCard(d, true));
}

async function datasetView(name) {
  const d = (await getJson("/api/datasets")).find((x) => x.name === name);
  if (!d) throw new Error("no dataset " + name + " in this folder");
  head.replaceChildren(crumbs([["Datasets", "#/"], [d.title]]));
  return [datasetCard(d, false)];
}

async function rowsView(name, sample) {
  const rows = await getJson("/api/rows?dataset=" + enc(name) + "&sample=" + enc(sample));
  const d = (await getJson("/api/datasets")).find((x) => x.name === name);
  head.replaceChildren(crumbs([["Datasets", "#/"], [d ? d.title : name, dsHref(name)], [sample]]));
  const box = el("section", CARD + " flex flex-col gap-3");
  box.append(
    table(
      "Rows of " + sample,
      ["ID", "Labels", "Note", "Revised"],
      rows.map((r) => [
        el("a", LINK, r.id, { href: rowHref(name, r.id) }),
        text(r.labels ? r.labels.join(", ") : "pending"),
        text(r.note ? "yes" : "no"),
        text(r.revised ? "yes" : "no"),
      ]),
    ),
  );
  return [box];
}

// The hash picks the view: #/ datasets, #/d/<dataset>, #/d/<dataset>/s/<sample>, #/pass/<id>.
function parse() {
  const p = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean).map(decodeURIComponent);
  if (p[0] === "pass" && p[1]) return { kind: "pass", id: p[1] };
  if (p[0] === "d" && p[1] && p[2] === "s" && p[3]) return { kind: "rows", d: p[1], s: p[3] };
  if (p[0] === "d" && p[1] && !p[2]) return { kind: "dataset", d: p[1] };
  if (!p.length) return { kind: "datasets" };
  return { kind: "unknown" };
}

const scrolls = new Map(); // route -> scrollY, so Back lands where the list was
let shownHash = null;

async function browse(r) {
  app.replaceChildren(el("p", MUTED, "Loading..."));
  try {
    let parts = [el("p", MUTED, "No such page.")];
    if (r.kind === "datasets") parts = await datasetsView();
    else if (r.kind === "dataset") parts = await datasetView(r.d);
    else if (r.kind === "rows") parts = await rowsView(r.d, r.s);
    app.replaceChildren(...parts);
  } catch (e) {
    app.replaceChildren(el("p", "rounded-lg border border-red-700 p-3 text-red-800 dark:border-red-400 dark:text-red-300", "Error: " + e.message, { role: "alert" }));
  }
}

async function go() {
  if (shownHash !== null) scrolls.set(shownHash, window.scrollY);
  shownHash = location.hash;
  state = null;
  shown = null;
  error = "";
  saved = null;
  note = "";
  selected = [];
  const r = parse();
  statusEl.hidden = r.kind !== "pass";
  head.replaceChildren();
  if (r.kind === "pass") {
    passId = r.id;
    await load();
  } else {
    await browse(r);
  }
  window.scrollTo(0, scrolls.get(shownHash) || 0);
}

window.addEventListener("hashchange", go);
go();
