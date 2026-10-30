// Renders the server's `state` and posts the person's actions. No rules live here: the server
// validates labels, picks the next item and writes the file.
const token = new URLSearchParams(location.search).get("token") || "";
const app = document.getElementById("app");
let state = null;
let shown = null; // id of the item the selection belongs to
let selected = [];
let error = "";

const BTN =
  "min-h-11 rounded-lg border border-zinc-300 bg-white px-4 py-2 font-medium text-zinc-900 " +
  "hover:bg-zinc-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 " +
  "disabled:opacity-60 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 dark:hover:bg-zinc-800 " +
  "dark:focus-visible:outline-blue-400";
const PRIMARY =
  "min-h-11 rounded-lg border border-zinc-900 bg-zinc-900 px-4 py-2 font-semibold text-white " +
  "hover:bg-zinc-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700 " +
  "disabled:opacity-60 dark:border-zinc-100 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-300 " +
  "dark:focus-visible:outline-blue-400";
const CARD =
  "rounded-lg border border-zinc-300 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-900";

function el(tag, cls, text, attrs) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  for (const k in attrs || {}) e.setAttribute(k, attrs[k]);
  return e;
}

async function call(method, path, body) {
  try {
    const r = await fetch(path, {
      method,
      headers: { "X-Goldlabel-Token": token, "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await r.json();
    if (!r.ok) {
      error = data.error || "request failed (" + r.status + ")";
    } else {
      error = "";
      state = data;
    }
  } catch (e) {
    error = "Cannot reach the labelling server. Has it been stopped?";
  }
  render();
}

const load = () => call("GET", "/api/state");
const save = () => selected.length && call("POST", "/api/label", { id: state.item.id, labels: selected });
const back = () => call("POST", "/api/back");
const skip = () => call("POST", "/api/skip");
const done = async () => {
  await call("POST", "/api/done");
  if (!error) {
    app.replaceChildren(
      el("h1", "text-xl font-semibold", "All saved"),
      el("p", "text-zinc-600 dark:text-zinc-400", "The labelling session has ended. You can close this tab."),
    );
    state = null;
  }
};

function choose(name) {
  const multi = state.mode === "multi";
  if (!multi) selected = [name];
  else if (selected.includes(name)) selected = selected.filter((n) => n !== name);
  else if (name === "off_topic") selected = [name];
  else selected = selected.filter((n) => n !== "off_topic").concat(name);
  render();
}

function header() {
  const bar = el("div", "h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800");
  const fill = el("div", "h-2 bg-zinc-900 dark:bg-zinc-100");
  fill.style.width = (state.total ? (100 * state.done) / state.total : 0) + "%";
  bar.append(fill);
  const head = el("div", "flex items-baseline justify-between gap-2");
  head.append(
    el("h1", "text-lg font-semibold", "Label"),
    el("p", "tabular-nums text-zinc-600 dark:text-zinc-400", state.done + " / " + state.total + " labelled"),
  );
  return [head, bar];
}

function counts() {
  const table = el("table", "w-full text-left");
  const cap = el("caption", "pb-2 text-left text-sm font-medium text-zinc-600 dark:text-zinc-400", "Labelled so far");
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
    el("p", "text-zinc-600 dark:text-zinc-400", state.done + " of " + state.total + " rows have labels. Press Done to end the session, or go back to change one."),
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

function item() {
  const box = el("section", CARD + " flex flex-col gap-4");
  box.append(el("p", "whitespace-pre-wrap break-words text-lg leading-relaxed", state.item.text, { "aria-label": "Item to label" }));
  const group = el("fieldset", "flex flex-col gap-2");
  group.append(el("legend", "mb-2 text-sm font-medium text-zinc-600 dark:text-zinc-400", state.mode === "multi" ? "Choose every label that fits" : "Choose one label"));
  state.labels.forEach((l, i) => {
    const on = selected.includes(l.name);
    const row = el(
      "label",
      "flex min-h-11 cursor-pointer items-start gap-3 rounded-lg border p-3 " +
        (on ? "border-zinc-900 bg-zinc-100 dark:border-zinc-100 dark:bg-zinc-800" : "border-zinc-300 dark:border-zinc-700"),
    );
    const input = el("input", "mt-1 size-5 shrink-0", undefined, { type: state.mode === "multi" ? "checkbox" : "radio", name: "label" });
    input.checked = on;
    input.onchange = () => choose(l.name);
    const text = el("span", "min-w-0 break-words");
    text.append(el("span", "font-medium", (i < 9 ? i + 1 + ". " : "") + l.name));
    if (l.description) text.append(el("span", "block text-sm text-zinc-600 dark:text-zinc-400", l.description));
    row.append(input, text);
    group.append(row);
  });
  box.append(group);
  const nav = el("div", "grid grid-cols-3 gap-2");
  const b = el("button", BTN, "← Back", { type: "button" });
  b.onclick = back;
  const s = el("button", BTN, "Skip", { type: "button" });
  s.onclick = skip;
  const n = el("button", PRIMARY, "Save →", { type: "button" });
  n.disabled = !selected.length;
  n.onclick = save;
  nav.append(b, s, n);
  box.append(nav);
  box.append(el("p", "text-sm text-zinc-600 dark:text-zinc-400", "Keys: number = choose, Enter or → = save and next, ← = back."));
  return box;
}

function render() {
  if (!state) return;
  if (!state.finished && shown !== state.item.id) {
    shown = state.item.id;
    selected = state.item.labels || [];
  }
  const parts = header();
  if (error) parts.push(el("p", "rounded-lg border border-red-700 p-3 text-red-800 dark:border-red-400 dark:text-red-300", "Error: " + error, { role: "alert" }));
  parts.push(state.finished ? finished() : item(), counts());
  app.replaceChildren(...parts);
}

document.addEventListener("keydown", (e) => {
  if (!state || e.ctrlKey || e.metaKey || e.altKey) return;
  const onButton = document.activeElement && document.activeElement.tagName === "BUTTON";
  if (state.finished) {
    if (e.key === "ArrowLeft") back();
    return;
  }
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= state.labels.length) choose(state.labels[n - 1].name);
  else if (e.key === "ArrowRight" || (e.key === "Enter" && !onButton)) save();
  else if (e.key === "ArrowLeft") back();
  else return;
  e.preventDefault();
});

load();
