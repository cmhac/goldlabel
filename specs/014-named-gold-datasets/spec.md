# Feature Specification: Named samples, one rerun-safe draw, evaluations on the classifier, and named gold datasets

**Feature Branch**: `claude/sleepy-ritchie-ko69ta` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Draft (constitution amended to 1.3.0 for it)

**Input**: User description: "Fix issues #22 and #23 and improve how gold labelling works." Issue #22, *Multiple gold datasets/separate evals*: "Users may want to set up multiple gold datasets for evaluation. For example, you might tune a prompt on one corpus, then want to apply it to another and just create a test set there without going through the dev/test workflow. Test is often sufficient in such cases. Need to be able to create separate, named golden datasets." Issue #23, *gold labeling not respecting draw's n parameter*: "I just ran a gold.draw with n=50, and the UI is showing 100. There's also a test draw in the notebook with another n=50, but not sure why the gold dataset is not treating those as separate."

Decisions from the user in the conversation of 2026-11-04 (the final ones; earlier drafts had more structure that the user removed):

1. The labelling page shows only the items being labelled in that pass.
2. `Gold` takes the candidates when it is created, and a `sample_size` (default 50).
3. One draw function, `gold.draw_sample(name, n=None)`, used every time. It tops the named sample up to its size, with no guard and no seed: the order is fixed by the row ids. It returns a Sample.
4. A sample is just a name the user chooses ("dev", "test", "test-2"). The library has no dev/test kinds and does not police samples; protecting a test set is the user's job. The library only reports how many times each sample was evaluated.
5. Samples combine with `+`, which is how a spent test set is folded into tuning; `fold_test` is removed. The docs say how and when.
6. `gl.label` and the evaluation take a Sample. Evaluation and the band check are classifier methods (`clf.evaluate`, `clf.band_sample`); the band check has no seed and gets an async form.
7. Everything is saved in the one storage folder, with no option to switch it off or send a file elsewhere: `log=False`, `log=<path>`, `Gold(path=)` and `gl.eval_log` are removed.
8. A dataset name (`gl.Gold(candidates, name="corpus-b")`) picks the gold file; a sample name tags rows inside it.

## Clarifications

### Session 2026-11-04

- Q: What is a gold row's sample name called in the gold file and in the Python and table views? → A: `sample` everywhere (file key, `row.sample`, the `sample` column), replacing `split`; goldlabel is early alpha, so nothing written before this feature (gold files, logs, bundles) is read or kept compatible, and there are no aliases or shims.

## Where things are today

- **#23 is not a bug in the draw.** `gold.draw(candidates, n=50, split="dev")` writes exactly 50 rows. The user's notebook (`2026-11-04-trump-on-the-ballot-v2.ipynb`) then called `gl.label(gold, taxonomy)` with no `split`. That call pages every row in the file, labelled or not, in both splits, so one 50-row draw opened a page of 100. The README, the walkthrough and the stage skills all use that bare call.
- **A draw is an append.** Rerunning a `draw` cell, even with the same seed, appends a different 50 rows (checked on the current code: 0 overlap, 150 rows after three 50-row draws). The notebook therefore needed guards and a seed per draw. A seed's meaning changes whenever the candidates change.
- **The draw's result is dropped.** Every example ignores what `draw` returns, then passes the whole `gold` and a split to `gl.label` and a snapshot (`gold.dev`) to `gl.evaluate(clf, ...)`. Meanwhile `clf.classify` and `clf.estimate` are methods.
- **The log can be bypassed.** `log=False` writes nothing, and `log=<path>` writes where `fold_test` and `gl.eval_log()` never look. Every rerun adds a line, even when nothing changed.
- **`fold_test` is unclear and unsafe to rerun.** It takes nothing, so the code does not say what moves. After a fold, "the test split" means other rows.
- **#22.** A second gold file needs a path, the docs never say so, and the evaluation history is counted across every gold file.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Draw a named sample and get it back; rerunning does nothing (Priority: P1)

A user creates the gold dataset once: `gold = gl.Gold(candidates)`. `dev = gold.draw_sample("dev")` makes sure the sample named "dev" holds `sample_size` rows. It draws only what is missing and returns that Sample. `gold.draw_sample("test")` and later `gold.draw_sample("test-2")` work the same way. A sample is a fixed set of rows in the dataset, tagged with its name in each row's `sample` field. Rerunning any draw cell, at any point in the notebook's life, therefore draws nothing and returns the same rows.

Rows come in an order fixed by their ids and the dataset's name. There is no seed. A colleague running the notebook from scratch over the same candidates gets the same rows, and widening the candidates does not move rows already drawn. `n` asks for a different size for that sample in that call and never changes `sample_size`. `gold["test-2"]` returns a sample without drawing.

**Why this priority**: it removes the guards, the seeds and the dropped return value, and every later story uses the Sample.

**Independent Test**: start from 200 hand-built candidates and check:

- `draw_sample("dev")` twice gives 50 rows and a 50-row file.
- `draw_sample("test")` adds 50 rows with no id in "dev".
- `draw_sample("test-2")` adds 50 more, in neither.
- `draw_sample("dev", n=80)` adds 30; `draw_sample("dev", n=30)` then adds none.
- A fresh `Gold` over the same candidates in another folder draws the same "dev" ids.
- Adding candidates and drawing on a fresh file keeps every previously drawn id that is still present.

**Acceptance Scenarios**:

1. **Given** a `Gold` with candidates and no rows, **When** `draw_sample("dev")` is called, **Then** 50 pending rows tagged "dev" are written and the returned Sample says 50 were drawn now.
2. **Given** "dev" holds 50 rows, **When** `draw_sample("dev")` is called again, **Then** nothing is written and the Sample says "nothing drawn".
3. **Given** "dev" holds 50, **When** `draw_sample("dev", n=80)` is called, **Then** 30 more are drawn and `sample_size` stays 50; **Given** it holds 80, **When** `draw_sample("dev", n=30)` is called, **Then** nothing is drawn or removed.
4. **Given** "test" exists, **When** `draw_sample("test-2")` is called, **Then** a separate sample of 50 is drawn from candidates in no sample, and "test" is unchanged.
5. **Given** a sample name that is empty or has characters other than letters, digits, `-` and `_`, or no name, **Then** the call is refused and nothing is written.
6. **Given** two fresh datasets with the same name over the same candidates, **Then** they draw the same ids; different dataset names give different orders.
7. **Given** rows of a sample were removed with `gold.remove(ids)`, **When** its draw is rerun, **Then** it draws replacements from candidates that are in no sample and not in the dataset's removed-rows file, and says how many; a removed row is never drawn again.
8. **Given** fewer unused candidates than the shortfall, **Then** the draw writes nothing and fails with both numbers; **Given** `sample_size` or `n` that is not a whole number of at least 1, **Then** it is refused.
9. **Given** a `Gold` with no candidates, **When** a draw has no shortfall, **Then** it works; **When** it has one, **Then** it fails saying to give the candidates when creating the `Gold`.
10. **Given** `gold["test-2"]`, **Then** it returns that sample without drawing; an unknown name raises `KeyError` listing the sample names.
11. **Given** the old `gold.draw(...)`, `gold.dev`, `gold.test`, `gold.fold_test()` or `Gold(path=...)`, **Then** they no longer exist.

---

### User Story 2 - Label a Sample: the page shows only the rows of this pass (Priority: P1)

`gl.label(dev, taxonomy)` opens the page on exactly the rows of that Sample that are pending when it is called. It shows "x of 50" with the sample's name on the page. Rows already labelled and rows of other samples are neither counted nor paged. The total stays fixed for the pass, and Back can return to rows labelled earlier in it.

**Why this priority**: this is issue #23 and decision 1.

**Independent Test**: build a file by hand with 50 labelled "dev" rows and 50 pending "test" rows. The server for the "test" Sample should report total 50, done 0 and sample "test", and should never serve a "dev" row. For the "dev" Sample, it should print 012's "nothing to label" line and start no server.

**Acceptance Scenarios**:

1. **Given** 50 labelled "dev" rows and 50 pending "test" rows, **When** `gl.label(test, taxonomy)` is called, **Then** the total is 50, progress counts only those rows, the page names "test", and no "dev" row is served.
2. **Given** a pass of 50 of which 20 get labelled, **When** the call is made again, **Then** the pass is the 30 still pending.
3. **Given** `draw_sample("dev", n=80)` added 30 rows to a labelled "dev", **When** `gl.label(dev, taxonomy)` is called, **Then** the pass is those 30.
4. **Given** nothing pending and no `force_open_ui`, **Then** 012's one line is printed, no server starts, and the Sample is returned.
5. **Given** `force_open_ui=True`, **Then** the pass is every row of the Sample, labelled or not (review and relabel).
6. **Given** anything that is not a Sample (a `Gold`, a `GoldSet`), **Then** `gl.label` refuses it with a message showing the `gold.draw_sample("dev")` form.
7. **Given** Samples from two datasets, **Then** each is labelled in its own file under its own lock.

---

### User Story 3 - The classifier evaluates a Sample, and every evaluation is logged (Priority: P1)

`clf.evaluate(dev, target=0.95)` (and `await clf.aevaluate(...)`) scores the Sample's labelled rows as they are in the file at that moment, so labels the page saved a moment ago are used with no reload. Pending rows are skipped and counted, as today.

Every evaluation is written to `evals.jsonl` beside the dataset's gold file, and there is no option to skip or move it. An identical rerun writes no second line, so rerunning a notebook adds nothing. Identical means the same dataset, samples, rows and labels, prompt, model, metric and target.

The library refuses nothing on account of which sample is scored or how often. Instead, each Sample's summary says how many times it was evaluated and with how many prompts, so the user can see when they have looked at a held-out sample more than once.

**Why this priority**: decisions 4, 6 and 7.

**Independent Test**: label 50 "dev" rows over the simulated HTTP labeller, then evaluate the Sample made before labelling. Expect 50 rows scored with one `FunctionModel` call each, and one log line. Evaluate again: expect zero calls and still one line. Evaluate under a second prompt: expect one more line and the summary "evaluated 2 times (2 prompts)".

**Acceptance Scenarios**:

1. **Given** a Sample made before labelling, **When** it is evaluated after the page saved labels, **Then** the new labels are used.
2. **Given** a Sample with 10 pending of 50, **Then** 40 are scored and 10 counted as skipped.
3. **Given** the same evaluation twice, **Then** the second returns an equal result, writes no line and makes no model call.
4. **Given** the same Sample and prompt with a new `target`, **Then** a new line is written, and the summary's prompt count does not change.
5. **Given** a Sample evaluated under two prompts, **Then** its summary says "evaluated 2 times (2 prompts)"; a Sample never evaluated says "not evaluated".
6. **Given** `clf.evaluate(..., log=...)` or a `GoldSet`, **Then** there is no `log` argument and only a Sample is accepted.
7. **Given** the old `gl.evaluate`, `gl.aevaluate` or `gl.eval_log`, **Then** they no longer exist.
8. **Given** `clf.band_sample(candidates, per_band=30)` or `await clf.aband_sample(...)`, **Then** it returns a `BandReport` as `gl.band_sample` does today, refuses non-seed candidates, and writes no log line. It picks its per-band rows in the id-fixed order, with no seed, so a rerun picks the same rows. (A band check is not an evaluation against gold.)

---

### User Story 4 - Combine Samples with `+`; fold a spent test set into tuning (Priority: P1)

Adding Samples gives a combined Sample over the union of their rows, from the same dataset only. Combining writes nothing. A combined Sample can be labelled and evaluated like any other, and its log lines and summary name every sample in it.

When the user holds a sample out as their test set, scores it, and then decides to keep tuning, this is how the spent rows join the tuning set in plain sight:

```python
tuning = dev + test                     # nothing is written; no row changes
test_2 = gold.draw_sample("test-2")     # a fresh held-out sample
gl.label(test_2, taxonomy)
clf2.evaluate(tuning, target=0.95)
clf2.evaluate(test_2, target=0.95)
```

The docs and skills say when this is honest: only after the user's explicit yes, with a test set that was scored and is spent. They also give the exact calls. The library does not check any of this (decision 4).

**Why this priority**: decision 5; it replaces `fold_test` and is what makes the whole notebook safe to rerun.

**Independent Test**: take a labelled "dev" (50) and "test" (50). Check that `dev + test` has 100 rows and that the gold file is byte-identical before and after. Check that evaluating `dev + test` writes one line naming both samples. Check that `dev + other_dataset_sample` is refused.

**Acceptance Scenarios**:

1. **Given** two samples, **When** they are added, **Then** the result has the union of their rows, its summary names both, and nothing is written.
2. **Given** Samples of two datasets, **When** they are added, **Then** it is refused.
3. **Given** `dev + dev`, or a sample added twice, **Then** each row appears once.
4. **Given** a combination, **When** it is labelled, **Then** the pass is its pending rows.
5. **Given** a combination is evaluated, **Then** the log line names every sample in it, and each part's own summary count is unchanged.

---

### User Story 5 - A second, separately named gold dataset (Priority: P1)

To apply a tuned prompt to another corpus with only a test set there:

```python
gold_b = gl.Gold(candidates_b, name="corpus-b")
test_b = gold_b.draw_sample("test", n=30)
gl.label(test_b, taxonomy)
clf.evaluate(test_b)
```

Corpus A's dataset is untouched. B's rows, labels, samples, page, lock and evaluation counts never mix with A's.

**Why this priority**: issue #22.

**Independent Test**: create two datasets in one temporary folder, with the same id in both, labelled differently. Check that each reads back its own rows, that the unnamed `Gold` is still `gold.jsonl`, that two labelling sessions run at once, and that an evaluation of B's "test" leaves A's "test" count at zero.

**Acceptance Scenarios**:

1. **Given** no name, **Then** the dataset is `<root>/gold.jsonl`.
2. **Given** a name, **Then** the dataset is `<root>/gold-<name>.jsonl`; the name follows the same rule as sample names and also fixes the draw order.
3. **Given** two datasets, **Then** a row id may be in both, and each has its own lock and removed-rows file.
4. **Given** a dataset with only one sample, **Then** it is labelled and evaluated as any other.
5. **Given** an evaluation of B, **Then** A's samples' counts are unchanged (the history is read per gold file).

---

### User Story 6 - The docs and skills teach the Sample flow and the test discipline (Priority: P2)

An agent following the stage skills writes:

```python
gold = gl.Gold(candidates)
dev = gold.draw_sample("dev")
gl.label(dev, taxonomy)
clf.evaluate(dev, ...)
```

It then does the same for "test", with no guards, seeds, reloads or log options. Because the library does not police samples, the skills carry the test discipline of constitution 1.3.0:

- The sample the user holds out is scored once, at the end, fully labelled.
- It never guides edits.
- It is not rescored under another prompt.
- It is combined into tuning only with the user's explicit yes, followed by a fresh held-out sample.

The skills also give a second corpus its own named `Gold`, and say the evaluation history is `evals.jsonl`, a plain file.

**Independent Test**: the drift tests (`tests/test_skills.py`, `tests/test_skill_stages.py`, `tests/test_docs.py`) pass with the changed examples. A check fails when an example uses a removed name (`.draw(`, `draw_dev`, `draw_test`, `fold_test`, `gl.evaluate(`, `gl.aevaluate(`, `gl.band_sample(`, `gl.eval_log(`, `log=`, `Gold(path`, `gl.label(gold`) or passes `seed=` to `draw_sample`.

**Acceptance Scenarios**:

1. **Given** the README, the walkthrough (notebook and script), the overview skill and its references, the stage skills, `docs/agent-instructions.md` and `.kiro/steering/goldlabel.md`, **Then** they use the Sample flow.
2. **Given** `goldlabel-tune` and `references/tuning.md`, **Then** they state the test discipline and explain combining a spent test sample (when it is honest, the explicit yes, the exact calls) in place of `fold_test`.
3. **Given** `goldlabel-tune` and `goldlabel-run`, **Then** they describe the second-corpus, test-only case.
4. **Given** the gold rule, **Then** `src/goldlabel/gold_rule.md` and every copy are unchanged, and nothing adds a way to set a label.

---

### Edge Cases

- **Files from before this feature are not supported** (early alpha). A gold file with `split` and no `sample` fails to load with the existing "not a gold row" error, a log line without `samples` is not counted for any sample, and an old classifier bundle's `evaluation.json` is not read back.
- **A drawn id that is no longer a candidate** stays in its sample and counts toward its size.
- **The id order** is the same on every machine and Python version (it does not use Python's per-process string hashing).
- **A Sample never caches rows.** A variable made before labelling or a top-up shows the file as it is now.
- **Dataset names cannot collide with the default.** The default dataset and one named "gold" are `gold.jsonl` and `gold-gold.jsonl`.
- **A row drawn by another process after a labelling pass began** is not added to that pass.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The constructor MUST be `Gold(candidates=None, *, name=None, sample_size=50)`. The file is `<root>/gold.jsonl` with no name, or `<root>/gold-<name>.jsonl`. There MUST be no path argument. `sample_size` MUST be a whole number of at least 1.
- **FR-002**: Every row MUST belong to exactly one sample, the name in its `sample` field, which replaces `split` in the file, on `GoldRow` and in every table and summary. Names MUST match `[A-Za-z0-9_-]+`. The library MUST treat no sample name specially.
- **FR-003**: `gold.draw_sample(name, n=None)` MUST make the sample `name` (required) hold at least `n` rows (default `sample_size`). It MUST:
  - draw only the shortfall, from candidates that are in no sample of the file and not in its removed-rows file;
  - never remove rows;
  - write nothing if there is no shortfall or not enough candidates;
  - return the Sample.

  `gold[name]` MUST return a sample without drawing. `draw`, the `dev`/`test` properties and `fold_test` MUST be removed.
- **FR-004**: The draw order MUST be fixed by each candidate's id and the dataset's name, the same on every machine. There MUST be no seed argument.
- **FR-005**: A Sample MUST be a live, read-only view of its rows: it reads the file when used and stores no labels. Its summary MUST name the dataset and sample(s) and give rows, labelled, pending, how many the call that made it drew, and how many times it was evaluated with how many prompts. It MUST export `to_polars()` and `to_pandas()`.
- **FR-006**: `sample + sample` MUST return a combined Sample over the union of their rows. It MUST refuse Samples of different datasets and MUST write nothing. It MUST NOT check which samples are combined.
- **FR-007**: `gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)` MUST take a Sample and refuse anything else.
  - It MUST page only the rows pending in the Sample at the call, or every row with `force_open_ui=True`, with a total fixed for the pass.
  - The page MUST name the sample, and its "x of N" MUST count only the pass.
  - It returns the Sample.
- **FR-008**: `clf.evaluate(sample, *, metric=None, target=None)` and `await clf.aevaluate(...)` MUST replace `gl.evaluate` and `gl.aevaluate`, and MUST accept only a Sample.
  - Every evaluation MUST be appended to `evals.jsonl` in the folder of the dataset's gold file, naming the gold file and the samples. `Evaluation`, the log line and a saved classifier bundle carry `samples` (the list of names) in place of `split`.
  - An identical evaluation already in the log MUST NOT be written again. Identical means the same gold file, samples, row ids and labels, prompt digest, model, metric and target.
  - There MUST be no argument to skip or move the log, and no refusal based on which sample is scored or how often.
- **FR-009**: `clf.band_sample(candidates, *, per_band=30)` and `await clf.aband_sample(...)` MUST replace `gl.band_sample`. They MUST pick rows in the id-fixed order with no seed, and write no log line.
- **FR-010**: `gl.eval_log` and `EvalLog` MUST be removed. A sample's evaluation count MUST be read from the log per gold file and shown on the Sample.
- **FR-011**: Each dataset MUST have its own rows, lock, removed-rows file and labelling session. The "id not already in the file" rules of drawing and `import_rows` MUST apply per dataset. `import_rows(rows, name)` puts its rows in the sample `name`.
- **FR-012**: These files MUST use the Sample flow: the README, the walkthrough (notebook and script), the overview skill and references, the stage skills, `docs/agent-instructions.md` and `.kiro/steering/goldlabel.md`.
  - They MUST state the agents' test discipline (constitution 1.3.0, Principle VI).
  - They MUST explain combining a spent test sample, with the explicit-yes rule, and the second-corpus case.
  - They MUST NOT use a removed name, and a drift test MUST fail when one does.
- **FR-013**: Nothing in this change MAY add a way to write a gold label or alter `gold_rule.md`. Only the labelling server and `Gold.import_rows` write labels. A draw writes only pending rows, and combining writes nothing.

### Key Entities

- **Gold dataset**: one file in the storage folder, unnamed (`gold.jsonl`) or named (`gold-<name>.jsonl`), with its candidates and sample size. It holds samples.
- **Sample**: the rows tagged with one name, or a combination of several. Draws return it, and `gl.label` and `clf.evaluate` take it. Live and read-only.
- **Pass**: the pending rows of a Sample at the moment `gl.label` is called.
- **Evaluation log**: `evals.jsonl` beside the gold files in the storage folder. Append-only and always written, it is shared by the datasets there, and each line names its gold file and samples.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A notebook's whole gold section is `gold = gl.Gold(candidates)`, then per sample one `draw_sample`, one `gl.label` and one `clf.evaluate`, with no guard, seed, reload or log option. Running it top to bottom a second time leaves the gold file and the log unchanged and makes no model call. That holds after a fold by `+` and a "test-2" too.
- **SC-002**: After a 50-row "dev" draw and a 50-row "test" draw, the page for each shows "of 50", never 100, and never a row of the other sample, in 100% of tests covering that flow.
- **SC-003**: Two people running the same notebook over the same candidates from an empty folder draw the same rows.
- **SC-004**: Every evaluation appears in the log exactly once, and each Sample's summary gives the right number of evaluations and prompts in 100% of tests.
- **SC-005**: A second dataset over another corpus can be drawn, labelled and scored without touching the first, and the first dataset's samples and counts are identical before and after.
- **SC-006**: No doc or skill example uses a removed name, and a test fails when one does.

## Assumptions

- The constitution is amended to 1.3.0 (Principle VI). `fold_test` is replaced by combining samples. Every evaluation is always logged. The library does not police samples, and the test discipline is a rule for agents. The user approved this on 2026-11-04.
- Dataset and sample names only pick a file and tag rows. There is no registry, list command or stored metadata.
- `n` means "this sample should hold at least `n` rows", not "add `n`".
- goldlabel is early alpha: this feature keeps no compatibility with gold files, logs or classifier bundles written before it, and adds no aliases or shims.
- `GoldSet` stays for `gold.all`, `gold.pending`, `remove`, `import_rows` and `orphaned`. Only per-sample views are Samples.
- `gl.label` stays a library function taking a Sample.
- The band check writes no log line, because it is not an evaluation against gold.
- Other places that choose or skip a file are out of this feature, for a follow-up spec: `get_candidates(out=)`, `cache=`, `classify(out=)`, `clf.save(dir)` and `Classifier.load(dir)`, the explicit `read`/`write` helpers, and changing `gl.settings.root` mid-notebook.

## Deliberately skipped

- Dev/test kinds, and any library rule about which sample is held out ("spent", refusals): the user protects their test set; the skills carry the discipline.
- `draw_dev` / `draw_test` shortcuts.
- A seed or salt argument: change the dataset's name for a different order.
- An append-style draw ("add 10 more"): ask for a bigger size.
- Drawing inside `gl.label`, or drawing samples at `Gold` creation.
- `sum()` of Samples, subtraction, or any set operation besides `+`.
- Aliases or a deprecation period for any removed name.
- A dataset or sample registry, listing command or stored "current" anything.
- A history viewer to replace `gl.eval_log` (read `evals.jsonl` with polars).
- A sample picker, tabs or a dataset switcher in the page.
- Merging, copying or diffing datasets, and moving rows between datasets.
- Any compatibility with, or migration of, gold files, logs or bundles written before this feature.
- Any change to the classifier, cache, cost ledger or metrics beyond moving evaluation and the band check onto the classifier.
- Rewording the gold rule, and any new way to write a label.
