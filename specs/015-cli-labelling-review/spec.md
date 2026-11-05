# Feature Specification: Start the labelling page from the command line, browse samples, review evaluations and revise gold labels

**Feature Branch**: `claude/nifty-planck-1agal4` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Read https://github.com/cmhac/goldlabel/issues/26 and build a spec for this." Issue #26, *Labelling page: start from the CLI, browse samples, review evaluations and revise gold labels*: "A tester was invited to change two gold labels. The page opened generically, he had to page through every row to find the two IDs, and he couldn't go back. Today `gl.label` is the only way to start the server, and it knows only the one sample it was called with. He also couldn't see the text while scrolling a long label list."

The issue's checklist is the scope of this spec. Its three "open decisions" are resolved below as **Decisions taken** with the smallest option; each can be overturned in `/speckit-clarify` before planning.

## Decisions taken (the issue's open decisions)

1. **Taxonomy.** Stored in the gold file itself (the user's decision, 2026-11-05). A gold dataset becomes one JSON document holding the taxonomy and the rows, instead of one JSON line per row; `gl.label` writes the taxonomy it was called with into it, and a page started from the command line reads it from there. Until `gl.label` has run, the taxonomy is empty and the page offers only the labels already used in that dataset's rows and says so. `clf.evaluate` does not write it. The command line takes no Python import path or taxonomy file.
2. **Running server.** One lock file per storage folder holds the running server's process id, port and start time. A lock whose process is gone, or whose port does not answer, is stale and is replaced. This lock replaces the per-gold-file `.lock` of 012-014.
3. **Revision record.** On the gold row itself (the user's decision, 2026-11-05). When the page changes a row that already had labels, the row gets a `revisions` entry holding the time of the change and the previous labels, note and `labelled_by`. There is no separate log. An evaluation is **stale** when any row of its sample has a revision entry newer than the evaluation's own time, so a first label never makes one stale.

## Where things are today

- `gl.label(sample, taxonomy)` is the only way to start the server. It serves one pass over one sample, can only advance through rows that were pending (or, with `force_open_ui=True`, every row once, in file order), and has no way to open a given row.
- A second `gl.label` on the same gold file raises "already being labelled". The lock is per gold file, so two datasets can be labelled at once but nothing shows more than one of them.
- The page shows the pass's text on the left and the controls on the right. From 1024px the controls card is sticky, but it is not scrollable on its own: with many labels the text and the later labels cannot be on screen together.
- `evals.jsonl` records each evaluation's metrics, prompt digest, rows digest, taxonomy and sample names, but not which rows the classifier got wrong. The disagreements exist only on the `Evaluation` object returned to the notebook.
- A revised gold row is overwritten in place (`labels`, `labelled_at`, `note`). Nothing records what it said before. A row first labelled by `Gold.import_rows` and later revised in the page loses `labelled_by: "imported"` with no trace.

## Clarifications

### Session 2026-11-05

- Q: When a page is already running and a notebook calls `gl.label`, does the cell return at once or wait? → A: It waits until no row of the pass is still pending (or the user interrupts), then returns the Sample, so the notebook flow of 012-014 is unchanged. With `force_open_ui=True` there is nothing pending to wait for, so it prints the URL and returns at once.

- Q: Where is a revision recorded, and how is an evaluation flagged stale? → A: The user's decision: on the gold row, as a `revisions` list of entries with the time and the previous values (no `revisions.jsonl`, no digest comparison). An evaluation is stale when a row of its sample has a revision newer than the evaluation's time; a first label is not a revision, so it does not make one stale.

- Q: Where do the label options come from for a page started from the terminal? → A: The user's decision: not a separate snapshot file; the gold file itself changes from one JSON line per row to a single JSON document holding the taxonomy and the rows, and `gl.label` writes the taxonomy into it. Files in the 014 format are not read and not migrated (early alpha, as 014 decided).

- Q: Where is the page's access token kept? → A: The user's decision: there is no token. The Host check stays, and writes need a fixed custom header (FR-027) so another web page cannot post to the port.

- Q: If a notebook cell is waiting on a running page and the user presses **Done** with rows still pending, does it keep waiting? → A: No. It returns when no row of the pass is pending or **Done** is pressed on that pass, whichever comes first.

Run `/speckit-clarify` again to overturn any of the three decisions above.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open the page from a terminal and change two labels by id (Priority: P1)

A colleague is told "labels for rows `a17` and `b203` in the trump dataset are wrong". They run `goldlabel label trump` in the project folder. The page opens on that dataset, listing its samples with row counts and how many rows are labelled. They open the sample, type `a17` into **Jump to id**, change the label, add a note, save, go back to where they were, jump to `b203`, change it, and close the page. Each change is saved at once and recorded on the row.

**Why this priority**: it is the case that prompted the issue, and everything else in the page builds on a page that can open on any row of any dataset without a notebook.

**Independent Test**: build a storage folder with a gold file of two samples, run the command with a fake browser, and over HTTP list datasets and samples, open a row by id, post a revised label and note, read the gold file, and use back to return to the previous row.

**Acceptance Scenarios**:

1. **Given** a storage folder with `gold.json` and `gold-corpus-b.json`, **When** the user runs `goldlabel label` (no name), **Then** the page lists both datasets, each with its samples, their row counts and labelled counts, and does not open any row.
2. **Given** the same folder, **When** the user runs `goldlabel label corpus-b`, **Then** the page opens on that dataset; a name that matches no file prints the datasets that exist and exits non-zero without starting a server.
3. **Given** a labelled row `a17`, **When** the user opens it by id and saves a different label, **Then** the gold file holds the new label stamped `labelled_by: "goldlabel-ui"` with a new `labelled_at`, and the row gains one `revisions` entry holding the time and the previous labels, note and `labelled_by`.
4. **Given** an id that is not in the dataset, **When** the user submits it in **Jump to id**, **Then** the page says so and stays where it was.
5. **Given** the user opened row `a17`, then jumped to `b203`, **When** they press Back, **Then** they are on `a17` with their place in the sample list unchanged, and Back again returns to the row before it, one step each, down to the first row they opened.
6. **Given** `--dir PATH`, **When** the command runs, **Then** it serves `PATH`; without it, `GOLDLABEL_DIR`, then `.goldlabel/`, as every other function resolves the storage folder.

---

### User Story 2 - `gl.label` joins a server that is already running (Priority: P1)

A notebook user has the page open from the terminal, then runs `gl.label(dev, taxonomy)`. No second server starts. The cell prints the running server's URL, pointed at the dev sample's pending rows, and waits until none of those rows is pending any more or the user presses **Done** on that pass (or interrupts the cell), then returns the Sample. If nothing is running, `gl.label` behaves as in 012-014 (it opens a page and waits for **Done**).

**Why this priority**: today a second labelling call fails with an error; with one server per folder it must instead lead the user to the page they already have.

**Independent Test**: with a server running for a storage folder (started by the library, so no process is needed), call `label` for another sample and check that the number of listening servers has not changed, the printed URL is the running server's, and the call waits while a row of the pass is pending and returns once none is, or once Done is posted for the pass (drive both over the page's API in the test). Then stop the server, leave a lock for a dead process, and check that the next call replaces the lock and starts a server.

**Acceptance Scenarios**:

1. **Given** a running server for the folder, **When** `gl.label(sample, taxonomy)` runs, **Then** it prints that server's URL, starts no server, writes no gold file itself, and returns the Sample once no row of the pass is pending or **Done** is pressed on it; interrupting the cell stops the wait and changes nothing.
2. **Given** that call, **When** the page is opened from the printed URL, **Then** it opens on the pass over the sample's rows that were pending at the call, so the labelling flow of 013-014 is unchanged.
3. **Given** a lock naming a process that no longer exists, or a port that does not answer, **When** `gl.label` or `goldlabel label` runs, **Then** the lock is replaced and a server starts.
4. **Given** two storage folders, **When** a server runs for one, **Then** the other is unaffected.
5. **Given** the taxonomy passed to `gl.label` differs from the one stored in the gold file, **When** it runs, **Then** the stored taxonomy is replaced with the new one, rows and their labels are untouched, and a running server uses it from its next request.
6. **Given** a server already running for the folder, **When** the user runs `goldlabel label [NAME]`, **Then** it prints that server's URL (on the dataset `NAME`), opens it, and exits 0 without starting another.
7. **Given** a server started by `gl.label`, **When** the user presses **Done**, **Then** the server stops as today. A server started by `goldlabel label` does not stop on **Done**: the page returns to the dataset list, any waiting `gl.label` call for that pass returns, and the server runs until the terminal process is interrupted.

---

### User Story 3 - Review an evaluation and its disagreements (Priority: P2)

For a sample, the page lists its evaluations from `evals.jsonl`, newest first: when, score against target, row count, model, prompt digest. Opening one lists the classifier's disagreements with the gold labels, each with the row's text, the gold label, the predicted label, the classifier's reasoning and the row's note. An evaluation whose sample was revised since it ran is flagged **STALE** in words, with the reason ("a row was revised after this ran"). The user can click a disagreement to open the row and revise it, and the flag appears on the list from then on.

**Why this priority**: it turns "read the disagreements" into the loop it was meant to be (spot a wrong gold label, fix it, know the number is out of date), but it needs the browse page of Story 1.

**Independent Test**: write an `evals.jsonl` by hand (with and without the new disagreement list), serve it, and check the history for a sample, the disagreements of one line, and that revising one row makes exactly the lines of that sample stale and no other.

**Acceptance Scenarios**:

1. **Given** a sample evaluated twice, **When** its history is opened, **Then** both evaluations are listed with their time, score, target and PASS/FAIL (or neither without a target), rows scored and how many were skipped as pending.
2. **Given** an evaluation that recorded its disagreements, **When** it is opened, **Then** each shows id, text, gold label at evaluation time, predicted label, reasoning, and the row's current note.
3. **Given** a disagreement whose row has since been revised, **When** it is shown, **Then** it also shows the current label ("revised since") so the reader does not mistake the old gold label for today's.
4. **Given** an evaluation line written before this feature (no disagreements stored), **When** it is opened, **Then** the page says "disagreements were not recorded by this version" and shows its metrics only.
5. **Given** a disagreement whose row has been removed from the gold file, **When** it is shown, **Then** it says the row is no longer in the file, and still shows the logged gold and predicted labels.
6. **Given** an evaluation of `dev` and a revision of a `test` row, **When** the lists are shown, **Then** the `dev` evaluation is not stale. An evaluation of `dev + test` is stale after either.
7. **Given** a pending row labelled for the first time after an evaluation ran, **When** the lists are shown, **Then** that evaluation is not stale (a first label is not a revision).
8. **Given** the same page, **Then** it has no button or key that runs an evaluation or a classification.

---

### User Story 4 - The text stays in view while scrolling a long label list (Priority: P2)

From 1024px wide, the item text and the label controls scroll independently. The text card stays in view and scrolls on its own if the text is longer than the window; the controls card is as tall as the window at most and scrolls on its own, so a label at the bottom of a 40-label list can be chosen while the text stays on screen. Below 1024px the layout is one column: the text, then the controls, in the page's ordinary scroll. The text scrolls out of view as the labels are read; nothing floats or pins on the small layout.

**Why this priority**: it fixes the second complaint in the issue and is independent of the rest, but it only matters once taxonomies are large.

**Independent Test**: fetch the served page and CSS and check the scroll containment and viewport-height limits at the 1024px rule. A person checks it in a real browser at 1280px and 390px (listed under human checks).

**Acceptance Scenarios**:

1. **Given** a taxonomy with 40 labels and a window 800px tall at 1280px wide, **When** the user scrolls the label list to its last label, **Then** the full text of a short item is still on screen.
2. **Given** an item whose text is taller than the window, **When** at 1280px, **Then** the text card scrolls on its own and the label list does not move with it.
3. **Given** 390px, **Then** the page is one column and scrolls as one page.
4. **Given** a keyboard-only user, **When** they tab into either scrolling area, **Then** it can be scrolled by keyboard and shows a visible focus outline.

---

### User Story 5 - Every revision is recorded on the row and the gold rule still holds (Priority: P1)

Every change to an already-labelled row's labels or note adds an entry to that row's `revisions` list in the gold file: the time of the change and the previous labels, note and `labelled_by`. The current values stay in the row's usual fields, so the row reads as its own record of revisions. Saving a row with nothing changed writes nothing. The first labelling of a pending row is not a revision. The labelling server remains the only writer of gold labels (and `Gold.import_rows`); no code path in the library, the command or the page writes a label from a model's output.

**Why this priority**: revising labels is safe only if the old value is kept, and the constitution's first principle depends on the server being the one writer.

**Independent Test**: revise a labelled row, a pending row, an imported row, and a note only; save one row unchanged; check the entries and that the gold file differs only in that row.

**Acceptance Scenarios**:

1. **Given** a labelled row, **When** its labels change, **Then** the new labels and the revision entry are written in the same atomic rewrite of the gold file, so there is never a changed row without its entry.
2. **Given** an imported row, **When** it is revised in the page, **Then** the gold row becomes `labelled_by: "goldlabel-ui"` and the entry keeps `imported` as the previous stamp.
3. **Given** a row saved with the same labels and the same note, **When** it is posted, **Then** no entry is added and the file is not rewritten.
4. **Given** a row revised twice, **Then** it holds two entries, oldest first, each with the values from just before its own change.
5. **Given** the page's API, **Then** no endpoint accepts a label from anything but a request that passes the page's local-origin checks (FR-027), and no endpoint returns a model's prediction as a suggestion for a label.
6. **Given** a pending row labelled for the first time, **Then** it gets no revision entry and no evaluation becomes stale because of it.

---

### Edge Cases

- No gold file in the storage folder: the command starts nothing and prints that no gold dataset was found in the folder (the path), and how to make one.
- A gold file that is not valid JSON, is in the 014 line-per-row format, or has a bad row: the page shows the dataset's error (the file and, for a bad row, its position) and the other datasets still list.
- A dataset drawn from a notebook while the page is open: the next page load shows it; the page does not poll.
- A dataset with a sample whose rows are all labelled: the sample's **Label pending** action is disabled and says "nothing pending".
- `--port` already in use: exit non-zero with the message and start nothing; a bare run picks a free port.
- Two browser tabs on one server: saves are serialized and both read the file each time, so the later save wins; both are recorded as entries.
- A stale lock found on a read-only folder: the command reports it cannot replace the lock and exits non-zero.
- A gold file with no taxonomy yet (drawn or imported, never labelled with `gl.label`): the page says the labels shown are the ones already used, and a first label for a pending row can only choose among them.
- A saved label that is not in the stored taxonomy (a row labelled under an older taxonomy): shown in the row as-is, and a revision can only choose among the stored taxonomy's labels; the page flags it as "not in this taxonomy".
- `labelled_by` of a row is something other than the three known values: the entry copies it unchanged.
- The server never listens beyond 127.0.0.1 and drops the access token of 013 (FR-027); the printed URL has no secret in it.

## Requirements *(mandatory)*

### Functional Requirements

**Command**

- **FR-001**: The package MUST have a `goldlabel label [NAME] [--dir PATH] [--port N]` subcommand next to `install`. `NAME` is a dataset name as in `gl.Gold(candidates, name=NAME)`; with none, the page opens on the list of datasets.
- **FR-002**: The storage folder MUST resolve as everywhere else: `--dir`, then `GOLDLABEL_DIR`, then `.goldlabel/`.
- **FR-003**: The command MUST print the page URL, the storage folder it serves, and the gold rule's one-line reminder, open the browser, and run until interrupted. It MUST exit non-zero and start nothing for an unknown dataset name, an empty folder, or a port in use.
- **FR-004**: The command MUST NOT take a Python import path, a taxonomy file, or any flag that sets, imports or edits a label.

**Joining a running server**

- **FR-005**: A running server MUST be discoverable by the storage folder through one lock file holding its process id, port, and start time, removed when the server stops.
- **FR-006**: `gl.label(sample, taxonomy, ...)` MUST, when a server for that folder is already running, print that server's URL aimed at the pass over the rows pending in `sample` at the call (every row of `sample` with `force_open_ui=True`), start no server, and wait until none of those rows is still pending or the user presses **Done** on that pass, whichever comes first, then return the `Sample`; an interrupt stops the wait and writes nothing. With `force_open_ui=True` there is nothing pending to wait for, so it prints the URL and returns at once. With none running it MUST behave as in 012-014.
- **FR-007**: A lock whose process is gone, or whose port does not answer a request, MUST be treated as stale and replaced. The per-gold-file lock and its "already being labelled" refusal are removed.
- **FR-008**: `gl.label` MUST get the taxonomy it was called with into the gold file: written by its own server when it starts one, or, when a server is already running, sent to that server, which writes it, so no other process rewrites a gold file while a server runs. A running server MUST read the stored taxonomy at each request. Only the labelling server writes it; `draw_sample`, `Gold.import_rows` and `clf.evaluate` keep whatever the file holds.

**Browse and navigate**

- **FR-009**: The page MUST list every gold dataset in the storage folder (the default and each named one), each with its samples, their row counts, and how many rows are labelled and pending.
- **FR-010**: A user MUST be able to open any row of any sample, labelled or pending, from a list of the sample's rows (id, labels, whether it has a note), and from **Jump to id** within the open dataset.
- **FR-011**: **Back** MUST step back through the rows the user opened in this page visit, one at a time, and leave the sample list where it was (scroll position and filter, if any). Reloading the page MUST land on the row or list the user was on.
- **FR-012**: **Label pending** on a sample MUST start the labelling pass of 013-014 over its pending rows: the same keys, the same counts for the pass only, Skip, and the finished screen. It MUST be the same code that serves `gl.label`.

**Revise**

- **FR-013**: On any row the user MUST be able to change its labels (within the stored taxonomy and its `single`/`multi` mode) and its note, with the same keyboard behaviour as 013, and the change MUST be saved at once.
- **FR-014**: The server MUST validate every revision exactly as it validates a first label (known labels, mode, body size) and MUST be the only writer of gold labels besides `Gold.import_rows`.
- **FR-015**: A revised row MUST be restamped `labelled_by: "goldlabel-ui"` with a new `labelled_at`; the gold-file format changes as FR-026 says, and no other way to set a label is added.

**Local access**

- **FR-027**: The 013 access token is removed: no token in the URL, the lock file or the served pages. The server MUST still listen only on 127.0.0.1, MUST still refuse a request whose Host is not `127.0.0.1:<port>` or `localhost:<port>` (DNS rebinding), and MUST refuse any request that changes data unless it carries a fixed custom header that only the page's own script sends. That header makes a browser send a permission check first, which the server never grants, so a web page from another site cannot post a label even though it can reach the port.

**Gold file format**

- **FR-026**: A gold dataset MUST be one JSON document in the storage folder, `gold.json` or `gold-<name>.json`, holding the dataset's taxonomy (empty until `gl.label` stores one) and its rows; each row keeps the fields of 014 plus the optional `revisions` list of FR-016. Every write MUST replace the whole file atomically, as today. Files in the 014 format (`gold*.jsonl`) MUST NOT be read, migrated or given an alias. The removed-rows file and `evals.jsonl` keep their line-per-record form.

**Revision record**

- **FR-016**: Each revision of an already-labelled row, to its labels or its note, MUST append one entry to an optional `revisions` list on that row in the gold file, holding the time of the change (`at`) and the previous `labels`, `note` and `labelled_by`. The entry and the new values MUST be written in the same rewrite of the file. A row with no revisions has no `revisions` key.
- **FR-017**: A save that changes neither labels nor note MUST add no entry and rewrite nothing. The first labelling of a pending row MUST NOT add an entry.
- **FR-018**: Entries MUST only be appended by the labelling server, never edited or removed by it; the page does not offer a way to delete one.

**Evaluations**

- **FR-019**: `evals.jsonl` lines written by `clf.evaluate`/`aevaluate` MUST also store the disagreements: for each, the row id, gold labels, predicted labels and the classifier's reasoning (not the text, which the gold file holds). Lines already in a log, and the identical-rerun rule (same sample, rows digest, prompt digest, model, metric and target), MUST NOT change.
- **FR-020**: For each sample the page MUST list the evaluations whose logged samples include it, newest first, each showing the sample names it scored (so `dev + test` reads as such), and for an opened evaluation list its disagreements as in Story 3.
- **FR-021**: The page MUST mark an evaluation **STALE** when any row of the evaluated sample has a `revisions` entry whose time is later than the evaluation's logged time, naming the reason in words. Because a revision is a change to labels or note, a note-only revision also counts; the page's reason text says which row.
- **FR-022**: The page, the server and the command MUST NOT run an evaluation, classification, estimate or any model call.

**Layout**

- **FR-023**: From 1024px, the text card and the controls card MUST each scroll on their own within the window's height, the text MUST stay in view while the controls scroll, and both scroll areas MUST be reachable and show focus by keyboard.
- **FR-024**: Below 1024px the page MUST be one column of text then controls in the ordinary page scroll, as in 013, with the one-column behaviour above documented in the page's help text.

**Agent surface**

- **FR-025**: The skills, the README and `docs/agent-instructions.md` MUST tell users to run `goldlabel label` to review or revise labels and tell agents to hand that command to the user, never to write a label. Everything that names `gold.jsonl` (the docs, skills, `AGENTS.md`, examples and their drift tests) MUST name the new file. The gold rule's canonical text MUST NOT change. The constitution (Additional Constraints: "one console command, ... there is no other command") and `AGENTS.md` MUST be amended in the same change to allow `goldlabel label` (a MINOR amendment, 1.4.0, which needs the user's approval before implementing).

### Key Entities

- **Storage folder**: the folder named by `--dir`, `GOLDLABEL_DIR` or `.goldlabel/`; holds the gold files (each with its taxonomy), `evals.jsonl` and the server lock.
- **Server lock**: process id, port and start time of the one running labelling server for a storage folder.
- **Stored taxonomy**: the taxonomy `gl.label` last wrote into a gold dataset's file; the page uses it for label options.
- **Revision entry**: an item in a gold row's `revisions` list: the time of a change and the labels, note and `labelled_by` the row had just before it.
- **Evaluation line (extended)**: an existing `evals.jsonl` line plus its disagreements; **stale** is derived from it and the rows' revision times, never stored.
- **Pass**: the rows `gl.label` or **Label pending** walks, fixed when it starts (unchanged from 013-014).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person given two row ids opens the page from a terminal and saves a new label for both without paging through any other row: 0 rows visited besides the two, and under 60 seconds from the command to the second save.
- **SC-002**: With a server running for a folder, 100% of `gl.label` calls print its URL and start no second server; with none running, 100% start one.
- **SC-003**: 100% of changes to a labelled row's labels or note add exactly one `revisions` entry with the previous values, and 0% of unchanged saves or first labels do.
- **SC-004**: An evaluation is flagged stale after exactly the revisions made to rows of its own sample after it ran, and never after a first label, a revision made before it ran, or a revision in another sample.
- **SC-005**: At 1280px with a 40-label taxonomy, the full text of a short item stays on screen while the last label is scrolled into view.
- **SC-006**: The gold-rule tests (`tests/test_gold_rule.py`, `tests/test_skills.py`, `tests/test_docs.py`) pass unchanged: no new way to set a label exists besides the page's person-triggered request.

## Assumptions

- The user runs the command from a terminal with a browser on the same machine, as with `gl.label`; running it for another machine is out of scope.
- The disagreement list is stored from this version on; older evaluation lines stay readable and show metrics only.
- Staleness compares each evaluation's logged time with the `at` of the rows' revision entries; no digest is compared. Notes never reach a model, so a note-only revision flags an evaluation that did not need it; that is accepted for simplicity.
- `gold-<name>.json` and `gold.json` are the only gold files; `*.removed.jsonl` and `*.tmp` are not datasets.
- The labelling flow, keys and counts of 013-014 are unchanged and keep their tests, except the per-file lock tests, which move to the folder lock.
- `evals.jsonl` lines written before this feature name a `.jsonl` gold file, so the page does not list them under the new file; they stay in the log.
- The page runs on the user's own computer for the user alone (the user's decision, 2026-11-05), so it has no access token; other local programs are trusted as much as the user's own files are.

## Human checks (agents report these and stop)

Open the command's page in a real browser at 1280px and 390px, light and dark, with a 40-label taxonomy; revise two rows by id with the keyboard only and use Back; open `gl.label` while it runs; read the disagreements of a real evaluation and see it go stale; run the gold-rule refusal trial with the updated skills.

## Deliberately skipped

- Running evaluations, classifications or estimates from the page (the issue says evaluations stay code-only).
- Editing the taxonomy in the page, a taxonomy file or Python import path for the command, and `clf.evaluate` writing the taxonomy.
- Adding, drawing, removing or moving rows from the page (`draw_sample` and `remove` stay in code).
- Searching by text, filters, sorting or bulk revision; only list, **Jump to id**, and **Label pending**.
- Undoing a revision from the page, or showing a row's revision entries in the page (they are in the gold file; read it with polars).
- A separate revision log, and a digest-based stale check.
- Live refresh of the page when files change, or a notifier between `gl.label` and the page.
- `--host`, `--no-browser`, and serving beyond 127.0.0.1.
- A sticky or floating text on the one-column layout, and a new layout below 1024px.
- Accounts, names for reviewers, or any "who revised" beyond the `labelled_by` stamp.
- Any reading or migration of 014-format gold files, and of older logs, or reading disagreements back out of the cache for old evaluation lines.
- A secret, token, password or login for the page.
- Any change to the classifier, cache, cost ledger, metrics, or to what an evaluation scores.
