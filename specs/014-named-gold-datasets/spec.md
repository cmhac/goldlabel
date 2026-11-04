# Feature Specification: Samples: rerun-safe, seedless gold draws that label and evaluate one split, and named gold datasets

**Feature Branch**: `claude/sleepy-ritchie-ko69ta` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft

**Input**: User description: "Fix issues #22 and #23 and improve how gold labelling works." Issue #22, *Multiple gold datasets/separate evals*: "Users may want to set up multiple gold datasets for evaluation. For example, you might tune a prompt on one corpus, then want to apply it to another and just create a test set there without going through the dev/test workflow. Test is often sufficient in such cases. Need to be able to create separate, named golden datasets." Issue #23, *gold labeling not respecting draw's n parameter*: "I just ran a gold.draw with n=50, and the UI is showing 100. There's also a test draw in the notebook with another n=50, but not sure why the gold dataset is not treating those as separate." Follow-up decisions from the user (2026-11-04): the labelling page only shows the items being labelled in that pass; there is never a reason to label without a split; `Gold` takes the candidates when it is created and a `sample_size` (default 50) per split; `draw` becomes `draw_sample` with `draw_dev` and `draw_test` shortcuts, with a per-call size override; no `if not gold.all.rows:` guard and no seed numbers (option 3: a draw tops a split up to its size, in an order fixed by the row ids); the draw calls return a `Sample` that is passed to `gl.label` and to the evaluation; evaluation and the band check become methods of the classifier (`clf.evaluate(sample)`, `clf.band_sample(candidates)`), like `clf.classify` and `clf.estimate`.

## Where things are today

- **#23 is not a bug in the draw.** `gold.draw(candidates, n=50, split="dev")` writes exactly 50 rows. The user's notebook (`2026-11-04-trump-on-the-ballot-v2.ipynb`) then called `gl.label(gold, taxonomy)` with no `split`, which pages *every* row in the file, labelled or not, in both splits: one 50-row draw opened a page of 100 (the file already held 50 test rows), and the printed result was "GoldSet all: 100 rows". The README, the walkthrough and the stage skills all use that bare call.
- **A draw is an append.** Each `draw` adds `n` more rows. Re-running the cell, even with the same seed, appends a *different* 50 (rows already drawn are excluded, so the seeded shuffle runs over a smaller pool; checked on the current code: 0 overlap, 150 rows after three 50-row draws). So the notebook needed `if not gold.all.rows:` and `if not any(r.split == "test" ...)` guards, and a seed per draw for reproducibility, which also changes meaning whenever the candidates change.
- **The draw's result is easy to drop.** `draw` returns the drawn rows, but every example ignores it and then passes the whole `gold` plus a split to `gl.label` and `gold.dev` / `gold.test` (labelled rows only, a snapshot) to `gl.evaluate`. The notebook reloaded `gl.Gold()` twice "so the new rows show", though every `Gold` property already re-reads the file.
- **#22.** A `Gold` is one file (`gold.jsonl` under the root, or any path passed in). A second corpus can already get its own file by passing a path, but nothing says so, and the evaluation log is shared: "the test split was evaluated N times" and `fold_test`'s "evaluated since the last fold" check count test evaluations from *every* gold file (each log line records the gold file; those checks ignore it).
- **Evaluation is the odd one out.** `clf.classify(items)` and `clf.estimate(items)` are classifier methods, but evaluation is `gl.evaluate(clf, gold_set)` / `gl.aevaluate(...)` and the per-band off-topic check is `gl.band_sample(clf, candidates)`: library functions that take the classifier as an argument. These three are the only public functions that do.
- **A partly labelled test split can be evaluated.** `evaluate` skips pending rows and counts them, so a test split can be scored, and so spent, before people finish labelling it; the notebook guarded this with an `assert`.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Draw a split and get a Sample back; rerunning is harmless (Priority: P1)

A user creates the gold dataset once with its candidates (and optionally a `sample_size`, default 50, per split). `dev = gold.draw_dev()` makes sure the dev split has `sample_size` rows, drawing only what is missing, and returns a **Sample**: the dev split of this dataset. Re-running the cell draws nothing and returns the same Sample, saying so in one line. The rows come in an order fixed by their ids (and the dataset's name), so there is no seed: a colleague who runs the notebook from scratch over the same candidates gets the same rows, and widening the candidates later does not move the rows already drawn. `draw_test()` does the same for the test split, and `draw_sample(split, n=None)` is the general call underneath. Passing `n` asks for a different total for that split in that call; it never changes `sample_size`.

**Why this priority**: it removes the guards, the seeds and the dropped return value at once, and every later story builds on the Sample.

**Independent Test**: over a hand-built set of 200 candidates, `draw_dev()` twice returns 50 dev rows both times and the file holds 50; `draw_test()` adds 50 test rows with no id in dev; `draw_dev(n=80)` adds 30; `draw_dev(n=30)` adds none and says the split already has 80; a second fresh `Gold` over the same candidates draws the same 50 dev ids; adding 20 candidates and redrawing on a fresh file keeps every one of those 50 ids that is still a candidate in the first 50 positions it can.

**Acceptance Scenarios**:

1. **Given** a `Gold` with candidates and no rows, **When** `draw_dev()` is called, **Then** 50 pending dev rows are appended and a Sample for dev is returned whose summary says 50 were drawn now.
2. **Given** the dev split already has 50 rows, **When** `draw_dev()` is called again, **Then** nothing is written and the returned Sample says "dev has 50 rows; nothing drawn".
3. **Given** dev has 50 rows, **When** `draw_dev(n=80)` is called, **Then** 30 more are drawn (the shortfall), `sample_size` stays 50, and a later `draw_dev()` draws nothing.
4. **Given** dev has 80 rows, **When** `draw_dev(n=30)` is called, **Then** nothing is drawn or removed, and the Sample says the split already has 80, more than asked.
5. **Given** dev was drawn, **When** `draw_test()` is called, **Then** its rows never include a dev row (or any row already in the file).
6. **Given** two fresh `Gold` objects with the same name over the same candidates, **When** each draws dev, **Then** they draw the same ids; **Given** different names, **Then** their orders differ.
7. **Given** a split whose rows were removed with `gold.remove(ids)`, **When** its draw is called, **Then** it draws replacements up to the size and says how many it drew.
8. **Given** fewer unused candidates than the shortfall, **When** a draw is called, **Then** it writes nothing and fails naming how many are available and how many are needed.
9. **Given** a `sample_size` or `n` below 1 or not a whole number, or a `draw_sample` split that is not `dev` or `test`, **Then** the call is refused before anything is written.
10. **Given** a `Gold` created without candidates, **When** a draw is attempted, **Then** it fails saying to give the candidates when creating the `Gold`; reading, labelling, evaluating and folding still work.
11. **Given** the old `gold.draw(candidates, n, split, seed)`, **Then** it no longer exists; every doc, skill, example and test uses the new calls.

---

### User Story 2 - Label a Sample: the page shows only the rows of this pass (Priority: P1)

The user passes the Sample to the labelling call: `gl.label(dev, taxonomy)`. The page shows exactly the pending rows of that split: "x of 50", the split named on the page. Rows already labelled (an earlier pass) and rows of the other split are neither counted nor paged. A **pass** is the set of rows pending in the Sample's split when `gl.label` is called; its total stays fixed for the pass and **Back** can return to rows labelled earlier in it. There is no split argument any more: the Sample carries it, so a page can never mix dev and test.

**Why this priority**: this is issue #23 and the user's stated intent ("the UI only shows the items being labelled in that pass").

**Independent Test**: build a gold file by hand with 50 labelled dev rows and 50 pending test rows; start the labelling server for the test Sample and check the state reports 50 total, 0 done, split `test`, and never serves a dev row; for the dev Sample, check 012's "nothing to label" line and no server.

**Acceptance Scenarios**:

1. **Given** 50 labelled dev rows and 50 pending test rows, **When** `gl.label(test, taxonomy)` is called, **Then** the total is 50, progress counts only those rows, the page names "test", and no dev row is served.
2. **Given** a pass of 50 pending rows of which 20 get labelled, **When** the call is made again, **Then** the new pass is the 30 still pending, total 30.
3. **Given** `draw_dev(n=80)` added 30 rows to a fully labelled dev split, **When** `gl.label(dev, taxonomy)` is called, **Then** the pass is those 30.
4. **Given** no pending row in the Sample and no `force_open_ui`, **When** `gl.label` is called, **Then** it prints 012's one line, starts no server, and returns the Sample.
5. **Given** `force_open_ui=True`, **When** the call is made, **Then** the pass is every row of the Sample's split, labelled or not (review and relabel, as 012 intended).
6. **Given** a `Gold` or anything other than a Sample, **When** `gl.label` is called with it, **Then** it is refused with a message showing the `gold.draw_dev()` / `gold.dev` form.
7. **Given** two Samples from different datasets, **When** each is labelled, **Then** each uses its own dataset's file and lock.

---

### User Story 3 - The classifier evaluates a Sample; a test Sample must be fully labelled (Priority: P1)

The user evaluates the same Sample with the classifier, the way they classify with it: `clf.evaluate(dev, target=0.95)` (and `await clf.aevaluate(...)`, like `classify` / `aclassify`). `gl.evaluate` and `gl.aevaluate` are removed. The Sample reads the file when it is used, so the labels saved by the page a moment ago are there, with no reload. A dev Sample with pending rows is scored on its labelled rows, with the pending ones counted as skipped, as today. A test Sample with any pending row is refused, because scoring a half-labelled test split spends it. `gold.dev` and `gold.test` return the same Samples without drawing, for a notebook that only reads.

**Why this priority**: the Sample is only clearer than today if the same object goes to `label` and `evaluate`; the test refusal replaces the notebook's `assert` and protects the "test once" discipline.

**Independent Test**: label 50 dev rows over the simulated HTTP labeller (as `tests/test_e2e.py` does), then evaluate the same Sample object made before labelling and check 50 rows were scored with one `FunctionModel` call each. Leave one test row pending and check `evaluate` on the test Sample raises and makes no model call and writes no log line.

**Acceptance Scenarios**:

1. **Given** a Sample made before labelling, **When** it is evaluated after the page saved labels, **Then** the new labels are used.
2. **Given** a dev Sample with 10 pending rows of 50, **When** it is evaluated, **Then** 40 are scored and 10 counted as skipped, as today.
3. **Given** a test Sample with any pending row, **When** it is evaluated, **Then** it is refused with the number pending, before any model call or log line.
4. **Given** `gold.dev` / `gold.test`, **Then** they return the Sample of that split (including pending rows), equal to what `draw_dev()` / `draw_test()` returns once nothing is missing.
5. **Given** the test Sample was evaluated, **Then** the log line names its dataset's gold file and split, as today, which the per-dataset counts (US5) use.
6. **Given** `fold_test` moved the test rows to dev, **When** an existing test Sample is shown, **Then** it has 0 rows; `draw_test()` then draws a fresh one.
7. **Given** `clf.evaluate(sample, metric=..., target=..., log=...)`, **Then** it takes the same keyword options and returns the same `Evaluation`, and writes the same log line, as `gl.evaluate(clf, ...)` does today; `clf.aevaluate` is its async form and the sync form works inside a running notebook loop.
8. **Given** the old `gl.evaluate(clf, ...)` / `gl.aevaluate(clf, ...)`, **Then** they no longer exist (not exported); every doc, skill, example and test uses the method.
9. **Given** `clf.band_sample(candidates, per_band=30, seed=None)`, **Then** it returns the same `BandReport` as `gl.band_sample(clf, candidates, ...)` does today (same refusal for keyword or whole-corpus candidates, nothing written); `gl.band_sample` no longer exists.

---

### User Story 4 - A second, separately named gold dataset (Priority: P1)

A user tuned a prompt on corpus A. They apply it to corpus B and only want a test set there: `gold_b = gl.Gold(candidates_b, name="corpus-b")`, `test_b = gold_b.draw_test(n=30)`, label it, `clf.evaluate(test_b)`. A's dataset is untouched; B's rows, labels, counts, page, lock and evaluations never mix with A's. A dataset with only a test split (or only dev) needs no dev/test ceremony.

**Why this priority**: this is issue #22.

**Independent Test**: create two named datasets in one temporary root, give both a row with the same id, label them differently, check each reads back its own rows, that the unnamed `Gold` is still the single `gold.jsonl`, and that two labelling sessions can run at once.

**Acceptance Scenarios**:

1. **Given** no name, **When** a `Gold` is created, **Then** it is the same file as today, so existing gold files keep working.
2. **Given** a name, **Then** its file sits beside the default one, derived from the name; an explicit path wins over a name (the name still sets the draw order and the summary label).
3. **Given** two datasets, **When** a row id is drawn into one that the other already holds, **Then** the draw succeeds (ids are unique per dataset).
4. **Given** a dataset drawn only with `draw_test`, **When** its test Sample is evaluated, **Then** it works with no dev rows.
5. **Given** a name that is empty or has characters other than letters, digits, `-` and `_`, **Then** `Gold` refuses it.
6. **Given** a dataset or Sample, **When** it is printed, **Then** its dataset name (or "default") appears with its counts.
7. **Given** two datasets, **Then** each has its own lock; the same dataset still refuses a second concurrent session.

---

### User Story 5 - Evaluations and folds count per dataset (Priority: P2)

Evaluating B's test Sample does not touch A's "test evaluated N times" line or A's `fold_test` check. Each dataset's history is its own view of the shared, append-only log.

**Why this priority**: without it US4 is wrong in a quiet way: "evaluate the test split once" and the fold guard (constitution 1.2.0) would be measured across datasets.

**Independent Test**: log a test evaluation against B's path, check that A's count is zero and A's `fold_test` still refuses with "has not been evaluated since the last fold"; log one against A and check it counts.

**Acceptance Scenarios**:

1. **Given** test evaluations for two gold files, **When** the log is shown for one dataset, **Then** the test count is only that dataset's.
2. **Given** a test evaluation for B only, **When** A's `fold_test` is called, **Then** it refuses.
3. **Given** a fold on A, **Then** B's counts are unchanged (the `test_folded` event records its dataset).
4. **Given** an older log whose fold events carry no dataset, **Then** the event counts for the default dataset and nothing fails.

---

### User Story 6 - The docs and skills teach the Sample flow (Priority: P2)

An agent following the stage skills writes `gold = gl.Gold(candidates)`, `dev = gold.draw_dev()`, `gl.label(dev, taxonomy)`, `clf.evaluate(dev, ...)`, then the same for test, with no guards, seeds or reloads, and knows a second corpus gets a second named `Gold`, usually test-only.

**Independent Test**: the drift tests (`tests/test_skills.py`, `tests/test_skill_stages.py`, `tests/test_docs.py`) pass with the changed examples, and a check fails when an example calls `.draw(`, passes `seed=` to a draw, calls `gl.label` with a `Gold`, or calls `gl.evaluate(` or `gl.band_sample(`.

**Acceptance Scenarios**:

1. **Given** the README, the walkthrough (notebook and script), the overview skill's references, the stage skills and `docs/agent-instructions.md`, **Then** they use the Sample flow.
2. **Given** `goldlabel-tune` and `goldlabel-run`, **When** the user wants to apply a tuned prompt to another corpus, **Then** they say to create a named `Gold` over it, `draw_test()`, label, evaluate once.
3. **Given** the gold rule, **Then** `src/goldlabel/gold_rule.md` and every copy are unchanged, and nothing adds a way to set a label.

---

### Edge Cases

- A gold file written before this feature still loads, labels, evaluates and folds; its rows stay as drawn, and only later top-ups use the id order.
- A row id that is in the file but no longer a candidate stays in the split and counts toward its size.
- The id order is the same on every machine and Python version (it does not depend on Python's per-process string hashing).
- A Sample never caches rows; a variable made before labelling, a fold or a top-up shows the file as it is now.
- The default dataset and one named "gold" must not collide: `gold.jsonl` stays the default.
- `remove` writes `<file>.removed.jsonl` per dataset.
- A row drawn into the file by another process after a labelling pass began is not added to that pass.
- `force_open_ui=True` on a test Sample lets a person relabel test rows; it does not evaluate anything.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `Gold` MUST accept the candidates when it is created (optional, needed only to draw) and a `sample_size` (default 50, a whole number of at least 1), the default size of each split. A draw without candidates MUST fail saying where to give them.
- **FR-002**: `Gold.draw_sample(split, n=None)` MUST replace `Gold.draw`: it makes the split (`"dev"` or `"test"`, required) hold at least `n` rows (`sample_size` when `n` is not given), drawing only the shortfall from candidates not already in the file, writing nothing when there is no shortfall or not enough candidates, and never removing rows; an `n` override never changes `sample_size`. `draw_dev(n=None)` and `draw_test(n=None)` MUST call it. `draw` MUST be removed (no alias).
- **FR-003**: The draw order MUST be fixed by each candidate's id and the dataset's name, the same on every machine; there is no seed argument. Rows already drawn never move when the candidates change.
- **FR-004**: Every draw call MUST return a **Sample** for its split; `gold.dev` and `gold.test` MUST return the same Samples without drawing. A Sample MUST read its dataset's file each time it is used, MUST hold no labels of its own, and its summary MUST give the dataset name, split, rows, labelled, pending, and how many the call that made it drew.
- **FR-005**: `gl.label(sample, taxonomy)` MUST take a Sample and no split argument; anything else is refused with a message showing the Sample form. A pass MUST page and count only the rows pending in the Sample's split at the call (every row of that split with `force_open_ui=True`), never the other split; its total is fixed for the pass. It returns the Sample.
- **FR-006**: The labelling page MUST show which split it is labelling, and its "x of N" MUST count only the rows of this pass.
- **FR-007**: Evaluation MUST be a classifier method, `clf.evaluate(sample, *, metric=None, target=None, log=None)` with the async form `clf.aevaluate(...)`, keeping today's options, result and log line; `gl.evaluate` and `gl.aevaluate` MUST be removed (no alias). `gl.band_sample(clf, candidates, ...)` MUST likewise become `clf.band_sample(candidates, *, per_band=30, seed=None)` with today's behaviour, and be removed from the package. Evaluation MUST accept a Sample (and the `GoldSet` views that exist today) and use the labels in the file at that moment. A test Sample with any pending row MUST be refused before any model call or log line; a dev Sample keeps today's skip-and-count behaviour.
- **FR-008**: A user MUST be able to create a gold dataset by name; the name selects a file beside the default one, and an unnamed `Gold` MUST remain the existing default file. A name MUST be refused if it is empty or contains anything other than letters, digits, `-` and `_`.
- **FR-009**: Each dataset MUST have its own rows, lock, removed-rows file and labelling session; the "id is not already in the file" rules of drawing and `import_rows` MUST apply per dataset.
- **FR-010**: A dataset MUST be usable with only one split, with no message implying the other is missing.
- **FR-011**: The test-evaluation count and `fold_test`'s "evaluated since the last fold" check MUST consider only evaluations logged for that dataset's gold file; `test_folded` events MUST record their dataset; reading an older log MUST not fail.
- **FR-012**: The README, the walkthrough (notebook and script), `goldlabel` references, the stage skills and `docs/agent-instructions.md` MUST use the Sample flow and describe the second-corpus, test-only case; a drift test MUST fail when an example calls `.draw(`, passes `seed=` to a draw, passes a `Gold` to `gl.label`, or calls `gl.evaluate(` or `gl.band_sample(`.
- **FR-013**: Nothing in this change MAY add a way to write a gold label or alter `gold_rule.md`; only the labelling server and `Gold.import_rows` write labels. A Sample has no way to set a label.

### Key Entities

- **Gold dataset**: one file of human-labelled rows, with an optional name (which also fixes its draw order), the candidates it samples from, and a sample size per split. Its rows are dev or test; it may hold either or both.
- **Sample**: a live view of one split of one dataset: what a draw returns, what `gl.label` takes and what `clf.evaluate` scores. It reads the file when used and stores nothing.
- **Pass**: the pending rows of a Sample's split at the moment `gl.label` is called.
- **Evaluation log**: one append-only file shared by all datasets; each line already names its gold file, which separates the datasets' histories.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A notebook's whole gold section is `gold = gl.Gold(candidates)`, then per split one draw, one label and one `clf.evaluate` call, with no guard, seed or reload, and running it top to bottom twice leaves the gold file identical after the second run.
- **SC-002**: A user who draws dev and labels it sees "of 50"; after drawing test, the page for test shows "of 50" (not 100) with no dev row, in 100% of tests covering that flow, including a rerun against a file that already holds both splits.
- **SC-003**: Two people who run the same notebook over the same candidates from an empty gold directory draw the same rows.
- **SC-004**: Scoring a test Sample with a pending row is refused in 100% of tests, with no model call.
- **SC-005**: A second dataset over another corpus can be drawn, labelled and scored without reading or editing the first dataset's file; the first dataset's counts, evaluation count and fold eligibility are identical before and after.
- **SC-006**: Every gold file written before this feature loads and behaves as before; no example calls `.draw(`, passes a draw `seed=`, passes a `Gold` to `gl.label`, or calls `gl.evaluate(`, and a test fails when one does.

## Assumptions

- "Named dataset" means a name that picks a file and salts the draw order; no registry, list command or stored metadata, in line with "the code is the pipeline".
- `Gold(candidates=None, *, name=None, path=None, sample_size=50)`: candidates become the first parameter and the others keyword-only, so the old positional `Gold(path)` stops working; the plan lists the callers to update.
- `n` means "this split should hold at least `n` rows", not "add `n`"; asking for less than the split holds draws and removes nothing.
- `Sample` is the class name the user proposed. It is unrelated to `gl.band_sample` (the classifier's per-band check) and to `Candidates.sample`; the docs name it "a Sample of the gold set" where that could confuse.
- `gold.dev` / `gold.test` change from a snapshot of labelled rows to a live Sample that includes pending rows; `evaluate` already skips pending dev rows, so dev scores do not change.
- `gold.pending`, `gold.all`, `orphaned`, `remove`, `import_rows` and `fold_test` keep returning a `GoldSet` (a snapshot); only the per-split views become Samples.
- The page names the split in its existing header or status text; no redesign (013 stays as built).
- `gl.label` stays a library function taking the Sample; it does not become a Sample method in this change.
- `gl.eval_log()` stays a library function (it reads the log and takes no classifier); evaluation and `band_sample`, the only public functions that take a classifier, move onto it, as the user asked.
- Evaluation is pre-1.0 public API used by `Classifier.save(dir, evaluation=...)` callers and the bundle tests; those keep working with the `Evaluation` the method returns.

## Deliberately skipped

- A seed or `salt=` argument for "a different random sample": change the dataset's name instead.
- An append-style draw ("add 10 more"): ask for a bigger total.
- Drawing inside `gl.label`, or drawing both splits at `Gold` creation.
- A draw record or "draw key" stored on rows.
- A `draw` or `gl.evaluate` alias or deprecation period, and the old `gl.label(gold, taxonomy, split=...)` form.
- An async `aband_sample` (it has none today) and dropping `band_sample`'s seed; both are open questions for the user.
- A dataset registry, listing command, config file or stored "current dataset".
- A split picker, tabs or a dataset switcher in the page.
- Merging, copying or diffing datasets, and cross-dataset metrics.
- Moving rows between splits (beyond `fold_test`) or between datasets.
- A third split or custom split names.
- Migrating or renaming existing gold files.
- Any change to the classifier, cache, cost ledger or metrics.
- Rewording the gold rule, and any new way to write a label.
