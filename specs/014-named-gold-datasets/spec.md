# Feature Specification: A simpler gold API: candidates and sample size on `Gold`, a required split, named datasets

**Feature Branch**: `claude/sleepy-ritchie-ko69ta` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Fix issues #22 and #23 and improve how gold labelling works." Issue #22, *Multiple gold datasets/separate evals*: "Users may want to set up multiple gold datasets for evaluation. For example, you might tune a prompt on one corpus, then want to apply it to another and just create a test set there without going through the dev/test workflow. Test is often sufficient in such cases. Need to be able to create separate, named golden datasets." Issue #23, *gold labeling not respecting draw's n parameter*: "I just ran a gold.draw with n=50, and the UI is showing 100. There's also a test draw in the notebook with another n=50, but not sure why the gold dataset is not treating those as separate." Follow-up decisions from the user (2026-11-04): the labelling page only shows the items being labelled in that pass; there is never a reason to label without naming a split, so the split is required; `Gold` takes the candidates when it is created; `Gold` has a `sample_size` (default 50) that applies to each split; `draw` becomes `draw_sample(split=...)` using that size, with `draw_dev` and `draw_test` as shortcuts, and `draw_sample` still usable directly to draw more rows.

## Where things are today

- **#23 is not a bug in the draw.** `gold.draw(candidates, n=50, split="dev")` writes exactly 50 rows. The user's notebook (`2026-11-04-trump-on-the-ballot-v2.ipynb`) then called `gl.label(gold, taxonomy)` with no `split`, which pages *every* row in the file, labelled or not, in both splits: one 50-row draw opened a page of 100 (the file already held 50 test rows from an earlier run), and the printed result was "GoldSet all: 100 rows". The README, the walkthrough and the stage skills all use that bare call, so the confusing behaviour is the documented one.
- **The API repeats itself.** Every `draw` call passes the candidates, `n=50` and a split again. The notebook needed a guard (`if not gold.all.rows:`) because nothing says which draws were meant to be one-off.
- **#22.** A `Gold` is one file (`gold.jsonl` under the root, or any path passed in). A second corpus can already get its own file by passing a path, but nothing in the docs says so, and the evaluation log is shared: "the test split was evaluated N times" and `fold_test`'s "evaluated since the last fold" check count test evaluations from *every* gold file together (each log line records the gold file; those two checks ignore it). Scoring dataset B's test split would let dataset A's spent test rows be folded without ever being evaluated.
- A dataset that only has a test split is allowed already. "Draw dev, tune, draw test, evaluate once" is advice in the skills, not a library requirement.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The labelling page shows only the rows of this pass, for a split you name (Priority: P1)

A user draws a dev sample and runs the labelling call with `split="dev"`. The page shows exactly the pending dev rows: "x of 50", the split named on the page. Rows already labelled (an earlier pass) and rows of the other split are neither counted nor paged. Later the user draws a test sample and labels with `split="test"`: the page shows those 50, not 100. A **pass** is the set of rows pending in the named split when `gl.label` is called; its total stays fixed for the pass, and **Back** can return to rows labelled earlier in the same pass. The split is required: calling `gl.label` without one is an error, because there is no case where a page should mix dev and test.

**Why this priority**: this is issue #23 and the user's stated intent ("the UI only shows the items being labelled in that pass").

**Independent Test**: build a gold file by hand with 50 labelled dev rows and 50 pending test rows; start the labelling server for `test` and check the state reports 50 total, 0 done, split `test`, and never serves a dev row. Start it for `dev` and check it reports nothing pending (the 012 line, no server). Call `gl.label` without a split and check it is refused.

**Acceptance Scenarios**:

1. **Given** 50 labelled dev rows and 50 pending test rows, **When** `gl.label(gold, taxonomy, split="test")` is called, **Then** the page's total is 50, progress counts only those rows, the page names "test", and no dev row is served.
2. **Given** a pass of 50 pending rows of which 20 get labelled, **When** the call is made again, **Then** the new pass is the 30 still pending, total 30.
3. **Given** pending rows in both splits, **When** `gl.label(..., split="dev")` is called, **Then** only the dev rows are paged and the test rows stay pending and untouched.
4. **Given** no pending row in the named split and no `force_open_ui`, **When** `gl.label` is called, **Then** it prints one line (012's), starts no server, and returns the labelled rows of that split.
5. **Given** `force_open_ui=True` and a split, **When** the call is made, **Then** the pass is every row of that split, labelled or not (review and relabel, as 012 intended).
6. **Given** no `split`, or a split other than `dev` or `test`, **When** `gl.label` is called, **Then** it is refused before any server starts or file is touched, with a message that names the two allowed splits.

---

### User Story 2 - A `Gold` that knows its candidates and its sample size (Priority: P1)

A user creates the gold dataset once, with the candidates it samples from and, optionally, a sample size that applies to each split (default 50). They then draw a dev sample and a test sample without repeating the candidates or the number. `draw_sample(split)` draws `sample_size` pending rows of the named split (the split is required); `draw_dev()` and `draw_test()` are shortcuts for it. A user who wants more rows (a second dev round, a fresh test split after `fold_test`, a larger sample for one split) calls `draw_sample` again, or changes `sample_size` first; the new rows are drawn from candidates not already in the file.

**Why this priority**: it removes the repeated arguments that made the notebook's draw cells error-prone and gives agents one idiom.

**Independent Test**: create a `Gold` over a hand-built candidates set of 200 rows with the default size, call `draw_dev()` and `draw_test()` and check 50 pending rows each, no id in both; call `draw_sample("dev")` again and check 50 more, all new; set `sample_size = 10`, draw, and check 10.

**Acceptance Scenarios**:

1. **Given** a `Gold` with candidates and no size given, **When** `draw_dev()` and `draw_test()` are called, **Then** 50 pending dev rows and 50 pending test rows are appended, with no row in both.
2. **Given** `sample_size=20`, **When** `draw_test()` is called, **Then** 20 test rows are drawn; the size applies to each split.
3. **Given** `draw_sample(split="dev")` (or the shortcut) is called a second time, **When** the candidates still have enough unused rows, **Then** another `sample_size` rows are appended, none already in the file.
4. **Given** a `Gold` with candidates, **When** `draw_sample` is called without a split, or with one that is not `dev` or `test`, **Then** it is refused and nothing is written.
5. **Given** fewer unused candidates than `sample_size`, **When** a draw is called, **Then** it fails as today, naming how many are available and how many were asked for, and writes nothing.
6. **Given** a `Gold` created without candidates, **When** it is only read (labelled, evaluated, folded), **Then** it works; **When** a draw is attempted, **Then** it fails with a message that says to give the candidates when creating the `Gold`.
7. **Given** a `seed`, **When** `draw_sample`, `draw_dev` or `draw_test` is called, **Then** the same rows are drawn on the same inputs, as today.
8. **Given** the old `gold.draw(candidates, n, split)` call, **When** it is used, **Then** it no longer exists; the error is Python's `AttributeError`, and every doc, skill, example and test uses the new calls.

---

### User Story 3 - A second, separately named gold dataset (Priority: P1)

A user tuned a prompt on corpus A with the full dev/test workflow. They now apply it to corpus B and only want a test set there. They create a second `Gold` over B's candidates with a name, draw a test sample, label it and score it. A's dataset is untouched, and B's rows, labels, counts, labelling page, lock and evaluations never mix with A's. They can create as many named datasets as they like, and a dataset with only a test split (or only a dev split) needs no dev/test ceremony.

**Why this priority**: this is issue #22. Passing the candidates to the `Gold` makes the pairing natural: one dataset, one corpus's candidates, one file.

**Independent Test**: create two named datasets in one temporary root, give both a row with the same id, label them differently, and check each reads back its own rows only, that the unnamed `Gold` is still the single `gold.jsonl`, and that two labelling sessions can run at once (separate locks).

**Acceptance Scenarios**:

1. **Given** no name, **When** a `Gold` is created, **Then** it is the same file as today, so every existing gold file keeps working.
2. **Given** a name, **When** a `Gold` is created, **Then** its file sits beside the default one, derived from the name; an explicit path still wins over a name.
3. **Given** two datasets, **When** a row id is drawn into one that the other already holds, **Then** the draw succeeds (the "not already in the file" rule is per dataset).
4. **Given** a dataset whose draws were all `draw_test`, **When** `evaluate` is called on its test split, **Then** it works with no dev rows present.
5. **Given** a name that is empty or has characters unsafe in a file name, **When** a `Gold` is created, **Then** it is refused with a message naming the allowed characters.
6. **Given** a dataset, **When** it is printed, **Then** its name (or "default") appears with its dev, test and pending counts.
7. **Given** two datasets, **When** each is labelled in its own page, **Then** each has its own lock and neither blocks the other; the same dataset still refuses a second concurrent session.

---

### User Story 4 - Evaluations and folds count per dataset (Priority: P2)

A user evaluates the test split of dataset B. Dataset A's "test evaluated N times" line and A's `fold_test` check do not see it. Each dataset's history is its own view of the shared, append-only log.

**Why this priority**: without it, US3 is wrong in a quiet way: the "evaluate the test split once" discipline and the fold guard (constitution 1.2.0) would be measured across datasets.

**Independent Test**: log a test evaluation against dataset B's path, check that A's test count is zero and A's `fold_test` still refuses with "has not been evaluated since the last fold"; log one against A and check it now counts.

**Acceptance Scenarios**:

1. **Given** test evaluations logged for two gold files, **When** the log is shown for one dataset, **Then** the "test split evaluated N times" line counts only that dataset's evaluations.
2. **Given** a test evaluation for B only, **When** A's `fold_test` is called, **Then** it refuses as if A's test split was never evaluated.
3. **Given** a fold on A, **When** B's counts are shown, **Then** B's are unchanged (the `test_folded` event records its dataset).
4. **Given** an older log whose fold events carry no dataset, **When** it is read, **Then** the event counts for the default dataset and nothing fails.

---

### User Story 5 - The docs and skills teach the new calls (Priority: P2)

An agent following `goldlabel-tune` writes `Gold(candidates)`, `draw_dev()`, `gl.label(gold, taxonomy, split="dev")`, and later `draw_test()` and `split="test"`, and knows a second corpus gets a second named `Gold`, usually test-only.

**Independent Test**: the existing drift tests (`tests/test_skills.py`, `tests/test_skill_stages.py`, `tests/test_docs.py`) pass with the changed examples, and a new check fails when any example calls `gl.label` without `split=` or still calls `.draw(`.

**Acceptance Scenarios**:

1. **Given** the README, the walkthrough (notebook and script), the overview skill's references, the stage skills and `docs/agent-instructions.md`, **When** they create a gold set, draw, or label, **Then** they use `Gold(candidates)`, the draw shortcuts and a named `split`.
2. **Given** the `goldlabel-tune` and `goldlabel-run` skills, **When** the user wants to apply a tuned prompt to a different corpus, **Then** they say to create a named `Gold` over that corpus, draw a test sample, have people label it and evaluate once.
3. **Given** the gold rule, **When** any of this ships, **Then** `src/goldlabel/gold_rule.md` and every copy are unchanged, and nothing adds a way to set a label.

---

### Edge Cases

- A gold file written before this feature (no name anywhere) still loads, labels, evaluates and folds unchanged.
- `Gold(path=...)` and `Gold(name=...)` together: the path wins, the name is only a label in the printed summary.
- A named dataset that does not exist yet is not an error; the first draw or `import_rows` creates it, like the default file.
- The default dataset and one someone named "gold" must not collide: the name is mapped to a distinct file name, and `gold.jsonl` stays the default.
- Two named datasets with the same row id are fine; ids are unique per dataset only.
- `remove` writes `<file>.removed.jsonl` per dataset, so removed rows from B never land in A's file.
- `sample_size` is a plain attribute: changing it later changes later draws only, never rows already drawn. A size below 1 or not a whole number is refused.
- Re-running a notebook cell that calls `draw_dev()` draws another sample, exactly as re-running `draw` did; the user keeps their own guard (see "Deliberately skipped").
- A row drawn into the file by another process after a labelling pass began is not added to that pass.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `gl.label` MUST require `split` (`"dev"` or `"test"`), refusing a missing or other value before any server starts; no pass may page both splits. `Gold`'s labelling server (`serve`) MUST do the same.
- **FR-002**: A `gl.label` pass MUST page and count only the rows that were pending in its split when the call was made, never already-labelled rows (except with `force_open_ui=True`, which pages every row of that split) and never rows of the other split; the total is fixed for the pass. It returns the labelled rows of that split, as today.
- **FR-003**: The labelling page MUST show which split it is labelling, and its "x of N" MUST count only the rows of this pass.
- **FR-004**: `Gold` MUST accept the candidates when it is created, and a `sample_size` (default 50, a whole number of at least 1) that applies to each split and may be changed later as an attribute. Candidates are optional so a `Gold` can be created only to read, label, evaluate or fold; a draw without candidates MUST fail with a message saying where to give them.
- **FR-005**: `Gold.draw_sample(split, seed=None)` MUST replace `Gold.draw`: it takes the split as a required argument, draws `sample_size` rows from the candidates not already in the file, appends them pending, and writes nothing if the candidates cannot supply enough. `draw_dev(seed=None)` and `draw_test(seed=None)` MUST call it with `"dev"` and `"test"`. `draw` MUST be removed (no alias), and all docs, skills, examples and tests updated.
- **FR-006**: A user MUST be able to create a gold dataset by name; the name selects a file beside the default one, and an unnamed `Gold` MUST remain the existing default file.
- **FR-007**: A dataset name MUST be refused if it is empty or contains anything other than letters, digits, `-` and `_`, so it cannot escape the root or collide with the default file or its `.lock`, `.tmp` or `.removed.jsonl` companions.
- **FR-008**: Each dataset MUST have its own rows, lock, removed-rows file and labelling session; the "id is not already in the file" rules of drawing and `import_rows` MUST apply per dataset.
- **FR-009**: A dataset MUST be usable with only one split: drawing, `label`, `evaluate`, `fold_test` and the printed summary MUST work with only dev or only test rows, with no message implying the other is missing.
- **FR-010**: The printed summary of a `Gold` MUST show its name (or "default"), file and per-split counts.
- **FR-011**: The test-evaluation count and `fold_test`'s "evaluated since the last fold" check MUST consider only evaluations logged for that dataset's gold file; `test_folded` events MUST record the dataset they belong to; reading an older log MUST not fail.
- **FR-012**: The README, the walkthrough (notebook and script), `goldlabel` references, the stage skills and `docs/agent-instructions.md` MUST use the new calls and describe the second-corpus, test-only case; a drift test MUST fail when an example calls `gl.label` without `split=` or calls `.draw(`.
- **FR-013**: Nothing in this change MAY add a way to write a gold label or alter `gold_rule.md`; only the labelling server and `Gold.import_rows` write labels, and no label is ever changed by naming, sizing, drawing or counting datasets.

### Key Entities

- **Gold dataset**: a set of human-labelled rows in one file, with an optional name, the candidates it samples from, and a sample size. Its rows are dev or test; it may hold either or both.
- **Split**: `dev` (for tuning) or `test` (scored once at the end), unchanged; now also the required unit of a labelling pass.
- **Pass**: the pending rows of one split at the moment `gl.label` is called.
- **Evaluation log**: one append-only file shared by all datasets; each line already names its gold file, which is what separates the datasets' histories.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user who draws a dev sample and opens the labelling page for `dev` sees "of 50"; after labelling and drawing a test sample, the page for `test` shows "of 50" (not 100) with no dev row, in 100% of tests covering that flow, including a rerun against a gold file that already holds both splits.
- **SC-002**: A labelling call with no split, or an unknown one, is refused with the allowed names, and no server starts, in 100% of tests.
- **SC-003**: A dev and a test split can be drawn with no argument repeated: after `Gold(candidates)`, the whole draw step is `draw_dev()` and `draw_test()`, and the resulting file has 50 pending rows in each split with no shared id.
- **SC-004**: A user can create a second dataset over another corpus's candidates, draw a test sample, label it and score it, without editing or reading the first dataset's file, and the first dataset's counts, evaluation count and fold eligibility are identical before and after.
- **SC-005**: Every gold file written before this feature loads and behaves identically (the pre-006 fixtures and existing tests pass apart from the renamed calls and the named split).
- **SC-006**: No example in the README, walkthrough or skills calls `.draw(` or `gl.label` without `split=`, and a test fails when one does.

## Assumptions

- "Named dataset" means a name that picks a file; datasets need no registry, no list command and no stored metadata, in line with "the code is the pipeline".
- The name is a file-name suffix beside the default; the exact pattern is a plan decision, but it must keep the default untouched.
- `Gold(candidates=None, *, name=None, path=None, sample_size=50)`: candidates become the first parameter and the others keyword-only, so the old positional `Gold(path)` stops working. The plan lists the callers to update. (The user asked for the candidates to be passed at creation; the order and keyword-only choice are mine.)
- A seed stays an optional argument of the three draw calls, because the docs and skills use one for reproducibility.
- The page names the split in its existing header or status text; no redesign (013 stays as built).
- "This pass" means the rows pending at the call, which needs no record of which draw created a row (no draw ids, no stored state).
- `gl.label(gold, taxonomy, split=...)` stays a function of the library; it does not become a `Gold` method in this change.
- Datasets are not merged, copied or compared.

## Deliberately skipped

- A dataset registry, listing command, config file or stored "current dataset": names are only file names.
- A `draw` alias or deprecation period: the library is pre-1.0 and the user asked for a rename.
- An `n=` override on `draw_sample`: change `sample_size` instead.
- An idempotent draw (a guard that makes re-running `draw_dev()` a no-op); the user's notebook keeps its own `if not gold.all.rows:` check.
- A `split=None` or "both" mode for the labelling page, a split picker, tabs or a dataset switcher in the page.
- Merging, copying or diffing datasets, and cross-dataset metrics.
- Moving rows between splits (beyond the existing `fold_test`) or between datasets.
- A third split, a validation split or custom split names.
- Migrating or renaming existing gold files; the default file stays where it is.
- Any change to how the classifier, cache, cost ledger or metrics work.
- Rewording the gold rule, and any new way to write a label.
