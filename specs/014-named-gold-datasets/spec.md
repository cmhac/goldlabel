# Feature Specification: Named gold datasets, and a labelling page that keeps dev and test apart

**Feature Branch**: `claude/sleepy-ritchie-ko69ta` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Fix issues #22 and #23 and improve how gold labelling works." Issue #22, *Multiple gold datasets/separate evals*: "Users may want to set up multiple gold datasets for evaluation. For example, you might tune a prompt on one corpus, then want to apply it to another and just create a test set there without going through the dev/test workflow. Test is often sufficient in such cases. Need to be able to create separate, named golden datasets." Issue #23, *gold labeling not respecting draw's n parameter*: "I just ran a gold.draw with n=50, and the UI is showing 100. There's also a test draw in the notebook with another n=50, but not sure why the gold dataset is not treating those as separate."

## Where things are today

- **#23 is not a bug in `draw`.** The user's own notebook (`2026-11-04-trump-on-the-ballot-v2.ipynb`) confirms it: `gl.label(gold, taxonomy)` right after `draw(n=50, split="dev")` opened a page of 100 items, and the printed result after both passes was "GoldSet all: 100 rows". The intended behaviour, in the user's words: *the UI only shows the items being labelled in that pass.* `gold.draw(candidates, n=50)` writes exactly 50 rows. The user then drew a second 50 with `split="test"` into the same file, and `gl.label(gold, taxonomy)` (no `split`) scopes the page to *every* row in the file, labelled or not, in both splits. The page's counter ("x of 100") counts dev and test together. The README, the walkthrough and the stage skills all call `gl.label(gold, taxonomy)` with no split after drawing the test split, so the confusing behaviour is the documented one. Nothing on the page says which split a row belongs to.
- **#22.** A `Gold` is one file (`gold.jsonl` under the root, or any path passed in). A second corpus can already get its own file by passing a path, but nothing in the docs or skills says so, the file is not "named" anywhere a reader sees, and the evaluation log is shared: "the test split was evaluated N times" and `fold_test`'s "evaluated since the last fold" check count test evaluations from *every* gold file together (the log line records the gold file, but those two checks ignore it). So scoring dataset B's test split would let dataset A's spent test rows be folded without ever having been evaluated, and would add to A's evaluation count.
- Every gold row must carry `split` of `dev` or `test`, and a dataset that only has a test split is allowed already. The workflow "draw dev, tune, draw test, evaluate once" is advice in the skills, not a requirement of the library.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The labelling page shows only the rows of this pass (Priority: P1)

A user draws 50 dev rows and runs `gl.label(gold, taxonomy)`. The page shows exactly those 50 pending rows: "x of 50", the split named on the page. Rows that are already labelled (an earlier pass, or the other split) are not counted and are not paged. Later, the user draws 50 test rows and runs it again: the page shows those 50, not 100. A pass is the set of rows pending when `gl.label` is called (within the chosen split); the total stays fixed for the pass, and **Back** can return to rows labelled earlier in the same pass. A user who asks for `split="dev"` or `split="test"` gets that split's pending rows. If both splits have pending rows and the user did not say which, the call does not guess: it refuses with a message that names the two splits and how many rows are pending in each. `force_open_ui=True` is the one way to page already-labelled rows (to review or relabel), and it needs a split.

**Why this priority**: this is issue #23. The count the user saw was the single most visible symptom, and the fix changes what every notebook in the repo prints.

**Independent Test**: build a gold file by hand with 50 labelled dev rows and 50 pending test rows; call the labelling server with no split and check the state reports 50 total, 0 done, split `test`, and that no dev row is ever served. Repeat with both splits pending and check the call is refused with both counts in the message.

**Acceptance Scenarios**:

1. **Given** 50 labelled dev rows and 50 pending test rows, **When** `gl.label(gold, taxonomy)` is called with no split, **Then** the page's total is 50, its position and progress count only those test rows, and it shows the word "test". **Given** 50 pending dev rows and nothing else, the total is 50 and every row is a dev row.
   1a. **Given** a pass of 50 pending rows of which 20 are labelled, **When** the page is reloaded or the call is made again, **Then** the new pass is the 30 still pending, with total 30.
2. **Given** pending rows in only one split, **When** `gl.label` is called with no split, **Then** that split is chosen, and the printed line says which one.
3. **Given** pending rows in both splits, **When** `gl.label` is called with no split, **Then** it raises a `GoldError` that says "dev: N pending, test: M pending; pass split='dev' or split='test'" and starts no server.
4. **Given** no pending rows in either split and no `force_open_ui`, **When** `gl.label` is called with no split, **Then** it prints one line that nothing is pending (as 012 does) and returns the labelled rows of both splits as before.
5. **Given** `split="dev"` or `split="test"`, **When** `gl.label` is called, **Then** only that split is paged, counted and returned, as today.
6. **Given** `force_open_ui=True` and no split, **When** both splits have rows, **Then** the call is refused the same way as scenario 3 but listing each split's row count, because "review everything at once" is the mix this feature removes. **Given** `force_open_ui=True, split="dev"`, **Then** the pass is all dev rows, labelled or not, as 012 intended.

---

### User Story 2 - A second, separately named gold dataset (Priority: P1)

A user tuned a prompt on corpus A with the full dev/test workflow. They now apply it to corpus B and only want a test set there. They create a gold dataset by name (for example "corpus-b"), draw a test split from B's candidates, label it, and evaluate on it. Corpus A's dataset is untouched, and B's rows, labels, counts, labelling page, lock, and evaluations never mix with A's. They can create as many named datasets as they like, and a dataset with only a test split (or only a dev split) needs no dev/test ceremony.

**Why this priority**: this is issue #22.

**Independent Test**: create two named datasets in one temporary root, give both a row with the same id, label them differently, and check each reads back its own rows only, that the default (unnamed) dataset is still the single `gold.jsonl`, and that two labelling sessions can run at once (separate locks).

**Acceptance Scenarios**:

1. **Given** no name, **When** a `Gold` is created, **Then** it is the same file as today, so every existing notebook keeps working.
2. **Given** a name, **When** a `Gold` is created, **Then** its file sits beside the default one, derived from the name, and an explicit path still wins over a name.
3. **Given** two datasets, **When** a row id is drawn into one that the other already holds, **Then** the draw succeeds (the "not already in the file" rule is per dataset).
4. **Given** a dataset whose draws were all `split="test"`, **When** `evaluate` is called on its test split, **Then** it works with no dev rows present.
5. **Given** a name that would escape the root or is empty or has characters that are unsafe in a file name, **When** a `Gold` is created, **Then** it is refused with a message naming the allowed characters.
6. **Given** a dataset, **When** it is printed, **Then** its name appears with its dev, test and pending counts.
7. **Given** two datasets, **When** each is labelled in its own page, **Then** each has its own lock and neither blocks the other; the same dataset still refuses a second concurrent session.

---

### User Story 3 - Evaluations and folds count per dataset (Priority: P2)

A user evaluates the test split of dataset B. Dataset A's "test evaluated N times" line and A's `fold_test` check do not see it. Each dataset's evaluation history is its own view of the shared log; the log stays one append-only file.

**Why this priority**: without it, US2 is wrong in a quiet way: the "evaluate the test split once" discipline and the fold guard (constitution 1.2.0) would be measured across datasets.

**Independent Test**: log a test evaluation against dataset B's path, then check that A's test count is zero and that A's `fold_test` still refuses with "has not been evaluated since the last fold"; log one against A and check it now counts.

**Acceptance Scenarios**:

1. **Given** test evaluations logged for two gold files, **When** the evaluation log is shown for one dataset, **Then** the "test split evaluated N times" line counts only that dataset's evaluations.
2. **Given** a test evaluation for B only, **When** A's `fold_test` is called, **Then** it refuses as if A's test split was never evaluated.
3. **Given** a fold on A, **When** B's counts are shown, **Then** B's are unchanged (the `test_folded` event records which dataset it belongs to).
4. **Given** an older log whose fold events carry no dataset, **When** it is read, **Then** the event is attributed by the gold file recorded on the evaluations around it, or counted for the default dataset if nothing says otherwise, and nothing fails.

---

### User Story 4 - The docs and skills teach both (Priority: P2)

An agent following `goldlabel-tune` after this ships never writes a bare `gl.label(gold, taxonomy)` right after drawing a second split, and knows that a second corpus gets a second named dataset, usually test-only, and not a re-use of the first dataset's file.

**Independent Test**: the existing drift tests (`tests/test_skills.py`, `tests/test_skill_stages.py`, `tests/test_docs.py`) pass with the changed examples, and a new check fails when a skill example labels after a second `draw` without naming a split.

**Acceptance Scenarios**:

1. **Given** the README, the walkthrough (notebook and script), the overview skill's references and the `goldlabel-tune` skill, **When** they draw and then label, **Then** they pass the split they just drew to `gl.label`.
2. **Given** the `goldlabel-tune` and `goldlabel-run` skills, **When** the user wants to apply a tuned prompt to a different corpus, **Then** they say to create a named dataset for that corpus, draw a test split, have people label it, and evaluate once.
3. **Given** the gold rule, **When** any of this ships, **Then** `src/goldlabel/gold_rule.md` and every copy are unchanged, and nothing adds a way to set a label.

---

### Edge Cases

- A gold file written before this feature (no name anywhere) still loads, labels, evaluates and folds unchanged.
- `Gold(path)` and `Gold(name=...)` together: the path wins, the name is only a label in the printed summary.
- A named dataset that does not exist yet is not an error to name; it is created by the first `draw` or `import_rows`, like the default file.
- The default dataset and a dataset someone named "gold" must not collide: the name is mapped to a distinct file name, and `gold.jsonl` stays the default.
- Two named datasets with the same row id are fine; ids are unique per dataset only.
- `remove` writes `<file>.removed.jsonl` per dataset, so removed rows from B never land in A's file.
- A `force_open_ui=True, split=...` run on a fully labelled split still lets a person relabel, as 012 intended; that is the only pass that includes labelled rows.
- A row drawn into the file by another process after the pass began is not added to that pass.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A `gl.label` pass MUST page and count only the rows that were pending in its split when the call was made, never already-labelled rows and never rows of the other split; the total is fixed for the pass. With no `split`, the split is the single one that has pending rows. The rows it returns stay as today (the labelled rows of that split).
- **FR-002**: `gl.label` with no `split` and pending rows in both splits MUST refuse with a `GoldError` that gives each split's pending count and tells the user to pass `split="dev"` or `split="test"`, and MUST start no server.
- **FR-003**: When nothing is pending anywhere and no `split` is given, `gl.label` MUST keep 012's behaviour (one printed line, no server, labelled rows returned); with `force_open_ui=True` and no `split` and rows in both splits it MUST refuse as in FR-002.
- **FR-004**: The labelling page MUST show which split it is labelling, and its "x of N" MUST count only the rows of this pass.
- **FR-005**: A user MUST be able to create a gold dataset by name; the name selects a file beside the default one, and the unnamed `Gold()` MUST remain the existing default file so no current notebook changes.
- **FR-006**: A dataset name MUST be refused if it is empty or contains anything other than letters, digits, `-` and `_`, so it cannot escape the root or collide with the default file or its `.lock`, `.tmp` or `.removed.jsonl` companions.
- **FR-007**: Each dataset MUST have its own rows, its own lock, its own removed-rows file and its own labelling session; the "id is not already in the file" rules of `draw` and `import_rows` MUST apply per dataset.
- **FR-008**: A dataset MUST be usable with only one split: `draw`, `label`, `evaluate`, `fold_test` and the printed summary MUST work with only dev or only test rows, with no message that implies the other split is missing.
- **FR-009**: The printed summary of a `Gold` MUST show its name (or "default"), file and per-split counts.
- **FR-010**: The test-evaluation count and `fold_test`'s "evaluated since the last fold" check MUST consider only evaluations logged for that dataset's gold file; `test_folded` events MUST record the dataset they belong to. Reading an older log MUST not fail.
- **FR-011**: The README, the walkthrough (notebook and script), `goldlabel` references, `goldlabel-tune`, `goldlabel-run` and `docs/agent-instructions.md` MUST pass the drawn split to `gl.label` and describe the second-corpus, test-only case; a drift test MUST fail when a skill example labels after a second draw without a split.
- **FR-012**: Nothing in this change MAY add a way to write a gold label or alter `gold_rule.md`; only the labelling server and `Gold.import_rows` write labels, and no label is ever changed by moving, naming or counting datasets.

### Key Entities

- **Gold dataset**: a set of human-labelled rows in one file, with an optional name. Its rows are dev or test; it may hold either or both.
- **Split**: `dev` (for tuning) or `test` (scored once at the end), unchanged; now also the unit the labelling page works on.
- **Evaluation log**: one append-only file shared by all datasets; each line already names its gold file, which is now what separates the datasets' histories.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who draws 50 dev rows and opens the labelling page sees "of 50", and after labelling them and drawing 50 test rows sees "of 50" again (not 100) with no dev row, in 100% of the test cases covering that flow, including the rerun of a notebook whose gold file already holds both splits.
- **SC-002**: With pending rows in both splits and no split passed, the user gets a refusal that names both counts and the fix, and no page is opened, in 100% of tests.
- **SC-003**: A user can create a second dataset, draw 50 test rows from a different corpus, label them and score them, without editing or even reading the first dataset's file, and the first dataset's counts, evaluation count and fold eligibility are identical before and after.
- **SC-004**: Every gold file written before this feature loads and behaves identically (the pre-006 fixtures and the existing tests pass unchanged apart from the split now named on the page).
- **SC-005**: No example in the README, walkthrough or skills draws a second split and then calls `gl.label` without naming it, and a test fails when one does.

## Assumptions

- "Named dataset" means a name that picks a file; datasets need no registry, no list command and no stored metadata, in line with "the code is the pipeline".
- The name is a file-name suffix beside the default (for example `gold.jsonl` and one file per name); the exact pattern is a plan decision, but it must keep the default untouched.
- A user who wants dev and test for a second corpus gets them the same way as today, inside the second named dataset; nothing forces test-only.
- The page names the split in its existing header or status text; no redesign (013 stays as built).
- "This pass" means the rows pending at the call, which matches the user's wording and needs no record of which draw created a row (no draw ids, no stored state).
- Pending rows in both splits is rare in the documented flow (dev is labelled before test is drawn), so refusing instead of guessing costs little and avoids another surprise.
- Datasets are not merged, copied or compared; if a user wants to move rows between them, that is a new request.

## Deliberately skipped

- A dataset registry, listing command, config file or stored "current dataset": names are only file names.
- Merging, copying or diffing datasets, and cross-dataset metrics.
- A split picker, tabs or a dataset switcher inside the labelling page.
- Moving rows between splits (beyond the existing `fold_test`) or between datasets.
- A third split, a validation split or custom split names.
- Migrating or renaming existing gold files; the default file stays where it is.
- Any change to how the classifier, cache, cost ledger or metrics work.
- Rewording the gold rule, and any new way to write a label.
