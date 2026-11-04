# Feature Specification: Named samples, rerun-safe seedless draws, evaluations on the classifier, and named gold datasets

**Feature Branch**: `claude/sleepy-ritchie-ko69ta` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft (constitution amended to 1.3.0 for it)

**Input**: User description: "Fix issues #22 and #23 and improve how gold labelling works." Issue #22, *Multiple gold datasets/separate evals*: "Users may want to set up multiple gold datasets for evaluation. For example, you might tune a prompt on one corpus, then want to apply it to another and just create a test set there without going through the dev/test workflow. Test is often sufficient in such cases. Need to be able to create separate, named golden datasets." Issue #23, *gold labeling not respecting draw's n parameter*: "I just ran a gold.draw with n=50, and the UI is showing 100. There's also a test draw in the notebook with another n=50, but not sure why the gold dataset is not treating those as separate."

Decisions from the user in the conversation of 2026-11-04, in order:

1. The labelling page shows only the items being labelled in that pass, and never mixes dev and test.
2. `Gold` takes the candidates when it is created, and a `sample_size` (default 50) per sample.
3. `draw` becomes `draw_sample`, with `draw_dev` and `draw_test` shortcuts and a per-call size override.
4. No `if not gold.all.rows:` guards and no seed numbers: a draw tops its sample up to its size, in an order fixed by the row ids.
5. The draw calls return a Sample, which `gl.label` and the evaluation take.
6. Evaluation and the band check are classifier methods (`clf.evaluate`, `clf.band_sample`); the band check has no seed and gets an async form.
7. Everything is saved in the one storage folder, with no option to switch it off or send a file elsewhere: `log=False` and `log=<path>` go, `Gold(path=)` goes, and `gl.eval_log` is removed entirely.
8. `fold_test` is removed. Samples are named, and a spent test sample is folded into tuning by adding Samples with `+`; the docs say how and when.

## Where things are today

- **#23 is not a bug in the draw.** `gold.draw(candidates, n=50, split="dev")` writes exactly 50 rows. The user's notebook (`2026-11-04-trump-on-the-ballot-v2.ipynb`) then called `gl.label(gold, taxonomy)` with no `split`, which pages every row in the file, labelled or not, in both splits: one 50-row draw opened a page of 100. The README, the walkthrough and the stage skills all use that bare call.
- **A draw is an append.** Rerunning a `draw` cell, even with the same seed, appends a different 50 rows (checked on the current code: 0 overlap, 150 rows after three 50-row draws). The notebook needed guards, and a seed per draw, whose meaning changes whenever the candidates change.
- **The draw's result is dropped.** Every example ignores what `draw` returns, then passes the whole `gold` and a split to `gl.label`, and a snapshot (`gold.dev`) to `gl.evaluate(clf, ...)`, while `clf.classify` and `clf.estimate` are methods.
- **The log can be bypassed.** `log=False` writes nothing and `log=<path>` writes where `fold_test` and `gl.eval_log()` never look, so a test split can be scored off the record. Every rerun of a test evaluation adds a line and raises the "evaluated N times" count even when nothing changed.
- **`fold_test` is unclear and unsafe to rerun.** It takes nothing, so the code does not say what moves. After a fold, "the test split" means other rows, so rerunning the notebook scores the fresh test rows with the old prompt and can fold them a second time.
- **#22.** A second gold file needs a path, the docs never say so, and the evaluation history is counted across every gold file.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Draw a named sample and get it back; rerunning does nothing (Priority: P1)

A user creates the gold dataset once: `gold = gl.Gold(candidates)`. `dev = gold.draw_dev()` makes sure the sample named "dev" holds `sample_size` rows, drawing only what is missing, and returns that Sample. `test = gold.draw_test()` does the same for the sample named "test". A second test sample later is `gold.draw_test("test-2")`. Each sample is a fixed set of rows inside the dataset, so rerunning any draw cell, at any point in the notebook's life, draws nothing and returns the same rows. Rows come in an order fixed by their ids and the dataset's name, so there is no seed, a colleague running the notebook from scratch over the same candidates gets the same rows, and widening the candidates does not move rows already drawn. `n` asks for a different size for that sample in that call; it never changes `sample_size`. `gold["test-2"]` returns a sample without drawing.

**Why this priority**: it removes the guards, the seeds and the dropped return value, and every later story uses the Sample.

**Independent Test**: over 200 hand-built candidates, `draw_dev()` twice gives 50 dev rows and a 50-row file; `draw_test()` adds 50 with no id in dev; `draw_test("test-2")` adds 50 more, none in either; `draw_dev(n=80)` adds 30; `draw_dev(n=30)` adds none; a fresh `Gold` over the same candidates in another folder draws the same dev ids; adding candidates and drawing on a fresh file keeps every id still present that was drawn before.

**Acceptance Scenarios**:

1. **Given** a `Gold` with candidates and no rows, **When** `draw_dev()` is called, **Then** 50 pending rows in the dev sample "dev" are written and the returned Sample says 50 were drawn now.
2. **Given** "dev" holds 50 rows, **When** `draw_dev()` is called again, **Then** nothing is written and the Sample says "nothing drawn".
3. **Given** "dev" holds 50, **When** `draw_dev(n=80)` is called, **Then** 30 more are drawn and `sample_size` stays 50; **Given** it holds 80, **When** `draw_dev(n=30)` is called, **Then** nothing is drawn or removed.
4. **Given** "test" exists, **When** `draw_test("test-2")` is called, **Then** a separate test sample of 50 is drawn from candidates in no sample, and "test" is unchanged.
5. **Given** a sample name already used by the other split (for example `draw_dev("test")`), or a name that is empty or has characters other than letters, digits, `-` and `_`, **Then** the call is refused and nothing is written.
6. **Given** two fresh datasets with the same name over the same candidates, **Then** they draw the same ids; different dataset names give different orders.
7. **Given** rows of a dev sample were removed with `gold.remove(ids)`, **When** its draw is rerun, **Then** it draws replacements and says how many.
8. **Given** a spent test sample (US3) that is short of its size, **When** its draw is called, **Then** it is refused: a spent test sample never gains rows; draw a new, named test sample instead.
9. **Given** fewer unused candidates than the shortfall, **Then** the draw writes nothing and fails with both numbers; **Given** `sample_size` or `n` that is not a whole number of at least 1, **Then** it is refused.
10. **Given** a `Gold` with no candidates, **When** a draw has no shortfall, **Then** it works; **When** it has one, **Then** it fails saying to give the candidates when creating the `Gold`.
11. **Given** `gold["test-2"]`, **Then** it returns that sample without drawing; an unknown name raises `KeyError` listing the sample names.
12. **Given** the old `gold.draw(...)`, `gold.dev`, `gold.test`, `gold.fold_test()` or `Gold(path=...)`, **Then** they no longer exist.

---

### User Story 2 - Label a Sample: the page shows only the rows of this pass (Priority: P1)

`gl.label(dev, taxonomy)` opens the page on exactly the rows of that Sample that are pending when it is called: "x of 50", with the sample's name and split on the page. Rows already labelled and rows of other samples are neither counted nor paged. The total stays fixed for the pass, and Back can return to rows labelled earlier in it. There is no split argument: the Sample carries it.

**Why this priority**: this is issue #23 and decision 1.

**Independent Test**: a hand-built file with 50 labelled "dev" rows and 50 pending "test" rows: the server for the test Sample reports total 50, done 0, sample "test", split "test", and never serves a dev row; for the dev Sample, 012's "nothing to label" line and no server.

**Acceptance Scenarios**:

1. **Given** 50 labelled dev rows and 50 pending test rows, **When** `gl.label(test, taxonomy)` is called, **Then** the total is 50, progress counts only those rows, the page names "test", and no dev row is served.
2. **Given** a pass of 50 of which 20 get labelled, **When** the call is made again, **Then** the pass is the 30 still pending.
3. **Given** `draw_dev(n=80)` added 30 rows to a labelled "dev", **When** `gl.label(dev, taxonomy)` is called, **Then** the pass is those 30.
4. **Given** nothing pending and no `force_open_ui`, **Then** 012's one line is printed, no server starts, and the Sample is returned.
5. **Given** `force_open_ui=True`, **Then** the pass is every row of the Sample, labelled or not (review and relabel).
6. **Given** anything that is not a Sample (a `Gold`, a `GoldSet`), **Then** `gl.label` refuses it with a message showing the `gold.draw_dev()` form.
7. **Given** Samples from two datasets, **Then** each is labelled in its own file under its own lock.

---

### User Story 3 - The classifier evaluates a Sample; a test sample is scored once (Priority: P1)

`clf.evaluate(dev, target=0.95)` (and `await clf.aevaluate(...)`) scores the Sample's labelled rows as they are in the file at that moment, so labels saved by the page a moment ago are used with no reload. Every evaluation is written to `evals.jsonl` beside the dataset's gold file, in the storage folder; there is no option to skip or move it. Only a Sample can be evaluated. An identical rerun (same dataset, same samples, same rows and labels, same prompt and model, same metric and target) returns the result and writes no second line, so rerunning a notebook adds nothing. A test sample on its own:

- with any pending row is refused;
- is **spent** after its first evaluation;
- once spent, is refused under any other prompt, model or labels (an identical rerun still returns its result).

A Sample's summary says whether it was evaluated and whether it is spent.

**Why this priority**: decisions 5 to 7, and the constitution's "test once" rule (1.3.0), enforced in code.

**Independent Test**: label 50 dev rows over the simulated HTTP labeller, then evaluate the Sample made before labelling: 50 rows scored, one `FunctionModel` call each, one log line. Evaluate again: zero calls, still one line. Leave a test row pending: refused, zero calls, no line. Label it, evaluate the test sample: one line, spent. Evaluate it with another prompt: refused, zero calls, no line.

**Acceptance Scenarios**:

1. **Given** a Sample made before labelling, **When** it is evaluated after the page saved labels, **Then** the new labels are used.
2. **Given** a dev Sample with 10 pending of 50, **Then** 40 are scored and 10 counted as skipped, as today.
3. **Given** the same evaluation twice, **Then** the second returns an equal result, writes no line and makes no model call.
4. **Given** the same Sample and prompt with a new `target`, **Then** a new line is written (it is a different record) but a test sample's spent state does not change.
5. **Given** a test sample with a pending row, **Then** evaluating it is refused with the number pending, before any model call or line.
6. **Given** a spent test sample, **When** it is evaluated alone with another prompt or model, or after a label in it changed, **Then** it is refused with a message that says it is spent and shows the combine-and-redraw steps (US4).
7. **Given** `clf.evaluate(..., log=...)`, **Then** there is no such argument; `gl.evaluate`, `gl.aevaluate` and `gl.eval_log` no longer exist.
8. **Given** `clf.band_sample(candidates, per_band=30)` and `await clf.aband_sample(...)`, **Then** they return a `BandReport` as `gl.band_sample` does today, picking per-band rows in the id-fixed order (no seed; a rerun picks the same rows), refusing non-seed candidates, and writing no log line (a band check is not an evaluation against gold).

---

### User Story 4 - Fold a spent test sample into tuning by adding Samples (Priority: P1)

After a disappointing test score, if the user says yes to keep tuning, the spent test rows join the set they tune on, in plain sight:

```python
tuning = dev + test                  # nothing is written; no label or split changes
test_2 = gold.draw_test("test-2")    # a fresh test sample
gl.label(test_2, taxonomy)
clf2.evaluate(tuning, target=0.95)   # tune on 100 rows
clf2.evaluate(test_2, target=0.95)   # scored once
```

Adding Samples gives a combined Sample over the union of their rows (same dataset only). A test sample may join a combination only when it is fully labelled and spent, so a combination can never be used to peek at a fresh test sample. A combination is a tuning set: evaluating it is never a test evaluation and never spends anything. The docs and skills say when this is honest (only after the user's explicit yes, only with a spent test sample) and how to do it.

**Why this priority**: decision 8; it replaces `fold_test` and is what makes the whole notebook safe to rerun.

**Independent Test**: with "dev" (50, labelled) and a spent "test" (50), `dev + test` has 100 rows and the gold file is byte-identical before and after; `dev + test_2` with "test-2" unspent is refused; evaluating `dev + test` under a new prompt writes one line naming both samples and leaves "test" spent and "test-2" untouched; running the whole notebook chain twice leaves the gold file identical and makes no model call the second time.

**Acceptance Scenarios**:

1. **Given** labelled "dev" and spent "test", **When** `dev + test` is made, **Then** it has the union of their rows, its summary names both, and nothing is written.
2. **Given** an unspent or partly labelled test sample, **When** it is added to anything, **Then** it is refused with a message saying a test sample joins tuning only after it is scored.
3. **Given** Samples from two datasets, **When** they are added, **Then** it is refused.
4. **Given** `dev + dev`, or a sample added twice, **Then** each row appears once.
5. **Given** a combination, **When** it is labelled, **Then** the pass is its pending rows (normally none, or new dev rows).
6. **Given** a combination is evaluated, **Then** the log line names every sample in it, and no test sample's spent state changes.

---

### User Story 5 - A second, separately named gold dataset (Priority: P1)

To apply a tuned prompt to another corpus with only a test set there: `gold_b = gl.Gold(candidates_b, name="corpus-b")`, `test_b = gold_b.draw_test(n=30)`, label it, `clf.evaluate(test_b)`. Corpus A's dataset is untouched; B's rows, labels, samples, page, lock and evaluation history never mix with A's.

**Why this priority**: issue #22.

**Independent Test**: two datasets in one temporary folder, the same id in both labelled differently: each reads back its own rows; the unnamed `Gold` is still `gold.jsonl`; two labelling sessions run at once; a test evaluation of B leaves A's "test" unspent.

**Acceptance Scenarios**:

1. **Given** no name, **Then** the dataset is `<root>/gold.jsonl`, as today, so existing gold files keep working.
2. **Given** a name, **Then** the dataset is `<root>/gold-<name>.jsonl`; the name follows the sample-name rule and also fixes the draw order.
3. **Given** two datasets, **Then** a row id may be in both, and each has its own lock and removed-rows file.
4. **Given** a dataset with only a test sample, **Then** it is labelled and evaluated with no dev sample present.
5. **Given** a test evaluation of B, **Then** A's samples' evaluated and spent states are unchanged (the history is read per gold file).

---

### User Story 6 - The docs and skills teach the Sample flow (Priority: P2)

An agent following the stage skills writes `gold = gl.Gold(candidates)`, `dev = gold.draw_dev()`, `gl.label(dev, taxonomy)`, `clf.evaluate(dev, ...)`, then the same for test, with no guards, seeds, reloads or log options; folds only with the user's explicit yes, by `tuning = dev + test` and a newly named test sample; gives a second corpus its own named `Gold`; and reads the evaluation history, when the user wants it, from `evals.jsonl` as a plain file.

**Independent Test**: the drift tests (`tests/test_skills.py`, `tests/test_skill_stages.py`, `tests/test_docs.py`) pass with the changed examples, and a check fails when an example uses a removed name (`.draw(`, `fold_test`, `gl.evaluate(`, `gl.aevaluate(`, `gl.band_sample(`, `gl.eval_log(`, `log=`, `Gold(path`, `gl.label(gold`) or passes `seed=` to a draw.

**Acceptance Scenarios**:

1. **Given** the README, the walkthrough (notebook and script), the overview skill and its references, the stage skills, `docs/agent-instructions.md` and `.kiro/steering/goldlabel.md`, **Then** they use the Sample flow.
2. **Given** `goldlabel-tune` and `references/tuning.md`, **Then** they explain combining a spent test sample (when it is honest, the explicit yes, the exact calls) in place of `fold_test`.
3. **Given** `goldlabel-tune` and `goldlabel-run`, **Then** they describe the second-corpus, test-only case.
4. **Given** the gold rule, **Then** `src/goldlabel/gold_rule.md` and every copy are unchanged, and nothing adds a way to set a label.

---

### Edge Cases

- A gold file written before this feature has no sample names: each row belongs to the sample named after its split ("dev" or "test"); rows a past `fold_test` moved are simply dev rows. Its rows stay as drawn; only later top-ups use the id order.
- Old log lines name no samples: a line counts for the sample named after its split. Old `test_folded` events are ignored. A project whose "test" was evaluated before under some prompt is therefore spent: a new prompt on it is refused, and the user combines it and draws "test-2".
- A row id in the file that is no longer a candidate stays in its sample and counts toward its size.
- The id order is the same on every machine and Python version (it does not use Python's per-process string hashing).
- A Sample never caches rows; a variable made before labelling or a top-up shows the file as it is now.
- The default dataset and one named "gold" do not collide (`gold.jsonl` and `gold-gold.jsonl`).
- A row drawn by another process after a labelling pass began is not added to that pass.
- `force_open_ui=True` on a spent test sample lets a person correct a label; the sample stays spent, and evaluating it alone afterwards is refused (US3 scenario 6).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `Gold(candidates=None, *, name=None, sample_size=50)` MUST be the constructor; the file is `<root>/gold.jsonl` with no name or `<root>/gold-<name>.jsonl`; there MUST be no path argument. `sample_size` MUST be a whole number of at least 1.
- **FR-002**: A gold dataset MUST hold named samples, each a dev or a test sample. Every row MUST belong to one sample; a row with no sample name belongs to the sample named after its split. A sample name MUST match `[A-Za-z0-9_-]+` and MUST belong to only one split.
- **FR-003**: `gold.draw_sample(split, name=None, n=None)` MUST make the sample `name` (default: the split's name) of `split` (`"dev"` or `"test"`, required) hold at least `n` rows (default `sample_size`), drawing only the shortfall from candidates in no sample of the file, never removing rows, writing nothing if there is no shortfall or not enough candidates, and refusing to add rows to a spent test sample. `draw_dev(name=None, n=None)` and `draw_test(name=None, n=None)` MUST call it. Each MUST return the sample. `gold[name]` MUST return a sample without drawing. `draw`, the `dev`/`test` properties and `fold_test` MUST be removed.
- **FR-004**: The draw order MUST be fixed by each candidate's id and the dataset's name, the same on every machine; there MUST be no seed argument.
- **FR-005**: A Sample MUST be a live, read-only view of its rows (it reads the file when used and stores no labels), with a summary naming the dataset, sample(s), split, rows, labelled, pending, how many the call that made it drew, and whether it was evaluated and is spent; it MUST export `to_polars()` and `to_pandas()`.
- **FR-006**: `sample + sample` MUST return a combined Sample over the union of their rows, MUST refuse Samples of different datasets, and MUST refuse a test sample that is not fully labelled and spent. Combining MUST write nothing.
- **FR-007**: `gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)` MUST take a Sample (anything else refused) and page only the rows pending in it at the call (every row with `force_open_ui=True`), with a total fixed for the pass; the page MUST name the sample and split, and its "x of N" MUST count only the pass. It returns the Sample.
- **FR-008**: `clf.evaluate(sample, *, metric=None, target=None)` and `await clf.aevaluate(...)` MUST replace `gl.evaluate` and `gl.aevaluate`, and MUST accept only a Sample (a `GoldSet` such as `gold.all` is refused: scoring it would score test rows without the test rules). Every evaluation MUST be appended to `evals.jsonl` in the folder of the dataset's gold file (the storage folder), naming the gold file and the samples, except that an identical evaluation (same gold file, samples, row ids and labels, prompt digest, model, metric and target) already in the log MUST NOT be written again. There MUST be no argument to skip or move the log.
- **FR-009**: Evaluating a single test sample MUST be refused, before any model call or log line, when any of its rows is pending, or when it is spent and the prompt digest, model or labels differ from its first evaluation. A combined Sample MUST never count as a test evaluation.
- **FR-010**: `clf.band_sample(candidates, *, per_band=30)` and `await clf.aband_sample(...)` MUST replace `gl.band_sample`, pick rows in the id-fixed order with no seed, and write no log line.
- **FR-011**: `gl.eval_log` and `EvalLog` MUST be removed; whether a sample was evaluated and is spent MUST be read from the log per gold file and shown on the Sample.
- **FR-012**: Each dataset MUST have its own rows, lock, removed-rows file and labelling session; the "id not already in the file" rules of drawing and `import_rows` MUST apply per dataset. `import_rows(rows, split)` puts its rows in the sample named after the split.
- **FR-013**: The README, the walkthrough (notebook and script), the overview skill and references, the stage skills, `docs/agent-instructions.md` and `.kiro/steering/goldlabel.md` MUST use the Sample flow, MUST explain combining a spent test sample (with the explicit-yes rule) and the second-corpus case, and MUST NOT use a removed name; a drift test MUST fail when one does.
- **FR-014**: Nothing in this change MAY add a way to write a gold label or alter `gold_rule.md`; only the labelling server and `Gold.import_rows` write labels; a draw writes only pending rows and their sample name; combining writes nothing.

### Key Entities

- **Gold dataset**: one file in the storage folder, unnamed (`gold.jsonl`) or named (`gold-<name>.jsonl`), with its candidates and sample size; it holds named samples.
- **Sample**: a named set of rows of one split, or a combination of samples; what draws return and what `gl.label` and `clf.evaluate` take. Live, read-only.
- **Pass**: the pending rows of a Sample at the moment `gl.label` is called.
- **Evaluation log**: `evals.jsonl` beside the gold files in the storage folder, append-only, always written, shared by the datasets there; each line names its gold file and samples.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A notebook's whole gold section is `gold = gl.Gold(candidates)`, then per sample one draw, one label and one `clf.evaluate` call, with no guard, seed, reload or log option; running it top to bottom a second time, including after a fold by `+` and a second test sample, leaves the gold file and the log unchanged and makes no model call.
- **SC-002**: After a 50-row dev draw and a 50-row test draw, the page for each shows "of 50", never 100, and never a row of the other sample, in 100% of tests covering that flow.
- **SC-003**: Two people running the same notebook over the same candidates from an empty folder draw the same rows.
- **SC-004**: In 100% of tests, a test sample cannot be scored with a pending row, cannot be scored alone under a second prompt or model, and cannot join a combination before it is scored; none of the refusals makes a model call.
- **SC-005**: A second dataset over another corpus can be drawn, labelled and scored without touching the first; the first dataset's samples and their evaluated and spent states are identical before and after.
- **SC-006**: Every gold file and log written before this feature loads and behaves as described in the Edge Cases; no doc or skill example uses a removed name, and a test fails when one does.

## Assumptions

- The constitution is amended to 1.3.0 (Principle VI): `fold_test` is replaced by combining a spent test sample into the tuning set, every evaluation is always logged, and a test sample is scored alone once. The user approved this on 2026-11-04.
- "Named dataset" and "named sample" mean names that pick a file and group rows; no registry, list command or stored metadata.
- `n` means "this sample should hold at least `n` rows", not "add `n`".
- `GoldSet` stays for `gold.all`, `gold.pending`, `remove`, `import_rows` and `orphaned`; only per-sample views are Samples.
- `gl.label` stays a library function taking a Sample.
- The band check is not an evaluation against gold, so it writes no log line (the user's "everything saved" is about evaluations; say so if it should log too).
- Other places that choose or skip a file (`get_candidates(out=)`, `cache=`, `classify(out=)`, `clf.save(dir)` and `Classifier.load(dir)`, the explicit `read`/`write` helpers, changing `gl.settings.root` mid-notebook) are out of this feature, for a follow-up spec.

## Deliberately skipped

- A seed or salt argument: change the dataset's name for a different order.
- An append-style draw ("add 10 more"): ask for a bigger size.
- Drawing inside `gl.label`, or drawing samples at `Gold` creation.
- `sum()` of Samples, subtraction, or any set operation besides `+`.
- A sample-name argument on `import_rows`.
- Aliases or a deprecation period for any removed name.
- A dataset or sample registry, listing command or stored "current" anything.
- A history viewer to replace `gl.eval_log` (read `evals.jsonl` with polars).
- A split picker, tabs or a dataset switcher in the page.
- Merging, copying or diffing datasets, and moving rows between datasets.
- Migrating or renaming existing gold files or logs.
- Any change to the classifier, cache, cost ledger or metrics beyond moving evaluation and the band check onto the classifier.
- Rewording the gold rule, and any new way to write a label.
