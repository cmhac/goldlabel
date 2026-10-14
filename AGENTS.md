# AGENTS.md

## What this repo is

`hunches` is an interactive Textual TUI toolkit for content analysis over an already-embedded corpus: seed phrases → semantic search → candidates → LLM classifier validated against a hand-labelled gold set → classified output. An assistant model talks to the user; a classifier model does bulk classification (renamed from smart/cheap in 002). Python package `hunches`, console script `hunches`.

## Current state

001 (stages 1-9), 002 (system setup, projects, onboarding; tasks 01-09), 003 (TUI redesign, tasks 01-18) 004 (history, undo/redo, stale stages and the Redo plan; tasks 01-11), 005 (pgvector backend; tasks 01-13) and 006 (fixes from the first real test run; tasks 01-13) are implemented. Still needed from a human: the manual terminal pass listed in `specs/003-tui-redesign/tasks/18-e2e-and-docs.md`, and for 004 the checks in the spec's "Needs a human": that F6-F9 reach the app in the terminals we care about (and that the `↻` `◐` glyphs render), then the manual pass (edit seeds, a label description and the prompt; undo/redo each; `git checkout prompt.md` shows the external-change notice; change the prompt after a full run, stages 5-8 show stale and the Redo plan counts match the real run).

- 006 needs a human (`specs/006-test-run-fixes/spec.md`, "Needs a human"): whether the mouse pointer shape changes in the terminals Chris uses (Terminal.app unknown); that the RUNNING glyph `▶` and the thinking spinner glyphs render; that `ctrl+j` reaches the chat box in those terminals; that clicks reach the app; a real-model pass on the seed assistant prompt (asks first, corpus-voiced seeds, `replace_seed`/`delete_seeds`); a look at the Search first-run block (its button is a 36-cell bar) and results grids at 80×24 and 120×36, the descriptions popup, and the New project title row at 100 columns or more; the install size of `hunches[local]` (about 5.5 GB on Linux).
- 005 is implemented but not yet tested against a real managed service: Chris runs `specs/005-pgvector/manual-checklist.md` (RDS/Aurora IAM first) before the branch is merged. Its CI job (`pgvector` in `.github/workflows/ci.yml`) is optional and has not run yet.
- Source of truth for behaviour: `specs/001-initial-version/spec.md`, then `specs/002-onboarding-setup/spec.md` (which lists its explicit changes to 001), then `specs/003-tui-redesign/spec.md` (its "Behaviour that changes in 001 and 002" lists what it overrides), then `specs/004-history-and-redo/spec.md` (its "Clarifications" blocks record deviations made while implementing; "Behaviour that changes in 001–003"), then `specs/005-pgvector/spec.md` (its "Verified in task NN" subsections and "Clarifications from implementation" win over the draft text above them), then `specs/005-pgvector/deltas/` in number order (each delta wins over `spec.md`; 01 adds the two-table layout `pg_text_table`/`pg_text_id_column`, 02 names saved URLs by `pg_url_id`, a hash of host/port/database/user), then `specs/006-test-run-fixes/spec.md` (its "Verified in task NN" notes and "Clarifications from implementation" win over the draft text above them; "Behaviour that changes in 001–005")
- Implementation plans: `specs/<spec>/tasks/README.md` (dependency order, human-only actions) and one file per task. 001: `01-…` to `18-…`; 002: `01-…` to `09-…`; 003: `01-…` to `18-…`; 004: `01-…` to `11-…`; 005: `01-…` to `13-…`; 006: `01-…` to `13-…`

**Before starting any work: read the spec, then your task file.** If a task file and the spec disagree, flag it instead of guessing. If the spec is wrong or incomplete, say so and update it in the same change.

## Principles (non-negotiable)

- Absolute minimal implementation. No abstraction, base class, registry or plugin system unless the user explicitly asks. Where two behaviours must coexist (local vs S3 vector search), use a plain `if` in one function.
- Plain files in `.hunches/` are the only state. The tool itself never runs git; the user commits.
- Check every Pydantic AI and Textual API against the current docs before using it. Do not code from memory. Pydantic AI docs are under https://pydantic.dev/docs/ai/ (`llms.txt` index there); Textual testing guide: https://textual.textualize.io/guide/testing/
- Never call a real LLM or AWS API in tests. Use pydantic-ai `TestModel` / `FunctionModel`, stubbed boto3 responses and tiny hand-built vectors.
- Never show a cost of $0 when the price is unknown. Unknown is `?` with a prominent warning.
- Never commit API keys. Keys come from the environment or a git-ignored `.env`.

## Stack

Python 3.12+, `uv`, `pydantic-ai` (Agent, Embedder), `textual`, `numpy`, `genai-prices`, `pyyaml`, `boto3` and `psycopg[binary]` (S3 Vectors, pgvector, RDS/Aurora IAM), optional extra `local` (`sentence-transformers`, about 5.5 GB with CUDA wheels, Python < 3.14). Lint/format `ruff`, types `ty`, tests `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`).

## Commands (once task 01 has landed)

```
uv sync --extra local
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest                 # everything (CI runs this); parallel via pytest-xdist
uv run pytest -m "not ui"     # fast tier; this is what pre-commit runs
uv run pytest tests/test_x.py # targeted UI tests
uv run hunches          # run from a directory containing (or to create) .hunches/
```

Ruff, ty and the fast tests (`pytest -m "not ui"`) must pass before every commit (pre-commit enforces this). The slow Pilot UI tests (marked `ui` automatically in `tests/conftest.py` for any module that calls `run_test(`) are a CI requirement in GitHub Actions, not a pre-commit one. Locally, whenever a change touches a screen, modal, `app.py`, `theme.py`, `hunches.tcss` or anything a screen reads, run the relevant UI test files (targeted, e.g. `uv run pytest tests/test_tune_screen.py tests/test_sizes.py`) during development; run the full suite only when the change is broad. Do not wait on the full suite for every small change. If these commands don't exist yet, task 01 hasn't been done; do it first.

## Layout (target)

- `src/hunches/` — one module per concern (`files.py`, `cost.py`, `search.py`, `candidates.py`, `metrics.py`, `classifier.py`, `app.py`), screens in `src/hunches/screens/`
- System scope (per user, outside git): `system.py` (`system.json`, project/store lists, recommended models), `keys.py` (API keys: env > keyring), `models.py` (model list and prices for the pickers). `$HUNCHES_HOME` overrides the system directory
- Screens added by 002: `screens/system.py` (system settings, recommendation modal), `screens/projects.py`, `screens/new_project.py`, `screens/project_settings.py`, `screens/paths.py` (`PathInput`, `PathPicker`), `screens/model_picker.py`
- `screens/progress.py` (003): `LabelBar` (a labelled progress bar), `RunIndicator` (the centred run block with Stop/Resume/Start button), `eta_text`, `seconds_text`. The chat is `ChatPanel` in `app.py` (`send_context`, `record`, `ChatPanel.Submitted`, edits recorded without a model call via `files.edit_message`); there is no separate chat module
- Taxonomy versions (003 task 17): `files.taxonomy_in_use/labels_changed/list_versions/archive_version/start_new_version/restore_version`, archives in `.hunches/versions/<n>/` (never deleted), `VersionsScreen` in `screens/taxonomy.py`
- `HunchesApp.on_mount` runs the startup flow; always-on keys: `f3` project settings, `f4` Projects, `f5` System settings, `f8` History, `f9` Redo plan (stage screens, only while something is marked)
- History and redo (004): `history.py` (objects + append-only `log.jsonl` in `.hunches/history/`; `save` is the only writer of `seeds.csv`/`taxonomy.yaml`/`prompt.md`, plus `sync`, `undo/redo/restore`, `approval`, `NeedsVersion`); `screens/history.py` (`HistoryScreen`, `NeedsVersionScreen`, `ExternalNotice`, announced by `HunchesApp.check_history`); `screens/redo_plan.py` (`RedoPlanScreen`). `files.approve` is the only way to set a `State` flag (records `state.inputs`); `files.current_inputs/run_digest/stage_status` (statuses `current/stale/incomplete/not_started`, reasons <= 24 chars) drive the rail marks, `StageBanner`s and `first_incomplete_stage`; `files.orphaned_gold/gold_coverage` and `screens.gold.remove` (rows go to `gold_removed.jsonl`; `draw` skips them) for gold after a seeds change (`RemoveGoldScreen`, `GoldRowsScreen` in `screens/gold.py`); `classifier.is_cached/redo_plan` count live vs cached calls without calling anything. `hunches.app.current_status()` caches `stage_status` for 0.5 s. F6/F7 undo/redo are screen bindings on Brief, Taxonomy and the Tuning prompt modal; Textual's `TextArea` binds F6/F7 itself (select line / all), so the prompt modal declares them as priority bindings active only while the text equals the file. Gold labels are not in the history; the assistant gets `# Pipeline status` and `# Gold coverage` and Tuning has `get_gold_coverage/remove_gold/draw_gold` (never sets a label)
- pgvector (005): all database code is in `search.py` (`pg_connect`, `pg_message` scrubber, `extension_version`, `column_type`, `table_estimates`, `search_pg_exact` one query for all seeds, `search()` `index` mode, `is_approximate`, `Stop`/`SearchCancelled`, `check_store`); `candidates.build_candidates` has one `if` for it. Config fields are `Config.pg_*` read through `files.pg_setting` (defaults in `files.PG_DEFAULTS`); the connection URL is never in `config.toml`/`system.json` (environment or keyring via `keys.resolve/status/save`, variable named by `pg_url_var`, default `HUNCHES_PG_URL`); the only system field is `System.pg_max_result_mb` (512, edited in System settings). The UI is `screens/pg.py` (shared by New project and Project settings). Everything is read-only (`SELECT` and `SET LOCAL`, plus savepoints in `check_store`); identifiers go through `psycopg.sql.Identifier`. Tests: `tests/test_search_pg_*.py` use a fake `psycopg`; `tests/test_pg_integration.py` needs `HUNCHES_TEST_PG_URL` and is skipped otherwise
- Descriptions (006): `Config.project_description/store_description` (optional, written to `config.toml` when non-empty); `files.project_context()` (`# Project` and `# Store` blocks, "not provided" when empty), `files.status_context()` (pipeline status and gold coverage) and `files.assistant_context()` = both; Tuning hashes only `status_context()` so editing a description never sends an UPDATED message. `screens/new_project.py` has `compose_about`/`missing_about` (the two `TextArea.about`s, shared with Project settings and the popup); `screens/descriptions.py` is `DescriptionsScreen`, the required popup (no Esc; Save F2, Quit ctrl+q) that `HunchesApp.check_descriptions` pushes once per project open from `switch_to`
- Seed assistant (006): `brief.INSTRUCTIONS` (corpus voice, ask first) and the tools `propose_seeds`, `replace_seed(number, was, text)`, `delete_seeds(numbers)`, all through `BriefScreen.save` -> `history.save` with `source="assistant"` and the turn's group; they refuse while `BriefScreen.editor` is open
- Keeping runs alive (006): `HunchesApp.kept` (stage -> screen installed as `stage-<n>` while `working()`), `stage_screen`, `working(screen)` (a `run`-group worker or a `ChatPanel.running`), `running_stages()` (workers only), `upstream_running(stage)` (stages 5-8 only), `watch_runs` (0.25 s poll calling the screen's `runs_changed`). `goto_stage` keeps a working screen instead of removing it; `switch_to` drops all kept screens after `cancel_all`. The rail is clickable: `row()` in `StatusHeader.refresh_rail` wraps each row in `[@click=app.stage(n)]` / `[@click=app.rail(name)]`, handled by `action_stage`/`action_rail`; `DESTINATIONS` rows are (label, key, action). `RUNNING = "▶"` marks a running stage
- Chat (006): `ChatInput` (a `TextArea`, 1 to 6 rows, Enter submits, `ctrl+j` newline, priority F6/F7 forwarded to the screen's `action_undo/redo`, or on Tuning the app's notice undo), `ThinkingLine` (`#thinking`, last child of `#messages`, never saved), `-gap` class set by `ChatPanel.add` on a `FoldLine` that does not follow another tool line
- Search (006): `SearchScreen` has class `-first` until `candidates.jsonl` exists (centred run block, results hidden); `Rows` `Static`s draw the band and seed grids from the panel width (`band_rows`/`seed_rows`). Check store: `pg.report` (summary) and `pg.details`, `#pg-details` toggle; S3 `new_project.check_index` has no Details
- `src/hunches/theme.py` (colours, `label_tag`/`label_text`, the TextArea theme) and `src/hunches/hunches.tcss` (shared look); `screens/report.py` renders the metrics and disagreement tables shared by stages 5 and 6
- `tests/` — mirrors the modules; one Pilot smoke test per screen
- `examples/` — tiny sample project
- `specs/` — specs and task files

## TUI look

Visual design comes from a design handoff (dark theme, panels, stage stepper); `theme.py` and `hunches.tcss` implement it. Rules to keep:

- Every screen must work at 80×24; bigger terminals only grow the `1fr` regions. From 100 columns `StatusHeader` becomes a 26-column left rail (`app.rail` / `wide(app)`); below that it is one row on top. `tests/test_sizes.py` sweeps every screen and modal at 80×24, 100×30 and 120×36 (no clipped widget outside scroll areas); add new screens and modals there.
- Panels are borderless: `panel(widget, title, subtitle)` adds a one-row `PanelTitle` (change it with `retitle()`), `modal_box()` does the same for dialogs. One focus bar: only the focused panel gets the primary left bar (`.panel`, or `.-focused` for a region that has no focusable widget). App CSS beats `DEFAULT_CSS`, so shared look goes in `hunches.tcss` and per-screen layout in `DEFAULT_CSS`. No round or boxed borders.
- Every key has a button and every button shows its key: build them with `key_button(label, key)` ("Approve seeds  F2"); `AppFooter` drops the keys the rail already shows. One-line messages go through `say()` (hidden when empty). Run screens: `x` stops, `s` starts/resumes; `ctrl+s` saves an editor, `e` edits, `o` edits the prompt and `c` toggles Chat/Results on Tuning.
- Never colour alone: pair it with a word or glyph (PASS, FAIL, STALE, DIFFERS, ■ label).
- Labels render as `label_tag(...)` in Static markup and `label_text(...)` in DataTable cells (DataTable strings use Rich markup, Static uses Textual markup). Cost is `$0.0000`, unknown is `cost ?`.
- Spacing and subheads: `.subhead` (bold, one level under a `PanelTitle`) and `.indent` are in `hunches.tcss`; New project shows a `#title` row ("New project") beside the rail's `hunches` line from 100 columns. Every section gap on a screen is one blank row from a single rule, not per-panel margins
- Pointer: `hunches.tcss` sets `pointer: pointer` on `FoldLine`, `Tab`, `OptionList`, `DirTree` and the `DataTable`s that react to a row click; Textual's Button, Select, Input and TextArea set their own. The rail sets `styles.pointer` in `StatusHeader.on_mouse_move` from the `@click` meta of the cell under the mouse. There is no setting or fallback
- DataTable has no flex column: give the Text column a fixed width and resize it after layout (`report.fit_text_column`).

## Testing notes

- Textual: drive with `async with app.run_test() as pilot:`; `await pilot.pause()` before assertions that depend on a message being processed; default terminal is 80×24, pass `size=` when needed.
- Metrics tests compare against hand-computed values written in the test; never derive expected values by running the code under test.
- Use `tmp_path` and `monkeypatch.chdir` for `.hunches/` fixtures.
- "No model call" is proved by counting `FunctionModel` invocations (see `CALLS` in `tests/test_e2e.py`: labelling makes none, the first Tuning run makes one per dev item). `tests/conftest.py` has an autouse `no_real_models` guard that fails any un-stubbed model request, and stubs for the assistant turns screens send on mount (`stub_taxonomy_assistant`, `quiet_tune_assistant`) and an autouse `quiet_descriptions` that stubs `HunchesApp.check_descriptions`, so tests that open a config without descriptions do not get the popup; mark a test `@pytest.mark.descriptions` to turn the popup back on (`tests/test_descriptions_popup.py`). Chat tests drive `#chat-input` (a `TextArea`): set `.text`, post `ChatInput.Submitted` or press `enter`; post `events.Paste` to the app, not the box.
- Pilot clicks on a button inside a panel that is not focused may need `offset=(2, 0)`. Importing any `hunches.screens.*` module on its own works (`screens/__init__.py` loads `hunches.app` first).

## Conventions

- Match surrounding code style; comments only where the why isn't obvious.
- One commit per task, descriptive message. Develop on the branch you were assigned; do not open a PR unless asked.
- Don't tag, release or publish. The user pushes tags; PyPI uses trusted publishing (no token in secrets).

## Needs a human (stop and report, don't fake)

For 006: pointer shape, the `▶` and spinner glyphs, `ctrl+j`, clicks in Chris's terminals, a real-model pass on the seed assistant, a look at the Search first-run block and results grids, the descriptions popup and the New project title row, and the `hunches[local]` install size (the list under "Current state"). API keys, a real embedded corpus, AWS credentials, PyPI trusted-publisher setup, the GitHub `pypi` environment, the `v0.1.0` tag, and (if you can't verify it from AWS docs) the S3 Vectors `topK` maximum. For 005: a PostgreSQL with the pgvector extension, every managed service (RDS, Aurora, Supabase, each with and without its pooler), RDS/Aurora IAM authentication against a real instance, TLS, and tables larger than memory; the steps are `specs/005-pgvector/manual-checklist.md`. Never fake these or put a database URL, password or IAM token in a file. Full list: `specs/001-initial-version/tasks/README.md`.
