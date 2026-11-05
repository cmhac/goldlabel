# Feature Specification: Start the labelling page from the command line, browse samples, review evaluations and revise gold labels

**Feature Branch**: `claude/nifty-planck-1agal4` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-05

**Status**: Draft

**Input**: User description: "Read https://github.com/cmhac/goldlabel/issues/26 and build a spec for this." Issue #26, *Labelling page: start from the CLI, browse samples, review evaluations and revise gold labels*: "A tester was invited to change two gold labels. The page opened generically, he had to page through every row to find the two IDs, and he couldn't go back. Today `gl.label` is the only way to start the server, and it knows only the one sample it was called with. He also couldn't see the text while scrolling a long label list."

The issue's checklist is the scope of this spec. Its three "open decisions" are resolved below as **Decisions taken** with the smallest option; each can be overturned in `/speckit-clarify` before planning.

## Decisions taken (the issue's open decisions)

1. **Taxonomy.** `gl.label` saves a snapshot of the taxonomy it was called with, beside the gold file of that dataset. A page started from the command line reads that snapshot. With no snapshot, the page offers only the labels already used in that dataset's gold file and says so on the page. `clf.evaluate` writes no snapshot (the evaluation log already records the taxonomy it ran with, and a second place that stores one would drift). The command line takes no Python import path.
2. **Running server.** One lock file per storage folder holds the running server's process id, port and start time. A lock whose process is gone, or whose port does not answer, is stale and is replaced. This lock replaces the per-gold-file `.lock` of 012-014.
3. **Revision record.** A new append-only `revisions.jsonl` beside `evals.jsonl`. The gold-file format of 014 does not change. An evaluation is **stale** when the labels of its sample today differ from the labels it scored (the evaluation log already stores a digest of those), so staleness needs no timestamp comparison and also catches rows labelled for the first time after the evaluation ran.

## Where things are today

- `gl.label(sample, taxonomy)` is the only way to start the server. It serves one pass over one sample, can only advance through rows that were pending (or, with `force_open_ui=True`, every row once, in file order), and has no way to open a given row.
- A second `gl.label` on the same gold file raises "already being labelled". The lock is per gold file, so two datasets can be labelled at once but nothing shows more than one of them.
- The page shows the pass's text on the left and the controls on the right. From 1024px the controls card is sticky, but it is not scrollable on its own: with many labels the text and the later labels cannot be on screen together.
- `evals.jsonl` records each evaluation's metrics, prompt digest, rows digest, taxonomy and sample names, but not which rows the classifier got wrong. The disagreements exist only on the `Evaluation` object returned to the notebook.
- A revised gold row is overwritten in place (`labels`, `labelled_at`, `note`). Nothing records what it said before. A row first labelled by `Gold.import_rows` and later revised in the page loses `labelled_by: "imported"` with no trace.

## Clarifications

### Session 2026-11-05

- Q: When a page is already running and a notebook calls `gl.label`, does the cell return at once or wait? → A: It waits until no row of the pass is still pending (or the user interrupts), then returns the Sample, so the notebook flow of 012-014 is unchanged. With `force_open_ui=True` there is nothing pending to wait for, so it prints the URL and returns at once.

Run `/speckit-clarify` again to overturn any of the three decisions above.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Open the page from a terminal and change two labels by id (Priority: P1)

A colleague is told "labels for rows `a17` and `b203` in the trump dataset are wrong". They run `goldlabel label trump` in the project folder. The page opens on that dataset, listing its samples with row counts and how many rows are labelled. They open the sample, type `a17` into **Jump to id**, change the label, add a note, save, go back to where they were, jump to `b203`, change it, and close the page. Each change is saved at once and each is appended to `revisions.jsonl`.

**Why this priority**: it is the case that prompted the issue, and everything else in the page builds on a page that can open on any row of any dataset without a notebook.

**Independent Test**: build a storage folder with a gold file of two samples, run the command with a fake browser, and over HTTP list datasets and samples, open a row by id, post a revised label and note, read the gold file and `revisions.jsonl`, and use back to return to the previous row.

**Acceptance Scenarios**:

1. **Given** a storage folder with `gold.jsonl` and `gold-corpus-b.jsonl`, **When** the user runs `goldlabel label` (no name), **Then** the page lists both datasets, each with its samples, their row counts and labelled counts, and does not open any row.
2. **Given** the same folder, **When** the user runs `goldlabel label corpus-b`, **Then** the page opens on that dataset; a name that matches no file prints the datasets that exist and exits non-zero without starting a server.
3. **Given** a labelled row `a17`, **When** the user opens it by id and saves a different label, **Then** the gold file holds the new label stamped `labelled_by: "goldlabel-ui"` with a new `labelled_at`, and one line is appended to `revisions.jsonl`.
4. **Given** an id that is not in the dataset, **When** the user submits it in **Jump to id**, **Then** the page says so and stays where it was.
5. **Given** the user opened row `a17`, then jumped to `b203`, **When** they press Back, **Then** they are on `a17` with their place in the sample list unchanged, and Back again returns to the row before it, one step each, down to the first row they opened.
6. **Given** `--dir PATH`, **When** the command runs, **Then** it serves `PATH`; without it, `GOLDLABEL_DIR`, then `.goldlabel/`, as every other function resolves the storage folder.

---

### User Story 2 - `gl.label` joins a server that is already running (Priority: P1)

A notebook user has the page open from the terminal, then runs `gl.label(dev, taxonomy)`. No second server starts. The cell prints the running server's URL, pointed at the dev sample's pending rows, and waits until none of those rows is pending any more (or the user interrupts the cell), then returns the Sample. If nothing is running, `gl.label` behaves as in 012-014 (it opens a page and waits for **Done**).

**Why this priority**: today a second labelling call fails with an error; with one server per folder it must instead lead the user to the page they already have.

**Independent Test**: with a server running for a storage folder (started by the library, so no process is needed), call `label` for another sample and check that the number of listening servers has not changed, the printed URL is the running server's, and the call waits while a row of the pass is pending and returns once none is (label the rows over the page's API in the test). Then stop the server, leave a lock for a dead process, and check that the next call replaces the lock and starts a server.

**Acceptance Scenarios**:

1. **Given** a running server for the folder, **When** `gl.label(sample, taxonomy)` runs, **Then** it prints that server's URL, starts no server, writes no gold file itself, and returns the Sample once no row of the pass is pending; interrupting the cell stops the wait and changes nothing.
2. **Given** that call, **When** the page is opened from the printed URL, **Then** it opens on the pass over the sample's rows that were pending at the call, so the labelling flow of 013-014 is unchanged.
3. **Given** a lock naming a process that no longer exists, or a port that does not answer, **When** `gl.label` or `goldlabel label` runs, **Then** the lock is replaced and a server starts.
4. **Given** two storage folders, **When** a server runs for one, **Then** the other is unaffected.
5. **Given** the taxonomy passed to `gl.label` differs from the saved snapshot, **When** it runs, **Then** the snapshot is replaced with the new one and a running server uses it from its next request.
6. **Given** a server started by `gl.label`, **When** the user presses **Done**, **Then** the server stops as today. A server started by `goldlabel label` ignores **Done** for stopping and runs until the terminal process is interrupted.

---

### User Story 3 - Review an evaluation and its disagreements (Priority: P2)

For a sample, the page lists its evaluations from `evals.jsonl`, newest first: when, score against target, row count, model, prompt digest. Opening one lists the classifier's disagreements with the gold labels, each with the row's text, the gold label, the predicted label, the classifier's reasoning and the row's note. An evaluation whose sample was revised since it ran is flagged **STALE** in words, with the reason ("labels changed since this ran"). The user can click a disagreement to open the row and revise it, and the flag appears on the list from then on.

**Why this priority**: it turns "read the disagreements" into the loop it was meant to be (spot a wrong gold label, fix it, know the number is out of date), but it needs the browse page of Story 1.

**Independent Test**: write an `evals.jsonl` by hand (with and without the new disagreement list), serve it, and check the history for a sample, the disagreements of one line, and that revising one row makes exactly the lines of that sample stale and no other.

**Acceptance Scenarios**:

1. **Given** a sample evaluated twice, **When** its history is opened, **Then** both evaluations are listed with their time, score, target and PASS/FAIL (or neither without a target), rows scored and how many were skipped as pending.
2. **Given** an evaluation that recorded its disagreements, **When** it is opened, **Then** each shows id, text, gold label at evaluation time, predicted label, reasoning, and the row's current note.
3. **Given** a disagreement whose row has since been revised, **When** it is shown, **Then** it also shows the current label ("revised since") so the reader does not mistake the old gold label for today's.
4. **Given** an evaluation line written before this feature (no disagreements stored), **When** it is opened, **Then** the page says "disagreements were not recorded by this version" and shows its metrics only.
5. **Given** a disagreement whose row has been removed from the gold file, **When** it is shown, **Then** it says the row is no longer in the file, and still shows the logged gold and predicted labels.
6. **Given** an evaluation of `dev` and a revision of a `test` row, **When** the lists are shown, **Then** the `dev` evaluation is not stale. An evaluation of `dev + test` is stale after either.
7. **Given** a note-only revision, **When** the lists are shown, **Then** no evaluation becomes stale (notes never reach a model).
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

### User Story 5 - Every revision is recorded and the gold rule still holds (Priority: P1)

Every change to an already-labelled row's labels or note is appended to `revisions.jsonl`: time, dataset, sample, row id, labels and note before and after, who labelled it before (`labelled_by`) and the new stamp. Saving a row with nothing changed writes nothing. The first labelling of a pending row is not a revision. The labelling server remains the only writer of gold labels (and `Gold.import_rows`); no code path in the library, the command or the page writes a label from a model's output.

**Why this priority**: revising labels is safe only if it can be audited, and the constitution's first principle depends on the server being the one writer.

**Independent Test**: revise a labelled row, a pending row, an imported row, and a note only; save one row unchanged; check the log lines and that the gold file differs only in that row.

**Acceptance Scenarios**:

1. **Given** a labelled row, **When** its labels change, **Then** one line is appended before the gold file is rewritten, so a crash between the two leaves a record of a change that did not happen rather than a change with no record.
2. **Given** an imported row, **When** it is revised in the page, **Then** the gold row becomes `labelled_by: "goldlabel-ui"` and the record keeps `imported` as the previous stamp.
3. **Given** a row saved with the same labels and the same note, **When** it is posted, **Then** nothing is appended and the file is not rewritten.
4. **Given** the page's API, **Then** no endpoint accepts a label from anything but a person's request carrying the session's token, and no endpoint returns a model's prediction as a suggestion for a label.
5. **Given** a pending row labelled for the first time, **Then** no revision line is written and the sample's evaluations become stale (its labels differ from those they scored).

---

### Edge Cases

- No gold file in the storage folder: the command starts nothing and prints that no gold dataset was found in the folder (the path), and how to make one.
- A gold file with a malformed line: the page shows the dataset's error (the file and line) and the other datasets still list.
- A dataset drawn from a notebook while the page is open: the next page load shows it; the page does not poll.
- A dataset with a sample whose rows are all labelled: the sample's **Label pending** action is disabled and says "nothing pending".
- `--port` already in use: exit non-zero with the message and start nothing; a bare run picks a free port.
- Two browser tabs on one server: saves are serialized and both read the file each time, so the later save wins; both are recorded.
- A stale lock found on a read-only folder: the command reports it cannot replace the lock and exits non-zero.
- A taxonomy snapshot that does not parse: treated as missing, and the page says labels shown are the ones already used.
- A saved label that is not in the snapshot taxonomy (a row labelled under an older taxonomy): shown in the row as-is, and a revision can only choose among snapshot labels; the page flags it as "not in this taxonomy".
- `labelled_by` of a row is something other than the three known values: the record copies it unchanged.
- The server never listens beyond 127.0.0.1 and keeps the Host and token checks of 013; the lock file that carries the token is created readable only by its owner.

## Requirements *(mandatory)*

### Functional Requirements

**Command**

- **FR-001**: The package MUST have a `goldlabel label [NAME] [--dir PATH] [--port N]` subcommand next to `install`. `NAME` is a dataset name as in `gl.Gold(candidates, name=NAME)`; with none, the page opens on the list of datasets.
- **FR-002**: The storage folder MUST resolve as everywhere else: `--dir`, then `GOLDLABEL_DIR`, then `.goldlabel/`.
- **FR-003**: The command MUST print the page URL, the storage folder it serves, and the gold rule's one-line reminder, open the browser, and run until interrupted. It MUST exit non-zero and start nothing for an unknown dataset name, an empty folder, or a port in use.
- **FR-004**: The command MUST NOT take a Python import path, a taxonomy file, or any flag that sets, imports or edits a label.

**Joining a running server**

- **FR-005**: A running server MUST be discoverable by the storage folder through one lock file holding its process id, port, start time and access token, created readable only by its owner and removed when the server stops.
- **FR-006**: `gl.label(sample, taxonomy, ...)` MUST, when a server for that folder is already running, print that server's URL aimed at the pass over the rows pending in `sample` at the call (every row of `sample` with `force_open_ui=True`), start no server, and wait until none of those rows is still pending, then return the `Sample`; an interrupt stops the wait and writes nothing. With `force_open_ui=True` there is nothing pending to wait for, so it prints the URL and returns at once. With none running it MUST behave as in 012-014.
- **FR-007**: A lock whose process is gone, or whose port does not answer a request carrying its token, MUST be treated as stale and replaced. The per-gold-file lock and its "already being labelled" refusal are removed.
- **FR-008**: `gl.label` MUST save the taxonomy it was called with to a snapshot beside the gold file; a running server MUST use the snapshot as it is at each request.

**Browse and navigate**

- **FR-009**: The page MUST list every gold dataset in the storage folder (the default and each named one), each with its samples, their row counts, and how many rows are labelled and pending.
- **FR-010**: A user MUST be able to open any row of any sample, labelled or pending, from a list of the sample's rows (id, labels, whether it has a note), and from **Jump to id** within the open dataset.
- **FR-011**: **Back** MUST step back through the rows the user opened in this page visit, one at a time, and leave the sample list where it was (scroll position and filter, if any). Reloading the page MUST land on the row or list the user was on.
- **FR-012**: **Label pending** on a sample MUST start the labelling pass of 013-014 over its pending rows: the same keys, the same counts for the pass only, Skip, and the finished screen. It MUST be the same code that serves `gl.label`.

**Revise**

- **FR-013**: On any row the user MUST be able to change its labels (within the snapshot taxonomy and its `single`/`multi` mode) and its note, with the same keyboard behaviour as 013, and the change MUST be saved at once.
- **FR-014**: The server MUST validate every revision exactly as it validates a first label (known labels, mode, body size) and MUST be the only writer of gold labels besides `Gold.import_rows`.
- **FR-015**: A revised row MUST be restamped `labelled_by: "goldlabel-ui"` with a new `labelled_at`; the gold file's format, and the reading of files from 014, MUST NOT change.

**Revision record**

- **FR-016**: Each revision of an already-labelled row, to its labels or its note, MUST append one JSON line to `revisions.jsonl` in the storage folder holding: time, gold file, sample, row id, labels before and after, note before and after, `labelled_by` before and after, `labelled_at` before. The line MUST be written before the gold file is rewritten.
- **FR-017**: A save that changes neither labels nor note MUST write nothing. The first labelling of a pending row MUST NOT be recorded as a revision.
- **FR-018**: `revisions.jsonl` MUST be append-only, with no way to switch it off or send it elsewhere, as `evals.jsonl` is.

**Evaluations**

- **FR-019**: `evals.jsonl` lines written by `clf.evaluate`/`aevaluate` MUST also store the disagreements: for each, the row id, gold labels, predicted labels and the classifier's reasoning (not the text, which the gold file holds). Lines already in a log, and the identical-rerun rule (same sample, rows digest, prompt digest, model, metric and target), MUST NOT change.
- **FR-020**: For each sample the page MUST list the evaluations of exactly that sample, newest first, and for an opened evaluation list its disagreements as in Story 3. Combinations (`dev + test`) are listed under the combination's name when the log has any.
- **FR-021**: The page MUST mark an evaluation **STALE** when the labels of the rows that sample holds now differ from the rows digest the evaluation logged, naming the reason in words; a note-only change MUST NOT mark one.
- **FR-022**: The page, the server and the command MUST NOT run an evaluation, classification, estimate or any model call.

**Layout**

- **FR-023**: From 1024px, the text card and the controls card MUST each scroll on their own within the window's height, the text MUST stay in view while the controls scroll, and both scroll areas MUST be reachable and show focus by keyboard.
- **FR-024**: Below 1024px the page MUST be one column of text then controls in the ordinary page scroll, as in 013, with the one-column behaviour above documented in the page's help text.

**Agent surface**

- **FR-025**: The skills, the README and `docs/agent-instructions.md` MUST tell users to run `goldlabel label` to review or revise labels and tell agents to hand that command to the user, never to write a label. The gold rule's canonical text MUST NOT change. The constitution (Additional Constraints: "one console command, ... there is no other command") and `AGENTS.md` MUST be amended in the same change to allow `goldlabel label` (a MINOR amendment, 1.4.0, which needs the user's approval before implementing).

### Key Entities

- **Storage folder**: the folder named by `--dir`, `GOLDLABEL_DIR` or `.goldlabel/`; holds the gold files, `evals.jsonl`, `revisions.jsonl`, taxonomy snapshots and the server lock.
- **Server lock**: process id, port, start time and token of the one running labelling server for a storage folder.
- **Taxonomy snapshot**: the taxonomy `gl.label` last saved for a gold dataset; used only to show label options.
- **Revision**: an appended record of a change to a labelled row's labels or note, with before and after values.
- **Evaluation line (extended)**: an existing `evals.jsonl` line plus its disagreements; **stale** is derived from it and the current gold labels, never stored.
- **Pass**: the rows `gl.label` or **Label pending** walks, fixed when it starts (unchanged from 013-014).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A person given two row ids opens the page from a terminal and saves a new label for both without paging through any other row: 0 rows visited besides the two, and under 60 seconds from the command to the second save.
- **SC-002**: With a server running for a folder, 100% of `gl.label` calls print its URL and start no second server; with none running, 100% start one.
- **SC-003**: 100% of changes to a labelled row's labels or note produce exactly one revision line, and 0% of unchanged saves or first labels do.
- **SC-004**: An evaluation is flagged stale after exactly the label changes in its own sample (including first labels after it ran) and never after a note-only change or a change in another sample.
- **SC-005**: At 1280px with a 40-label taxonomy, the full text of a short item stays on screen while the last label is scrolled into view.
- **SC-006**: The gold-rule tests (`tests/test_gold_rule.py`, `tests/test_skills.py`, `tests/test_docs.py`) pass unchanged: no new way to set a label exists besides the page's person-triggered request.

## Assumptions

- The user runs the command from a terminal with a browser on the same machine, as with `gl.label`; running it for another machine is out of scope.
- The disagreement list is stored from this version on; older evaluation lines stay readable and show metrics only.
- Staleness is read from the logged rows digest, which already covers labels, not notes.
- `gold-<name>.jsonl` and `gold.jsonl` are the only gold files; `*.removed.jsonl` and `*.tmp` are not datasets.
- The labelling flow, keys and counts of 013-014 are unchanged and keep their tests, except the per-file lock tests, which move to the folder lock.
- A person who can read the lock file can already edit the gold file; the token's job is to stop other local processes and web pages, as in 013.

## Human checks (agents report these and stop)

Open the command's page in a real browser at 1280px and 390px, light and dark, with a 40-label taxonomy; revise two rows by id with the keyboard only and use Back; open `gl.label` while it runs; read the disagreements of a real evaluation and see it go stale; run the gold-rule refusal trial with the updated skills.

## Deliberately skipped

- Running evaluations, classifications or estimates from the page (the issue says evaluations stay code-only).
- Editing the taxonomy in the page, a taxonomy file or Python import path for the command, and `clf.evaluate` writing a taxonomy snapshot.
- Adding, drawing, removing or moving rows from the page (`draw_sample` and `remove` stay in code).
- Searching by text, filters, sorting or bulk revision; only list, **Jump to id**, and **Label pending**.
- Undoing a revision from the page, or showing a row's revision history in the page (the record is a file; read it with polars).
- Live refresh of the page when files change, or a notifier between `gl.label` and the page.
- `--host`, `--no-browser`, and serving beyond 127.0.0.1.
- A sticky or floating text on the one-column layout, and a new layout below 1024px.
- Accounts, names for reviewers, or any "who revised" beyond the `labelled_by` stamp.
- Any migration of older logs, or reading disagreements back out of the cache for old evaluation lines.
- Any change to the classifier, cache, cost ledger, metrics, or to what an evaluation scores.
