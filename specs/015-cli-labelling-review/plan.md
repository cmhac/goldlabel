# Implementation Plan: Start the labelling page from the command line, browse samples, review evaluations and revise gold labels

**Branch**: `claude/nifty-planck-1agal4` | **Date**: 2026-11-05 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/015-cli-labelling-review/spec.md`

## Summary

One labelling server per storage folder serves every gold dataset in it; `goldlabel label` and `gl.label` both start or join it.

- **Gold file.** A dataset becomes one JSON document, `gold.json` / `gold-<name>.json`: `{"taxonomy": …|null, "rows": […]}`. `gl.label` writes the taxonomy into it. A row that is revised gains an optional `revisions` list of `{at, labels, note, labelled_by}` holding the previous values. 014-format files are not read.
- **Server.** The existing `Handle` splits in two. A `Pass` keeps the 013 logic as it is (ids fixed at start, current row, Back, Skip, counts). A single `Server` per folder owns the lock, the Host and custom-header checks, a table of running passes, and the read routes for datasets, rows and evaluations. The access token is gone.
- **Joining.** The lock file holds `{pid, port, started}`. A later `gl.label` finds a live server (pid alive and `GET /api/datasets` answers), `POST`s a pass to it with `urllib`, prints `http://127.0.0.1:PORT/#/pass/N`, and polls the pass until nothing is pending or **Done** was pressed.
- **Page.** `app.js` gets a hash router (`#/`, `#/d/<dataset>`, `#/d/<dataset>/s/<sample>`, `#/d/<dataset>/r/<id>`, `#/pass/<n>`). The browser's own Back and reload give "go back without losing your place" and "reload lands where you were"; the list's scroll position is kept in a small map. The 013 labelling view is reused for a pass and, with the dataset instead of a pass id, for revising a single row.
- **Evaluations.** `clf.evaluate` also logs the disagreements (id, gold, predicted, reasoning). The server joins them to rows for the page and computes STALE from the rows' `revisions[].at` against the line's `time`.
- **Layout.** The text card and the controls card get `lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto`, `tabindex="0"` and the focus outline; `app.css` is rebuilt with the pinned Tailwind CLI.
- **CLI.** `goldlabel label [NAME] [--dir] [--port]` in `cli.py`, importing `_label` only when that subcommand runs.
- **Constitution 1.4.0** (approved by the user on 2026-11-05) allows the second subcommand; `AGENTS.md` follows.

No new module and no new dependency. Choices and alternatives are in [research.md](research.md), shapes in [data-model.md](data-model.md), the command, the HTTP routes and the Python changes in [contracts/interfaces.md](contracts/interfaces.md), and the checks in [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Python 3.12+; vanilla JavaScript for the page.

**Primary Dependencies**: none new. Standard library only for the new parts: `urllib.request` (join and wait), `http.server` (existing), `json`, `re`, `datetime`.

**Storage**: files in the storage folder:
- `gold.json`, `gold-<name>.json` (new format), `gold*.removed.jsonl` (unchanged form);
- `evals.jsonl` (lines gain `disagreements`);
- `labelling.lock` (replaces `<gold>.lock`).

**Testing**: pytest. Hand-built gold files and eval logs; the server driven over HTTP from a thread (as `tests/test_label_server.py`); `cli.main` in-process with a fake `webbrowser.open`; text checks of the served page and CSS. No browser.

**Target Platform**: a user's own computer; notebooks and a terminal.

**Project Type**: library with a local labelling page and a small CLI.

**Performance Goals**: none beyond today's. Every request rereads the dataset file(s), as `Gold` already does; datasets are hundreds of rows.

**Constraints**: importing `goldlabel` does no I/O and `cli.py` imports `_label` lazily; sync forms work inside a running loop (the existing `gl.label` is sync-only and blocks, unchanged); the gold rule; 127.0.0.1 only.

**Scale/Scope**:

| File | Change |
|---|---|
| `gold.py` | about +60/-30: JSON document, taxonomy, `revisions` field |
| `_label.py` | rewrite of about 370 lines into about 600 (Pass, Server, routes, lock, join) |
| `cli.py` | about +35: the `label` subcommand |
| `evaluation.py` | about +10: disagreements in the log line |
| `web/app.js`, `index.html`, `app.css` | about 290 → 650 lines of JS; CSS rebuilt |
| tests | `test_label_server.py`, `test_label_page.py`, `test_gold.py`, `test_e2e.py`, `test_gold_rule.py` and every fixture naming `gold.jsonl` change; new tests for revisions, join, evaluations, CLI |
| docs | README, `AGENTS.md`, constitution, seven skill files, `docs/agent-instructions.md`, `examples/sample/*` |

## Constitution Check

*GATE: passes before Phase 0; re-checked after Phase 1 (below).*

| Item | Result |
|---|---|
| I. Gold rule | PASS. Labels are written only by the server in response to a person's request (a first label, a revision). `Gold.import_rows` is unchanged. Writing the taxonomy into the file sets no label. No endpoint returns a prediction as a suggestion for a label, and the evaluation view shows predictions only beside the gold label. `gold_rule.md` is untouched. |
| II. Ponytail | PASS. The skill was invoked before drafting. Skipped, with reasons, in the spec's "Deliberately skipped" list and in research.md. |
| III. Spec Kit | PASS. spec → clarify → plan; tasks and `/ponytail-review` of spec, plan and tasks come before implementing. |
| IV. Test-first, no real service | PASS. Every task starts with the failing test; the server, lock and join are tested over loopback HTTP with `webbrowser.open` stubbed; no browser. |
| V. No hidden state | PASS. The folder resolves by `--dir`, `GOLDLABEL_DIR`, `.goldlabel/`, as for every function. The lock file is the one runtime file (it exists today). `revisions` on a row is the record the user asked for, not a library history log. |
| VI. Honest costs and evaluations | PASS. No cost or model call is added to the page. Evaluations stay code-only. `evals.jsonl` stays append-only and gains disagreements only. |
| VII. Notebook library | PASS. `gl.label` stays sync and blocking as it is. `Sample`/`GoldSet` reprs are unchanged. Importing `goldlabel` does no I/O and `cli.py` imports `_label` only for `label`. |
| Constraint: one console command | **Changes with the user's approval (2026-11-05).** Constitution 1.4.0 and `AGENTS.md` are amended in task 1 with `/speckit-constitution`. |
| Ponytail plan rules | PASS. Nothing new is abstract beyond `Pass`, which is the old `Handle` logic kept. No dependency. Complexity table below. |

**Post-design re-check**: unchanged. The one-server design needs `Pass` apart from `Server`; that is the only structural change and is justified below.

## Project Structure

### Documentation (this feature)

```text
specs/015-cli-labelling-review/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── interfaces.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks, not created here
```

### Source Code (repository root)

```text
src/goldlabel/
├── gold.py              # JSON document, taxonomy, revisions, .json names
├── _label.py            # Pass, Server, routes, folder lock, join and wait, serve_forever
├── cli.py               # + goldlabel label
├── evaluation.py        # + disagreements in the log line
└── web/{index.html,app.js,app.css}
tests/                   # as in Scale/Scope
```

**Structure Decision**: no new module; `_label.py` stays the one place that writes a label.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| `Pass` separated from the server | One server must hold several passes (a `gl.label` call, **Label pending**, a joining call) at once | A single global current row cannot serve two tabs or a joined call |
| `urllib` client inside `_label.py` | `gl.label` must hand a pass to a server in another process and wait on it | A shared file the server polls adds a second protocol; HTTP already exists |
| Breaking gold-file format | The user asked for the taxonomy in the file | Keeping JSONL plus a sidecar was the rejected snapshot design |
