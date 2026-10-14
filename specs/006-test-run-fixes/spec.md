# 006 — Fixes and improvements from the first real test run

Status: **ready to implement** (decisions Q1–Q7 resolved 2026-10-14; tasks 01–13 written in `tasks/`). Source: Chris's notes from a test run (`Hunches_notes_braindump.pdf`, 11 items with screenshots), checked against the code on branch `claude/funny-ritchie-args3k` (Textual 8.2.8 installed). Builds on `../001-initial-version/spec.md` to `../005-pgvector/spec.md`. Where this spec disagrees with them, this spec wins once it is implemented; the places are listed under "Behaviour that changes in 001–005".

**Read order for an implementer:** this spec → your task file (`tasks/NN-….md`, to be written) → the code named in the section.

## What this is, in one paragraph

A first real run (PostgreSQL/pgvector store, a brief about public-execution discourse) turned up a mix of layout rough edges, one packaging change, and three things that affect result quality or workflow: the assistant knows nothing about the project or the store, it writes seed phrases that describe a concept instead of sounding like the corpus, and it cannot change or delete seeds that already exist. This spec groups the 11 notes into six themes (A–F), records what the code does today for each, and says what must be true afterwards. It adds no new stage and no new file format beyond two `config.toml` fields.

## Principles

Same as 001–005: minimal implementation (no abstraction, base class, registry or plugin system; a plain `if` where two behaviours coexist), plain files in `.hunches/` are the only state, every Textual and Pydantic AI API checked against the installed version and current docs, no real LLM or AWS call in tests, unknown cost is `?`, never colour alone. Additional rules here:

- **Every screen still works at 80×24**, and `tests/test_sizes.py` still sweeps every screen and modal at 80×24, 100×30 and 120×36. New widgets are added there.
- **The assistant gets no ability a human lacks, and no more.** Item 9 gives it add, delete and replace on seeds, which the user already has (D7 in 004 still holds for gold: the assistant never sets a label).
- **Nothing here may stop a run the user did not ask to stop.** See theme F.

## Resolved decisions

| # | Question | Decision | Who / when |
|---|----------|----------|------------|
| Q1 | Item 1: "in the same coor as the 'hunches' text" | Same **row** (the content area cannot share a column with the left rail). | Chris, 2026-10-14 |
| Q2 | Item 2: the `local` extra pulls in `sentence-transformers` (and with it PyTorch), a very large install that is skipped on Python 3.14 (`python_version < '3.14'` marker) | **Keep `local` as an extra** (reversed after measuring: folding it in grew `.venv` from 240 MB to 5.7 GB, 3.2 GB of it nvidia CUDA wheels, 1.1 GB torch, 894 MB triton). `boto3` and `psycopg[binary]` move into the base install; `s3`, `pg`, `rds` are removed. The README says `hunches[local]` is large. | Chris, 2026-10-14 |
| Q3 | Item 5: what is "the store" for a local corpus folder? | The field is called "store description" everywhere; the form hint says "what the items are, where they came from, language and format", for all three backends. | Chris, 2026-10-14 |
| Q4 | Item 5: existing projects have no descriptions | **Not a blocker** for opening or using the project, but a **popup requires the user to enter both descriptions** for any project that is missing one (see item 5). | Chris, 2026-10-14 |
| Q5 | Item 6: newline in a growing chat box | Enter sends; `ctrl+j` inserts a newline (pasted newlines are kept as they are). | Chris, 2026-10-14 |
| Q6 | Item 11: switching to a different project | Opening the Projects list never stops anything; choosing another project keeps the existing "A run is in progress; stop it and switch?" confirm (the working directory is process-global and `switch_to` calls `workers.cancel_all()`). | Chris, 2026-10-14 |
| Q7 | Item 10: the design of the Search results | **Follow the existing design handoff** (`../004-history-and-redo/design/design_handoff_hunches_tui/reference/ui_kits/tui-rail/Search.jsx`, 003 `README.md` §2 Search), with the two overrides in item 10. | Chris, 2026-10-14; read and applied by Claude |

## Where things stand today (verified in code)

- `NewProjectScreen` (`screens/new_project.py`) composes three `panel(...)`s: location, corpus, models. The models panel is two `Static`s (`#models`, `#models-rest`) separated by a `Rule()`; the Rule is the line Chris wants gone. The first row of the content area is the `location` panel title; nothing in the content area names the screen. The one-row header (`StatusHeader`) names it below 100 columns.
- `pyproject.toml` has extras `s3` (`boto3`), `pg` (`psycopg[binary]`), `rds` (`psycopg[binary]`, `boto3`) and `local` (`pydantic-ai-slim[sentence-transformers]`). The base dependencies already include `pydantic-ai-slim[anthropic,openai]`; `keys.provider_var` knows only those two LLM providers, so "providers" in Chris's note means the **backends** (S3, pgvector, RDS IAM, local embeddings). `search.py` imports `boto3`/`psycopg` lazily and raises `ImportError("… pip install hunches[pg]")` in four places (lines 75, 143, 185, 534); two tests assert that exact text (`tests/test_search_pg_connect.py:116,247`). README lines 10–14 and 127, `AGENTS.md` (Stack, Commands), `.github/workflows/{ci,publish}.yml` (`uv sync --all-extras`) mention the extras.
- Textual's `Button`, `Select` and `Input` already set `pointer:` in their own CSS (`pointer: pointer`, `pointer: text`, `pointer: not-allowed` for disabled). Nothing in `src/hunches/` sets `pointer`. Custom clickable things (rail rows, `FoldLine`, seed rows, `DataTable` rows, the model picker lists) get the default arrow.
- Check store (`screens/pg.py:report`, `new_project.check_index` for S3) prints every fact it found, one per line (version/schema/encryption, column type/dimension, row estimate, each index, a sample row, then warnings and notes). On success that is 5–7 lines of mixed colour.
- `NewProjectScreen`/`ProjectSettingsScreen` have no description fields. `Config` (`files.py:23`) has no description fields. All assistants get their context through one function, `files.assistant_context()` (used at `brief.py:133`, `taxonomy.py:439`, `tune.py:491,1109,1170`); `tune.py:86` hashes it to decide when to send an UPDATED context message (D9 in 004: that is a model call).
- `ChatPanel` (`app.py:537`) is a one-row `Input` (`#chat-input`, `#chat-row { height: 1 }`) plus a send button. While a turn runs the input is disabled and nothing else shows until the first streamed text or tool line appears. `.fold-tool { margin-top: 0 }` and `.turn.first { margin-top: 0 }` make a tool line sit directly under the previous line.
- Brief's agent (`screens/brief.py`) has one tool, `propose_seeds`, which only appends (`add_seeds`). Its instructions tell it seeds are "statements that would be true of a matching item (e.g. "The author describes being laid off")", which is the origin of the "The item discusses …" phrasing in the screenshot. They also already say "Ask short follow-up questions until the brief is clear", which the model did not follow in the test run. The seed list in its prompt is numbered `1. …` from `self.seeds`, re-read on every run.
- Humans can add (`a`), edit (`e`) and delete (`d`) seeds in `BriefScreen`; all writes go through `history.save("seeds", …)` (004), so each is undoable.
- `SearchScreen` (`screens/search.py`) always shows the `Run search` button in the top row and always mounts the results panels (`#bands` and `#seeds` as two `Static`s of padded text, with zero counts and the placeholder "Run the search to see…" before a run). It marks `#results` `-inactive` when seeds are not approved or no candidates exist; it shows the last run from `candidates.jsonl` on mount.
- The left rail is **one `Static`** (`StatusHeader.refresh_rail`) rendered from markup, so its rows are not widgets and cannot be clicked. Navigation is keys only: `n`/`p` (`action_goto`), F3/F4/F5/F8/F9. `HunchesApp.goto_stage` uses `switch_screen`, which **removes** the old screen; Textual cancels a removed widget's workers (`Widget.remove` → `workers.cancel_node`; `App._replace_screen` only keeps a screen that is installed or in another mode's stack — checked in Textual 8.2.8 source). So pressing `n` while Search, Tuning, the Test run, the Threshold sample or the Full run is working cancels it. Overlay screens pushed on top (Projects, Project settings, System settings, History, Redo plan) leave the screen below alive, so those already do not cancel anything; `open_project` → `switch_to` is the only place that deliberately calls `workers.cancel_all()`, after a confirm.

## A. Layout and look

### 1. Project setup layout (note "Project setup layout")

On `NewProjectScreen` (and wherever the same panels are reused):

- A title row **"New project"** at the top of the content area, on the same row as the `hunches` line in the left rail, styled like it (bold, `$primary`). Below 100 columns the one-row header already names the screen; no extra row is added there (confirm against `StatusHeader.refresh_cost`).
- The `Rule()` between the two model blocks is removed. The `models` panel has two subheads, **assistant** and **classifier** (bold, like a `PanelTitle` one level down), each followed by its model line with the price label. `thinking: …` belongs under assistant. The line "pinned for this project; change later in Project settings" stays, once, at the bottom of the panel.
- **Equal spacing:** the same vertical gap (one blank row) between every section on the screen: the new "about" panel from item 5, location, corpus and models. Today location→corpus is 0 rows and corpus→models is 1. The gap is a single rule in `hunches.tcss` or the screen's `DEFAULT_CSS`, not per-panel margins.
- Must still fit and scroll at 80×24; Create and its message stay outside the scroll area as today.

### 3. Mouse pointer (note "Cursor: pointer")

Textual's `pointer` style (docs: https://textual.textualize.io/styles/pointer/; values https://textual.textualize.io/css_types/pointer/) sets the terminal's mouse pointer shape on hover. It relies on the Kitty pointer-shapes protocol (OSC 22), so terminals without it show no change.

- Anything the user can click that is not a `Button`/`Select`/`Input` gets `pointer: pointer`: the new rail rows (item 11), `FoldLine` (it toggles on click), `SeedRow`/list rows that respond to a click, model-picker and project-list rows, History entries. Disabled things get `not-allowed` (Textual's buttons already do).
- Done once in `hunches.tcss` where the shared look lives, using class selectors, not per-widget `DEFAULT_CSS`.
- No code, no setting and no fallback for unsupported terminals. Terminal support is recorded below as a human check; per Ghostty's OSC 22 table the protocol is supported by Kitty (0.31+), Ghostty (1.0+), Foot and recent iTerm2/xterm, and not by VTE or Alacritty (https://ghostty.org/docs/vt/osc/22, https://sw.kovidgoyal.net/kitty/pointer-shapes/). Chris's screenshots look like macOS Terminal; **whether it shows the pointer change there is not established** and is a "Needs a human" item.

### 4. Connection test success (note "Connection test success")

Applies to Check store for pgvector (`pg.report`) and S3 (`new_project.check_index`, shown in both New project and Project settings).

- **Success** (no error, no warning) is one green line: `✓ Connected` followed by the two or three facts the user needs, in muted text on the same line. pgvector: `pgvector 0.8.0 · vector(1536) · ~30,576,342 rows`. S3: `dimension 1536 · cosine`. The word "Connected" carries the meaning; green and ✓ only add (never colour alone).
- **Warnings and errors** keep their current text and colour, one per line, in order, **above** the summary line when the connection itself worked (`⚠ WARNING: …` stays the word "WARNING"). An error means no ✓ line.
- Facts that are normal and only add noise are not shown by default: schema, "encrypted", each index line, the sample row, "No index: the search scans the whole table", the pooler hint. Where one of them is something the user should act on (not encrypted, no index while `pg_search = "index"`, a pooler URL), it is already a `warning` or becomes one; the task lists each `notes`/`warnings` entry in `search.check_store` and decides keep, demote or show-as-warning in a table in the task file. The sample row stays available (it proves the text column is right): shown only when the user presses a "Details" toggle on the result, which reveals the old multi-line report.
- `search.check_store` and its return dict do not change; only `pg.report` and the S3 formatter do.

### 7. Typing/thinking indicator (note "Typing/thinking indicator")

While the assistant is working, show it. In `ChatPanel`:

- A one-row indicator in the message list (a spinner glyph and the words "thinking…" or the tool name, e.g. `⠋ thinking…`), muted colour, animated with `set_interval`, shown from the moment a turn starts until the first text delta, **again** after a tool result until the next text or tool call, and hidden when the turn ends or fails. It is not shown while text is streaming (the text itself is the indication) or while a tool line is in its running state (the tool line is).
- It lives in the existing `#messages` scroll area below the live line so `anchor()` keeps it visible. It is not saved in `chat/<stage>.json` and does not enter the model's message history.
- No model call, no new dependency. Tests: with a `FunctionModel` that waits on an `asyncio.Event`, the indicator exists while the turn is blocked and is gone after the turn finishes.

### 8. Spacing in chat (note "Spacing issue in chat")

A tool line (`FoldLine`, e.g. `propose_seeds Added 10 seeds.`) directly after a user turn or an assistant text turn gets one blank row above it. Consecutive tool lines stay tight (no blank row between them). Implement with CSS on `.fold-tool` by what precedes it, not by changing message order. Applies to every `ChatPanel` (Brief, Taxonomy, Tuning).

### 10. Search run UI (note "Search run UI")

Q7: the layout follows the existing design handoff (`../004-history-and-redo/design/design_handoff_hunches_tui/reference/ui_kits/tui-rail/Search.jsx` and the Search section of `../003-tui-redesign/design/README.md`), which already specifies the results panels; nothing new is invented. What the handoff already says and stays: the top row (primary `Run search  r` / `Rerun search  r` button, status text, per-seed progress bar to its right while searching), the two panels **Candidates by similarity** (subtitle: the total) and **Top seeds** (subtitle: the "similarity at or above ▼" select), the rerun confirm, the stale and gold-orphan notices. Two things change, both from Chris's note:

1. **Before the first search, only the Run block is shown, centred** (the handoff showed dimmed empty panels; that goes). 2. **The results are laid out as the handoff's grids** (the current `Static` text pads the bars to a fixed 30 cells and puts the count right beside them, which is what reads as rough).

| State | Page shows |
|-------|-----------|
| Never run (no `candidates.jsonl`), seeds not approved | Centred block: the disabled `Run search  r` button with "Seeds are not approved yet." beneath. No panels. |
| Never run, seeds approved | Centred block: the `Run search  r` button. No panels. |
| First run in progress | Centred block with the progress (the 003 `RunIndicator` pattern: title "Searching…", the `LabelBar` `4/12  <seed>` or, for the pgvector exact one-query mode, the elapsed/rows line, and Stop where it exists today). Reuse `RunIndicator` from `screens/progress.py` if its API fits; do not add a second progress widget. No panels. |
| First run failed or stopped | The centred block again, with the error ("Search failed: …" and the "Fix:" line) or "Search stopped." beneath. |
| Has results (also on opening a project that already has `candidates.jsonl`) | The handoff layout: top row, notices, both panels. Rerun in progress keeps the handoff's top-row progress bar and dimmed panels, as today. Stale results (seeds or embedding model changed) show normally with the existing banners. |

**Panel contents (from the handoff, measured in cells):**

- **Candidates by similarity:** a muted header row `Similarity · · · Candidates`, then one row per band: label column 11 wide (strong colour), a bar column that takes the remaining width (the bar is scaled to the largest band and capped at 40 cells so it never runs to the far edge on a wide terminal), and a count column 11 wide, right-aligned, bold, thousands separators, faint (not bold) when the count is 0. Columns are separated by 2 cells. The panel subtitle is `N candidates`.
- **Top seeds:** rows of rank (3 wide, right-aligned, faint), count (7 wide, right-aligned, bold, separators), bar (12 cells, primary colour; the first row's bar is `$accent`, the teal), then the seed text filling the rest and truncated with `…`. The select in the subtitle recomputes counts from `candidates.jsonl` as today (`candidates.top_seeds`).
- Counts are right-aligned and bars start at a fixed column, so rows line up in both panels at 80×24 and at 120×36. One blank row between the two panels (item 1's gap).
- Textual has no `grid` for `Static` text, so the task may use a `DataTable` per `AGENTS.md` ("DataTable has no flex column: give the Text column a fixed width and resize it after layout, `report.fit_text_column`"), per-row `Horizontal`s, or a `Static` that builds its padding from the panel's width on resize. Pick the smallest that keeps the widths above; the existing `bar()` helper in `screens/search.py` is reused.
- `tests/test_sizes.py` gets the never-run state and the has-results state; the hidden-panels state is asserted (`display` is false), not just their absence on screen.


## B. Packaging

### 2. Provider extras (note "Provider extras")

- Move `boto3` and `psycopg[binary]` into `[project] dependencies`, delete the `s3`, `pg` and `rds` extras and keep `local = ["pydantic-ai-slim[sentence-transformers]"]` (Q2; that extra is `python_version < '3.14'` in `pydantic-ai-slim`'s metadata, so Python 3.14 installs do not get local embeddings). The comment above the dependency list in `pyproject.toml` is updated. The README says `hunches[local]` is large (about 5.5 GB with CUDA wheels on Linux) and unavailable on Python 3.14.
- Imports in `search.py` may stay lazy (cheap startup) but the "pip install hunches[…]" `ImportError` messages go (the package is always installed with them). The two tests that assert the old text change with them. If `psycopg` or `boto3` is somehow missing the plain `ImportError` surfaces.
- README (Install section and the RDS/Aurora paragraph), `AGENTS.md` (Stack, Commands: `uv sync --extra local` replaces `uv sync --all-extras`), `.github/workflows/ci.yml`, `publish.yml` and the pgvector CI job follow. `specs/005-pgvector` text that names the extras is left as history; its "Clarifications" are not rewritten.
- `rds` existed to avoid forcing boto3 on pgvector-only users; that trade-off is the point of this change and needs no replacement.
- Test: a fresh `uv sync` (no extras) can `import boto3, psycopg` and run `pytest -m "not ui"`; CI uses `uv sync --extra local`.

## C. Assistant context

### 5. Project and store descriptions (note "Additional assistant context")

- `Config` gets two optional strings, `project_description` and `store_description`, written to `.hunches/config.toml` when non-empty (like the other optional fields; plain text, committed with the project, never anything secret).
- **New project:** a new top panel **"about"** (before location) with two multi-line text areas, "project" (what this project is trying to find out, and why) and "store" (what is in the corpus: what an item is, where it came from, language, format, anything that affects how an item is worded). Both are **required**: Create stays disabled and the existing hint reads `Required: project description, store description` (the hint already lists missing fields). Whitespace-only counts as empty. There is no minimum length.
- **Project settings (F3):** both are editable there, saved with the other settings.
- **Assistants:** `files.assistant_context()` begins with a `# Project` block and a `# Store` block (the text as written, or "not provided" for an old project), so Brief, Taxonomy and Tuning all receive it (they already all call it). Editing a description must **not** trigger the Tuning UPDATED context reply (`tune.py:86` hashes `assistant_context()`; hash only the pipeline status and gold coverage text, i.e. what it hashes today).
- **Missing descriptions popup (Q4).** Opening a project never fails because a description is missing, but as soon as the project's first stage screen is showing (after `goto_stage` in `switch_to`, so after any startup modal and the outside-edit check), if either description is empty or whitespace-only a modal `DescriptionsScreen` opens: title "Describe this project", the same two text areas and hints as New project, pre-filled with whichever one exists, and **Save  F2**, disabled until both are non-empty. It cannot be dismissed any other way (no Esc, no close): the user is required to fill it in. A **Quit  q** button is the only other exit (Textual's `ctrl+q` also quits; `q` as a plain key must not fire while a text area has focus, so the button and `ctrl+q` are what is tested). Save writes `config.toml` through `files.write_config` and the assistants see the text from then on. It is shown once per project open, not on every stage change. It is listed in `tests/test_sizes.py` at all three sizes.
- Because the popup would block every Pilot test that opens a project (about 28 test files build configs without descriptions), `tests/conftest.py` gets an autouse stub for the popup check, following the existing `quiet_tune_assistant` pattern, with a `descriptions` marker that turns it back on for the popup's own tests. `examples/` gets descriptions.
- **Project settings** also refuse to save an empty description (the same guard), otherwise the popup would come straight back.
- Optional, not required: saved S3 stores (`system.add_store`) remember a store description to pre-fill other projects on the same store. Left out of this spec unless Chris wants it.
- Tests: Create disabled until both are filled; `config.toml` round-trips both; the text appears in the instructions the Brief agent is given (inspect `agent` instructions with a `FunctionModel`, no real model call); old `config.toml` without the fields loads.

## D. Chat input

### 6. Chat input grows (note "Chat input box height")

- Replace the one-row `Input` in `ChatPanel` with a `TextArea` (or a compact equivalent) that starts at one row and grows with its content up to a maximum (six rows, never more than about a third of the panel), then scrolls inside itself. The send button stays on the first row of the box.
- Enter sends; the newline key is per Q5. Empty or whitespace-only text is not sent (as today). The box is cleared on send and disabled while a turn runs (as today).
- **Known trap:** Textual's `TextArea` binds F6 and F7 itself (select line / select all), and Brief, Taxonomy and the Tuning prompt use F6/F7 for undo/redo (004). The chat's `TextArea` must not take those keys: declare priority overrides the same way the Tuning prompt modal does (`screens/tune.py`).
- `Input`-based tests and code that read `#chat-input` (`test_chat.py`, `test_brief.py`, `test_app.py`, `test_taxonomy_screen.py`, `test_tune_screen.py`, `test_e2e.py`, `test_history_screens.py`) change with it; `ChatPanel.submit/send/sync_send` keep their names and behaviour. Add the box at its maximum height to `tests/test_sizes.py`.

## E. Seed assistant

### 9. Better seeds, and edit/delete tools (note "Assistant prompt improvements")

**Prompt (`brief.INSTRUCTIONS`):**

- Seeds are written **the way someone would write them in this corpus**, in that voice and register (a post, a comment, a headline, a case note, whatever the store description says the items are), not as descriptions of the concept. Today's example, "The author describes being laid off", is the wrong model and is replaced; examples in the prompt are generic about the *form*, and the assistant takes the *content* from the user's brief. The old examples ("The item discusses …") must not appear anywhere in the prompt.
- The assistant uses the project and store descriptions (item 5) to choose voice and vocabulary.
- **Ask before generating:** on a first request with no seeds yet, the assistant asks the user two to four short questions (what counts as a match and what does not, the voice or places the text would appear, the sort of phrases to avoid) and calls `propose_seeds` only after the user has answered, unless the user explicitly says to go ahead. This is prompt text; it cannot be proved by a test with a stub model, so the test only asserts the rule is in the instructions. The first real-model check is in "Needs a human".
- Several phrasings of the same idea are fine and expected (they are different queries); duplicates of existing seeds are not.

**Tools:** the assistant can do what the user can on the seed list: add, replace in place, delete.

| Tool | Does |
|------|------|
| `propose_seeds(seeds)` | unchanged: append |
| `replace_seed(number, was, text)` | replace seed `number` (1-based, as in the numbered `# Current seeds` list) with `text`; refuses with a clear message if the current seed at that number is not exactly `was` (the list may have changed since the assistant last saw it) |
| `delete_seeds(numbers)` | delete those seeds; numbers refer to the list as it was when the call started (applied together, highest first) and out-of-range numbers are an error that changes nothing |

- All three write through `BriefScreen.save(…)` → `history.save("seeds", …)` with `source="assistant"` and the turn's `group` (one undo reverses everything the turn did), and update the on-screen list. The `# Pipeline status` consequences (candidates stale after a seeds change) are the 004 machinery and need nothing new.
- A tool refuses with "The user is editing a seed; try again after they save or discard" while `BriefScreen.editor` is open (the human's in-progress edit is not overwritten).
- No confirm dialog: a human delete has none, and undo (F6) restores. The tool result names what changed ("Replaced seed 3", "Deleted seeds 2, 5") so the chat shows it.
- Tests (stub models): each tool's effect on `seeds.csv` and the history log (`source == "assistant"`, shared `group`), `was` mismatch changes nothing, out-of-range number changes nothing, refusal while the editor is open, one F6 undoes a whole turn's changes.

## F. Navigation

### 11. Navigate by clicking the rail; never stop a run for it (note "Navigation between stages")

**Requirements**

1. Every row in the left rail is clickable and does exactly what its key does: the nine stages (`goto_stage`), Projects (F4), Project settings (F3), System settings (F5), History (F8) and, when shown, Redo plan (F9). Clicking the current stage or the current overlay does nothing; clicking a row that its key could not open (History while an editor draft is open, a modal on top) is ignored the same way. Rail rows get `pointer: pointer` (item 3). Below 100 columns the one-row header has no rows, so keys are the only route there, as today.
2. **No run is stopped by navigation.** Leaving a stage screen (by click, `n`/`p`, or a Redo plan "Go to") while it has work in flight (a search, a Tuning run, the test run, the threshold sample, the full run, and an assistant turn) keeps the work going. Opening an overlay already works that way. Returning to the stage shows the live progress. The existing Stop controls (`x`) are the only way to stop.
3. **Work that finishes while the stage is hidden** is not lost: the screen's results are in the project files, and when the user returns the screen shows them (refresh from files on resume), exactly as if it had been open.
4. **The rail shows what is running**: a stage with work in flight carries a mark and the word RUNNING in the rail legend and tooltip (a glyph that does not collide with the existing `↻` stale and `◐` incomplete marks; the glyph is chosen in the task and checked in the terminals we care about, as 004 did for `↻ ◐`). A run's cost keeps counting in the cost line as now.
5. **Downstream work does not start on top of a running upstream stage**: while stage N's run is working, Start/Run on a later stage that reads its output (everything after Search reads `candidates.jsonl`; Tuning, Test, Threshold and Run read each other's files) is disabled with the reason ("Search is running"). Reading screens (Brief, Taxonomy, Gold labelling, Browse) stay usable. An assistant turn does not block anything.
6. **Switching project** is the one exception (Q6): choosing another project from the list still goes through `open_project`'s confirm and then cancels workers, because the working directory is global. Quitting is unchanged.

**How (to be verified in task 01, not decided here):** the cause is `switch_screen` removing the old screen. A screen with a running worker has to be kept instead of removed, e.g. installing it (`App.install_screen`, which `_replace_screen` respects) while its work runs and uninstalling it when the work ends, or giving each stage its own mode. The rail's rows are one `Static`; clicks can be handled with `[@click=…]` markup in the rail text (documented in Textual's content guide: `[@click=app.bell]text[/]`) or by mapping the click's `y` to a row. Choose the smallest of these after checking the installed Textual; keep a plain dict and `if`, no registry class. A kept screen must also be dropped on `switch_to`, and re-read the files on resume (point 3).

**Tests (Pilot):** start a search with a stub embedder that waits on an `asyncio.Event`; click another stage in the rail; assert the search worker is still running, the rail shows the mark and Run on a downstream stage is disabled; release the event, click back, and assert the finished candidates are shown. The same for the full run (count `FunctionModel` calls: the run must not restart or duplicate). Clicking each destination opens the same screen its key opens. Switching project with a run going still asks first.

## Behaviour that changes in 001–005

- 002/003 (New project and Project settings): new "about" panel with two required fields on New project; models panel without a Rule and with assistant/classifier subheads; one gap between all panels. Opening a project with a missing description shows a required popup.
- 003 (Chat): one-row `Input` becomes a growing `TextArea`; thinking indicator; tool-line spacing.
- 003 (Search screen): the centred run block before the first search and for a failed first run; no results panels until a search has produced results (the handoff showed them dimmed); the results use the handoff grids.
- 003/004 (navigation): the rail is clickable, `goto_stage` no longer cancels running work; new RUNNING mark and legend entry; stages are blocked while an upstream run is working.
- 005 (pgvector Check store) and 002 (S3 Check store): the success output.
- 001/005 (packaging): the `s3`, `pg` and `rds` extras are removed (`local` stays); `ImportError` messages change.
- 001 (Brief assistant): the seed phrasing rules and the two new tools; `# Current seeds` numbering is now part of the tools' contract.

## Out of scope

- A tool for the assistant to read corpus items or run searches while writing seeds (it might help seed quality; not asked).
- Giving the Taxonomy or Tuning assistants new tools.
- Renaming "store" for local corpora.
- Any change to history, staleness, gold or the classifier.

## Needs a human

- Whether the mouse pointer actually changes in macOS Terminal.app and in the other terminals Chris uses (item 3). The spec records the support list above; it cannot be tested from the container.
- The glyph for RUNNING in the rail (item 11) renders in those terminals.
- A real-model pass on the seed assistant: it asks questions before proposing, writes corpus-voiced seeds from a description, and uses `replace_seed`/`delete_seeds` correctly (item 9). Tests cover the plumbing, not the model's judgement.
- A look at the Search results at 80×24 and 120×36 once built, against the handoff mock (`search/done`); and at the descriptions popup.

## Tasks

`tasks/README.md` has the rules and the order; one file per task (`tasks/01-packaging.md` to `tasks/13-docs.md`). Dependency order: 01 packaging; 02 descriptions; 03 popup; 04 chat input; 05 chat indicator and spacing; 06 seed assistant; 07 New project layout; 08 Check store; 09 Search run UI; 10 keep runs alive; 11 clickable rail; 12 pointer styles; 13 docs.
