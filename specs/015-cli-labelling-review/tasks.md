# Tasks: Start the labelling page from the command line, browse samples, review evaluations and revise gold labels

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/interfaces.md](contracts/interfaces.md), [quickstart.md](quickstart.md).

**Commits**: one commit per task, named `015/TNN: ...`, on `claude/nifty-planck-1agal4`. No PR unless asked.

**Tests**: red/green is required (constitution Principle IV). Every task writes its failing tests first, runs them, watches them fail for the right reason, then implements and shows them green. Expected values are written by hand. Nothing calls a real model, browser or network; the server is driven over loopback HTTP from a thread, `webbrowser.open` is stubbed, and gold files and `evals.jsonl` are built by hand.

**Green at every commit**: `tests/test_skills.py`, `tests/test_docs.py` and `tests/test_gold_rule.py` check docs and the rule against the real names, so a task that renames something also updates every doc and test that uses it, in the same commit. Each task ends with `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` passing; pre-commit enforces them. Never edit a gold file by any means: tests write gold files as fixtures only.

**The gold rule** (constitution Principle I) holds in every task: no code path sets a label except the server answering a person's request and `Gold.import_rows`; no route returns a prediction as a label suggestion. The page's CSS: after changing a class in `index.html` or `app.js`, rebuild `src/goldlabel/web/app.css` by following `src/goldlabel/web/README.md` exactly (the pinned standalone Tailwind CLI v4.3.3 downloaded from the GitHub releases; it is not a Python package and not a project dependency).

## Phase 1: Setup

- [X] T001 Amend the constitution to 1.4.0 and `AGENTS.md` with `/speckit-constitution` (the user approved on 2026-11-05): "Additional Constraints" says the package has two console commands, `goldlabel install` (skills installer) and `goldlabel label` (starts or joins the labelling page, which writes gold labels only through the labelling server); `cli.py` imports the server lazily. Also fix the matching sentences in `AGENTS.md` ("What this repo is", "Commands", "Layout") and add a one-paragraph "015 in progress" line under "Current state". Update the Sync Impact Report. Tests: `tests/test_docs.py` and `tests/test_cli.py` still pass.

## Phase 2: Foundational (blocks every story)

- [X] T002 Change the gold file to one JSON document in `src/goldlabel/gold.py`, adapting every caller, test, fixture and doc (`gold.jsonl` → `gold.json`, `gold-<name>.jsonl` → `gold-<name>.json`).

  **Tests first (red)** in `tests/test_gold.py` (use a shared `write_gold(path, rows, taxonomy=None)` helper in `tests/conftest.py` that writes the document by hand):
  - `Gold()` path is `<root>/gold.json`; `Gold(name="corpus-b")` is `<root>/gold-corpus-b.json`; the removed-rows file is `gold.removed.jsonl` / `gold-corpus-b.removed.jsonl`.
  - The file is `{"taxonomy": null | {mode, labels}, "rows": [...]}`; `draw_sample` on a new dataset writes `"taxonomy": null`.
  - `_write(rows)` keeps the stored taxonomy; `_write(rows, taxonomy=t)` replaces it; draw, import and remove keep it.
  - `GoldRow.revisions` is `None` by default and `dump()` omits it when `None` or empty; a row with two entries round-trips unchanged, entries oldest first, each `{"at", "labels", "note", "labelled_by"}`.
  - A gold file that is not JSON, lacks `rows`, or has a bad row raises `GoldError` naming the file; a 014-format `gold.jsonl` is never read (no dataset, no error).
  - Every test and fixture that builds `gold.jsonl` (`tests/test_e2e.py`, `test_gold_rule.py`, `test_bundle.py`, `test_public_api.py`, `test_label_server.py`, `test_label_page.py`, `test_notebook.py`, `tests/fixtures/pre006/README.md`) uses the new name and shape.

  **Implementation:** `Gold.path` uses `.json`; `_read` returns `doc["rows"]`; add `_doc()`; `_write(rows, taxonomy=KEEP)` rewrites the whole file atomically (`tmp` then `os.replace`) keeping the stored taxonomy unless one is passed; `GoldRow.revisions: list[dict] | None = None` dropped from `dump()` when empty. The per-gold-file `.lock` name follows the path (`gold.json.lock`) until T003. Update README, `examples/sample/*`, skills, references, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md`, `AGENTS.md`: grep `gold.jsonl` and `gold-.*jsonl` finds none outside `specs/00*`-`014` history and the removed-rows file.

- [X] T003 Split the server in `src/goldlabel/_label.py`, drop the token, and move the lock to the folder, adapting `src/goldlabel/web/app.js` and `index.html` just enough to keep the 013 labelling view working.

  **Tests first (red)** in `tests/test_label_server.py` and `tests/test_label_page.py` (rewrite the token and per-file lock tests):
  - No token anywhere: `GET /` and the asset URLs contain no `token`; the served `index.html` has no `__TOKEN__`.
  - Host check: `Host: evil.example` → 403 on any route; `127.0.0.1:<port>` and `localhost:<port>` pass.
  - Every non-GET without header `X-Goldlabel: 1` → 403 (including `POST /api/pass` and `POST /api/label`); with it, accepted. GET needs no header.
  - Bodies over 1 MB → 400; non-object JSON → 400; the server binds only `127.0.0.1`.
  - `POST /api/pass {dataset, samples, force?}` creates a pass over the rows pending now (every row with `force`) and returns `{pass: ID}` where `ID` is a short random string (`secrets.token_urlsafe(6)`, an identifier, not a secret; ids are not reused after a restart); `GET /api/pass/ID` returns the 013 state object plus `pending` and `ended`; `POST /api/pass/ID/back`, `/skip`, `/done` behave as the 013 routes; `POST /api/label` with `pass` advances that pass. Two passes on one server do not disturb each other. An unknown pass id (for example one from before a restart) → 404 `{"error": "this pass has ended"}`.
  - Lock: `labelling.lock` in the gold file's folder holds exactly `{"pid", "port", "started"}` after the socket is bound; removed on stop; a lock for a dead pid, a closed port, or unreadable JSON is replaced; a second `serve` for a folder with a live server raises `GoldRuntimeError` (T009 turns that into joining). The per-gold-file `.lock` and its tests are deleted.
  - `Done` stops the server when it was started by `gl.label` (`stop_on_done=True`) and only marks the pass ended otherwise.
  - The simulated humans in `tests/test_e2e.py` (the token and `GET /api/state`/`POST /api/done` calls near lines 90-112) and `tests/test_gold_rule.py` (the `X-Goldlabel-Token` post near line 211) use the new URL, the `X-Goldlabel: 1` header and the pass routes, and still prove the pipeline and the rule.
  - Still true from 013/014: the pass rows are fixed at start, counts are for the pass only, `force_open_ui` walks every row once, extra row keys survive a save, no response carries a prediction.

  **Implementation:** keep the `Handle` pass logic as `Pass` (ids, `review`, `current`, history, `_after`, `_state`, `label`, `back`, `skip`) and add `pending()`, `end()`. New `Server(folder, stop_on_done)`: binds first, then creates the lock with `O_EXCL`, holds `passes: dict[str, Pass]` and a mutex, applies the Host and `X-Goldlabel` checks, serves routes per [contracts/interfaces.md](contracts/interfaces.md). Build a `Gold` per request with `Gold(name=…)` and set `.path` inside the server's folder (one comment: a notebook may change `settings.root`). `serve()` and `label()` keep their signatures and now start a `Server` and a first pass, printing `Labelling page: http://127.0.0.1:PORT/#/pass/<ID>`. In `web/app.js` set the header on every `fetch`, call the pass routes, and read the pass id from `location.hash`; in `index.html` remove `?token=__TOKEN__`. Rebuild `app.css` only if a class changed.

## Phase 3: User Stories 1 and 5 (P1) — open from a terminal, revise by id, record each revision

**Goal**: `goldlabel label` opens a page listing datasets and samples, any row can be opened by id and revised, and each revision is recorded on the row.

**Independent test**: the Independent Tests of Stories 1 and 5 in `spec.md`; [quickstart.md](quickstart.md) scenarios 1 to 4 of section 2.

- [X] T004 [US5] Record revisions when the server saves a row, in `src/goldlabel/_label.py`.

  **Tests first (red)** in `tests/test_label_server.py` (hand-built gold file, `POST /api/label` over HTTP, expected files written in the test):
  - Row with labels `["yes"]`, saved as `["no"]`: the row's labels are `["no"]`, `labelled_by` is `"goldlabel-ui"`, `labelled_at` is new, and `revisions` has exactly one entry whose `labels` is `["yes"]`, `note` is the previous note, `labelled_by` is the previous stamp, and `at` is an ISO time not before the request.
  - Imported row (`labelled_by: "imported"`) revised: the entry keeps `"imported"`; the row becomes `"goldlabel-ui"`.
  - Note-only change: one entry; labels unchanged.
  - Same labels and same note: no entry and the file bytes are unchanged (compare `read_bytes()` before and after).
  - First label of a pending row: no `revisions` key at all.
  - Revised twice: two entries, oldest first, each holding the values from just before its own change.
  - Entry and new values land in one atomic rewrite (the file is never seen with a new label and no entry: assert by reading after each request).
  - Validation is the same as a first label: unknown label, two labels in `single` mode, empty list, off-topic mixed with others → 400 and the file is unchanged.
  - Every other row in the file is byte-identical to before.

  **Implementation:** one `_save(gold, id, labels, note)` used by `Pass.label` and `POST /api/label` without `pass`. Revisions are only appended by the server, never edited or removed.

- [X] T005 [US1] Add the dataset, rows and row routes and store the taxonomy from `gl.label`, in `src/goldlabel/_label.py`.

  **Tests first (red)** in `tests/test_label_server.py` and `tests/test_gold.py`:
  - `GET /api/datasets` over a folder with `gold.json` (samples `dev` 3 rows 2 labelled, `test` 2 rows 0 labelled) and `gold-corpus-b.json` returns datasets keyed by file stem, `gold` and `gold-corpus-b`, each with a display `title` (`default`, `corpus-b`) and each sample's `rows`, `labelled`, `pending` (hand-written: dev 3/2/1, test 2/0/2) and `taxonomy: true/false`; a file with bad JSON lists as `{name, error}` and the other datasets still list; `gold.removed.jsonl`, `*.tmp`, `gold.jsonl` and `labelling.lock` are not datasets (match `gold(-[a-z0-9_-]+)?\.json` fully). A folder with both `gold.json` and `gold-default.json` (a dataset really named `default`) lists two datasets, `gold` and `gold-default`, and every route reaches each one separately.
  - `GET /api/rows?dataset=&sample=` returns `{id, labels, note: bool, revised: bool}` in file order; unknown dataset or sample → 404.
  - `GET /api/row?dataset=&id=` returns the fields in [contracts/interfaces.md](contracts/interfaces.md); unknown id → 404; `options` come from the stored taxonomy with its descriptions and `off_topic`; with `taxonomy: null` they are the labels already used in that dataset (mode `multi` if any row has two labels, else `single`, empty descriptions) and `stored_taxonomy` is false.
  - `POST /api/label` without `pass` can revise any row of any sample, labelled or pending, and returns the row.
  - `gl.label(sample, taxonomy, open_browser=False)` with no live server (its own server stopped by a posted `done`) writes the taxonomy into the gold file when it differs, leaves rows and labels byte-identical, and a second call with another taxonomy replaces it; `draw_sample`, `import_rows`, `remove` and `clf.evaluate` never write one.
  - `POST /api/pass` with a `taxonomy` object stores it in the dataset's file through the server's own save (rows and labels byte-identical, validated by `Taxonomy`); a bad one → 400 and the file is unchanged.

  **Implementation:** a small `_datasets(folder)` scan; routes on `Server`; the server, not the calling process, writes the taxonomy, either at start (no live server: `label()` hands `taxonomy.model_dump()` to its own `Server` before serving) or on `POST /api/pass`.

- [X] T006 [US1] Build the browse views in `src/goldlabel/web/app.js` and `index.html` (router, datasets, samples, row lists), then rebuild `src/goldlabel/web/app.css`.

  **Tests first (red)** in `tests/test_label_page.py` (text checks of the served files; no browser):
  - The served JS routes `location.hash` for `#/`, `#/d/<dataset>`, `#/d/<dataset>/s/<sample>` and `#/pass/<id>`, with a `hashchange` listener; a `Map` stores and restores `scrollY` per route.
  - Dataset titles show `default` for `gold`; a dataset with an `error` shows the message and the others still list.
  - A 404 from a pass route shows "this pass has ended" with a link to `#/`.
  - Dynamic text is set with `textContent`, never `innerHTML` (the existing 013 check extended to the new views).
  - The 013 labelling view, keys (`1`-`9`, `←`, `S`, `N`, `Esc`, `Ctrl`/`⌘`+`Enter`), held-key rule and the single `role="status"` element are unchanged (existing tests pass). CSS contains the classes the new views use.

  **Implementation:** `route()` plus `datasets()`, `samples()` and `rows()` views; each row in the list links to `#/d/<dataset>/r/<id>`.

- [X] T007 [US1] Add the row editor, **Jump to id**, **Label pending** and Back to `src/goldlabel/web/app.js`, then rebuild `src/goldlabel/web/app.css`.

  **Tests first (red)** in `tests/test_label_page.py`:
  - The served JS handles `#/d/<dataset>/r/<id>`; has a **Jump to id** field on dataset and sample pages that navigates to that route and shows "no row <id> in <dataset>" on a 404 without leaving the page; a **Label pending** button that posts `/api/pass` (with the dataset stem and sample) and navigates to `#/pass/<id>`; a Back that uses `history.back()`.
  - The editor shows the row's current labels pre-selected and the note, reuses the 013 `options()`, `noteField()`, `textCard()` and `panel()`, saves with `POST /api/label` (no `pass`), says so when `stored_taxonomy` is false, and shows a label outside the options as "not in this taxonomy".
  - **Done** on a pass navigates to `#/` when the server did not stop. Text is set with `textContent`.

- [X] T008 [US1] Add `goldlabel label [NAME] [--dir PATH] [--port N]` in `src/goldlabel/cli.py` (starting a server; joining comes in T009).

  **Tests first (red)** in `tests/test_cli.py` (in-process `main([...])`, `webbrowser.open` and the blocking wait stubbed, the server started on a thread and stopped by the test):
  - `main(["label"])` in a folder with `gold.json` starts a server, prints `Labelling page: http://127.0.0.1:<port>/`, the folder, and `GOLD_RULE_SHORT`, opens the browser once on `/` and, with `NAME`, on `/#/d/gold-NAME` (the file stem of the named dataset); returns 0 after the wait is released; removes the lock.
  - `--dir PATH` serves `PATH`; without it `GOLDLABEL_DIR`, then `.goldlabel/`.
  - Exit 1 and nothing started (no lock written): empty folder (message names the folder and says to make one with `gl.Gold`); `NAME` with no file (prints the datasets that exist); `--port` already bound; unreplaceable stale lock.
  - A `Server` started by the command ignores **Done** for stopping (`stop_on_done=False`).
  - There is no flag that takes a taxonomy, an import path or a label; `main(["label", "--help"])` lists only `NAME`, `--dir`, `--port`.
  - `import goldlabel.cli` imports no `goldlabel._label` until `label` runs (`sys.modules` check in a subprocess).

  **Implementation:** a `label` subparser next to `install`; `settings.root = Path(args.dir)` when given; call `goldlabel._label.run_forever(folder, name, port)` which binds, writes the lock, prints, opens the browser and waits for KeyboardInterrupt.

**Checkpoint**: MVP. Stories 1 and 5 work from a terminal with no notebook.

## Phase 4: User Story 2 (P1) — `gl.label` and the command join a running server

- [X] T009 [US2] Join a live server from `gl.label` and from the command, in `src/goldlabel/_label.py` and `src/goldlabel/cli.py`.

  **Tests first (red)** in `tests/test_label_server.py` and `tests/test_cli.py` (a real `Server` on a thread in the test process stands in for "another process"; the lock names this pid, so the test also covers a dead-pid lock, a closed port, and garbage):
  - Live server + `gl.label(dev, taxonomy, open_browser=False)` in a second thread: prints the running server's URL as `http://127.0.0.1:<port>/#/pass/<ID>`; the number of listening sockets in the process does not change; a pass exists with `dev`'s pending rows; the call does not return while a row of the pass is pending; labelling the last pending row over HTTP releases it and it returns the `Sample`; posting `done` for that pass releases it with rows still pending; `KeyboardInterrupt` raised in the waiting thread propagates and writes nothing.
  - `force_open_ui=True` with a live server: prints the URL and returns at once, the pass covers every row.
  - With a live server, the joining `label()` never opens or writes a gold file itself: it sends the taxonomy in the `POST /api/pass` body and the server stores it (assert that the only writer is the server's thread). A label saved through the server between the caller's start and its post survives (the lost-update case).
  - `label()` itself writes no label.
  - Liveness: a lock whose pid is alive but whose port is closed, a lock for a dead pid, and a garbage lock are all replaced, and the call starts its own server (stopped on **Done**).
  - `main(["label", "x"])` with a live server prints that server's URL on `/#/d/gold-x`, opens it, returns 0 and starts nothing.
  - Two folders: a server for one does not affect the other.

  **Implementation:** `_live(folder)` returns the port when the pid is alive and `GET /api/datasets` answers 200; `label()` posts the pass with `urllib.request` (header `X-Goldlabel: 1`), prints, then polls `GET /api/pass/<ID>` once a second with `time.sleep(1)` (tests patch the sleep) until `pending == 0` or `ended`. The "already being labelled" `GoldRuntimeError` and its tests are removed.

## Phase 5: User Story 3 (P2) — review evaluations and disagreements

- [ ] T010 [P] [US3] Log the disagreements in `src/goldlabel/evaluation.py`.

  **Tests first (red)** in `tests/test_evaluation.py`:
  - After `clf.evaluate(sample)` with a `FunctionModel` that gets rows `b` and `d` wrong, the one new `evals.jsonl` line has `"disagreements": [{"id": "b", "gold": [...], "predicted": [...], "reasoning": …}, {"id": "d", …}]` (values written by hand), no `text` key, and `predicted` is `null` for an item that failed.
  - An identical rerun still appends nothing and makes no model call; a changed prompt appends a second line.
  - Lines already in a log without `disagreements` are still read by `_history` and `Sample` summaries; the `same` keys are unchanged.

- [ ] T011 [US3] Add `GET /api/evals` with the stale flag in `src/goldlabel/_label.py`.

  **Tests first (red)** in `tests/test_label_server.py` with a hand-written `evals.jsonl` and gold file:
  - `GET /api/evals?dataset=&sample=dev` returns the lines whose `samples` include `dev`, newest first, each with `time`, `samples`, `score`, `target`, `passed` (PASS/FAIL, or none with no target), `n`, `skipped_pending`, `model`, `digest`, `stale`, `stale_rows`, `disagreements`; lines for another gold file or another sample are absent; a `dev + test` line appears under both samples with `samples == ["dev", "test"]`.
  - Each disagreement is joined with the row's `text`, current `labels`, `note`, `revised` (a revision after the line's `time`) and `missing` (id no longer in the file; the logged gold and predicted still shown).
  - A line with no `disagreements` key returns `disagreements: null` (the page says "disagreements were not recorded by this version").
  - Stale: a row of the sample with a `revisions[].at` later than the line's `time` → `stale: true` and its id in `stale_rows`; a revision earlier than the line, a first label (no entry), a revision in another sample, or none → `stale: false`; `dev + test` is stale after a revision in either; times are compared as parsed datetimes.
  - No route runs an evaluation or a model call (the existing "server never touches a model" test still passes).

- [ ] T012 [US3] Add the evaluation views to `src/goldlabel/web/app.js`, then rebuild `app.css`.

  **Tests first (red)** in `tests/test_label_page.py`: the served JS renders, on the sample route, the list from `/api/evals` with the words **STALE** and **PASS**/**FAIL** (state in words, never colour alone), a disagreement table (id, text, gold, predicted, reasoning, note), a "revised since" line showing the current label, "no longer in the file", and "disagreements were not recorded by this version"; each disagreement links to `#/d/<dataset>/r/<id>`; there is no button, key or `fetch` that runs an evaluation or classification; text is set with `textContent`.

## Phase 6: User Story 4 (P2) — the text stays in view

- [ ] T013 [US4] Make the cards scroll independently from 1024px in `src/goldlabel/web/app.js` (`textCard`, `panel`), then rebuild `app.css`.

  **Tests first (red)** in `tests/test_label_page.py`: the served JS gives the text card and the controls card each `lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto`, `tabindex="0"` and the focus classes; the one-column layout adds no sticky, fixed or `max-h` class below `lg`; the served `app.css` contains the rules for those classes inside the 1024px media query (`min-width:64rem`) and none without a query. The page's help text says what happens below 1024px.

  **Implementation:** the class changes above; rebuild the CSS; the 013 "row line" and keys are unchanged.

## Phase 7: Polish and cross-cutting

- [ ] T014 Teach the new command in the docs and skills (FR-025), keeping the rule verbatim: README, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md`, `src/goldlabel/skills/goldlabel/SKILL.md` and `references/`, `goldlabel-tune` and `goldlabel-run` where they offer the labelling page: users run `goldlabel label` to review or revise labels; agents hand that command to the user and never write a label. Add the new names to `tests/test_docs.py`/`tests/test_skills.py` expectations only as needed (the rule text is never reworded; the tests print what to paste). `examples/sample/walkthrough.py` and `.ipynb` stay cell-for-cell equal with no outputs.

- [ ] T015 Final pass: `/ponytail-review` of the diff and `/ponytail-debt` (report both; fix what they find), then update `AGENTS.md` "Current state" (015 implemented: summary, and the human checks of the spec: real browser at 1280px and 390px, light/dark, keyboard only, `gl.label` joining a running page, an evaluation going STALE after a revision, the gold-rule refusal trial, the Tailwind rebuild) and `specs/015-cli-labelling-review/spec.md` status. Run the four checks and `uv build` (the wheel must still contain `goldlabel/web/*` and `goldlabel/gold_rule.md`). Final report as the constitution requires.

## Dependencies and order

- T001 first (constitution). T002 → T003 → T004 → T005 → T006 → T007 → T008 → T009, in order: they share `_label.py`, `app.js` and the tests.
- T010 touches only `evaluation.py` and `tests/test_evaluation.py`: [P] with anything from T003 on. T011 needs T005 and T010. T012 needs T007 and T011. T013 needs T006. T014 needs T008, T009. T015 last.
- MVP: T001 to T008. Then T009 (join), T010 to T012 (evaluations), T013 (layout), in any order after their prerequisites.

## Parallel example

After T002: one agent takes T010 (`evaluation.py`) while another does T003 to T005; they meet at T011.

## Deliberately skipped (from the spec)

Running evaluations from the page; editing the taxonomy in the page; adding, drawing or removing rows from the page; search, filters or bulk edit; undo; live refresh; `--host`/`--no-browser`; a separate revision log; migrating 014 files; any new dependency, abstraction beyond `Pass`, router or table library.
