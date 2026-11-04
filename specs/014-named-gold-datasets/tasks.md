# Tasks: Named samples, one rerun-safe draw, evaluations on the classifier, and named gold datasets

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/api.md](contracts/api.md), [quickstart.md](quickstart.md).

**Commits**: one commit per task, named `014/TNN: ...`. The specs and constitution 1.3.0 are already committed.

**Tests**: red/green is required by the constitution (Principle IV). Every task writes its failing tests first, runs them and watches them fail for the right reason (not an import error that could have been avoided), then implements and shows them green. Expected values are written by hand. "No model call" is proved by counting `FunctionModel` calls. Nothing calls a real model, browser or network.

**Green at every commit**: `tests/test_skills.py` and `tests/test_docs.py` check every doc code block against the real public names. So a task that removes or renames a name also updates every doc and test that uses it, in the same commit. Each task ends with `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest` passing; pre-commit enforces them.

**Docs touched by every task** (call them "the docs"):
- `README.md`
- `examples/sample/walkthrough.py` and `examples/sample/walkthrough.ipynb`, kept cell-for-cell equal with no outputs
- `src/goldlabel/skills/*/SKILL.md`
- `src/goldlabel/skills/goldlabel/references/{workflow,tuning,running,reuse}.md`
- `docs/agent-instructions.md`
- `.kiro/steering/goldlabel.md`

Each task's grep is the check that none are missed.

## Phase 1: Named samples and draws (User Stories 1 and 5, plus `+` from User Story 4)

**Goal**: a `Gold` holds lowercase-named samples in a `sample` field. `draw_sample(name, n)` tops a sample up in an id-fixed order and returns a live Sample; Samples add with `+`; named datasets get their own file.

**Independent test**: US1's and US5's independent tests in `spec.md`.

- [X] T001 [US1] [US5] Implement named samples, `draw_sample`, `Sample` and named datasets in `src/goldlabel/gold.py` and `src/goldlabel/candidates.py`, adapting every caller.

  **Tests first (red).** Put these in `tests/test_gold.py` unless noted. Candidates are built by hand: `Candidates([{"id": str(i), "text": f"t{i}"} for i in range(200)])`. Tests use `monkeypatch.chdir(tmp_path)` or `settings.root = tmp_path`.
  - **Files and names.**
    - `Gold()` → `<root>/gold.jsonl`, and `Gold(name="corpus-b")` → `<root>/gold-corpus-b.jsonl`.
    - These dataset names are refused with `GoldError`: `"CorpusB"`, `""`, `"a.b"`, `"a/b"`.
    - `Gold(path=...)` raises `TypeError`.
    - `sample_size` of `0`, `-1`, `1.5` and `True` are refused.
  - **Rows.**
    - `GoldRow` has `sample` (must match `[a-z0-9_-]+`) and no `split`.
    - A hand-written file with a row `{"id":..., "text":..., "labels": null, "split": "dev"}` makes `gold.all` raise `GoldError` containing "not a gold row".
  - **Draws.**
    - `draw_sample("dev")` returns a Sample with `drawn == 50` and the file holds 50 rows with `sample == "dev"`.
    - A second call gives `drawn == 0` and still 50 rows.
    - `draw_sample("test")` and then `draw_sample("test-2")` each add 50; the three id sets are disjoint.
    - `draw_sample("dev", n=80)` gives `drawn == 30`; `draw_sample("dev", n=30)` then gives `drawn == 0` with 80 rows kept; `gold.sample_size == 50` throughout.
    - `n` of `0` and `True` are refused, and so is the name `"Test"`.
    - Asking for more than the unused candidates raises `GoldError` naming both numbers, and the file bytes are unchanged.
    - A `Gold()` with no candidates: a draw with no shortfall works; a shortfall raises `GoldError` containing `gl.Gold(candidates`.
  - **Order.**
    - Two roots with the same dataset name draw the same "dev" ids; dataset names `"a"` and `"b"` draw different id sets.
    - Ids `"a"`, `"b"`, `"c"` come out of `order_by_id` in the order the test computes itself with `hashlib.sha256(f"\0{id}".encode()).hexdigest()`.
    - Rerunning `draw_sample("dev")` after adding 50 candidates leaves the file bytes unchanged.
  - **Removed rows.** `gold.remove([two dev ids])`, then `draw_sample("dev")`, gives `drawn == 2`; neither removed id is redrawn and both are in `gold.removed.jsonl`.
  - **Lookup.** `gold["test-2"]` returns the Sample with `drawn == 0`; `gold["nope"]` raises `KeyError` whose message lists `dev`, `test` and `test-2`.
  - **Sample.**
    - A Sample made before the file is rewritten by a hand-built fixture shows the new rows and labels.
    - `len`, `counts(taxonomy)`, and `to_polars()`/`to_pandas()` together, with a `sample` column.
    - `repr` starts with `Sample "dev" of default: 50 rows (0 labelled, 50 pending); drew 50 now`, and `_repr_html_` escapes.
  - **Combining.**
    - `dev + test` has 100 rows, `names == ("dev", "test")`, and the gold file bytes are unchanged.
    - `dev + dev` has 50 rows.
    - A Sample from `Gold(name="b")` added to one from `Gold()` raises `GoldError`.
  - **Import.** `import_rows(rows, "test")` writes `sample: "test"`.
  - **Removed names.** `Gold` has no `draw`, `dev`, `test` or `fold_test`, and `goldlabel.Sample` exists.
  - **Two datasets.** The same id can be in `Gold()` and `Gold(name="b")`, each in its own file, with different `.lock` paths.

  **Implement**, as in plan.md "Design":
  - In `src/goldlabel/candidates.py`: `order_by_id`.
  - In `src/goldlabel/gold.py`:
    - `NAME`, `GoldRow.sample` replacing `split`, and `GoldSet` showing a `sample` column;
    - `Sample` with `__add__`;
    - `Gold(candidates=None, *, name=None, sample_size=50)`, `__getitem__`, `draw_sample` (skipping file ids and `.removed.jsonl` ids), and `import_rows(rows, name)`;
    - delete `SPLITS`, `draw`, `dev`, `test` and `fold_test`.
  - In `src/goldlabel/__init__.py`: export `Sample`.

  **Adapt every caller in this commit** (all minimal; Phases 2 and 3 replace them):
  - `src/goldlabel/_label.py`: `r.split` becomes `r.sample`, and `split=` is validated with `NAME` instead of `SPLITS`. `gl.label(gold, taxonomy, split=...)` keeps its signature for now.
  - `src/goldlabel/evaluation.py`: `r.split` becomes `r.sample`; the evaluation's split string comes from its rows only; delete the fold reading (`folds`, `test_folded`) from `EvalLog`.
  - The tests:
    - every hand-built gold row's `split` becomes `sample`;
    - every `Gold(path)` and `gold.draw(`/`.dev`/`.test` call;
    - the `fold_test` tests are deleted, and the fold test in `tests/test_e2e.py` is rewritten to `tuning = dev + test` and `draw_sample("test-2")`;
    - `tests/test_pre006_fixtures.py` loses its gold check, and `tests/fixtures/pre006/gold.jsonl` is deleted;
    - the gold column list in `tests/test_notebook.py` (line 392) and its `GoldRow(... split=...)` fixtures;
    - `tests/test_bundle.py`, `tests/test_label_server.py`, `tests/test_label_page.py`, `tests/test_evaluation.py` and `tests/test_gold_rule.py`.
  - The docs:
    - `gold.draw(candidates, n=..., split=..., seed=...)` becomes `gold.draw_sample("dev")` / `("test")`;
    - `gold.dev` / `gold.test` become the Sample variable or `gold["dev"]`;
    - `gl.label(gold, taxonomy)` becomes `gl.label(gold, taxonomy, split="dev")` until T002;
    - `gold.fold_test()` and its steps become the combining steps (`tuning = dev + test`, `test_2 = gold.draw_sample("test-2")`), with "explicit yes" kept in each file that shows them.
  - `tests/test_skills.py`:
    - the needle `gold.draw(` becomes `gold.draw_sample(`;
    - `test_folding_the_test_split_always_comes_with_the_explicit_yes` becomes a check that every file showing `dev + test` says "explicit yes" and that `goldlabel-tune/SKILL.md` is one of them.

  **Grep before committing**: `grep -rnE "\.draw\(|fold_test|gold\.(dev|test)\b|Gold\([a-z_]*path|split=\"(dev|test)\"" src tests README.md docs examples .kiro` must show only `gl.label(..., split=...)` calls, which are left for T002. Run `uv run pytest tests/test_gold.py tests/test_notebook.py tests/test_e2e.py tests/test_skills.py tests/test_docs.py -n0`, then the four checks.

## Phase 2: Labelling takes a Sample (User Story 2)

**Goal**: `gl.label(sample, taxonomy)` pages only the rows of the Sample that are pending when it is called, and names the sample on the page.

**Independent test**: US2's independent test in `spec.md`.

- [X] T002 [US2] Make `serve` and `gl.label` take a Sample in `src/goldlabel/_label.py`, and name the sample in `src/goldlabel/web/app.js`.

  **Tests first (red).**
  - In `tests/test_label_server.py`, start from a hand-built file of 50 labelled "dev" rows and 50 pending "test" rows. `serve(gold["test"], taxonomy)` must then behave as follows:
    - `/api/state` has `total == 50`, `done == 0` and `sample == "test"`.
    - Labelling every served row over HTTP never serves a dev id.
    - After 20 labels, a new `serve` has `total == 30`.
    - `force_open_ui=True` gives `total == 50`, labelled included.
    - Back returns to a row labelled in this pass.
    - `POST /api/label` for a dev id returns 404 and leaves the file unchanged.
  - In `tests/test_label_page.py`:
    - `gl.label(sample, taxonomy)` with nothing pending prints 012's line, starts no server and returns the Sample.
    - `gl.label(gold, taxonomy)` and `gl.label(gold.all, taxonomy)` raise `GoldError` containing `gold.draw_sample("dev")`.
    - The served `app.js` builds the row line with `state.sample`.

  **Implement**, as in research R7:
  - `Handle` keeps `sample` and the pass `ids`; `_scope()` is the rows with an id in `ids`.
  - `_state()` adds `"sample"`.
  - `serve(sample, taxonomy, *, force_open_ui=False, port=None)` and `label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)`; `split` goes.
  - In `app.js`, the row line becomes `"Row N of M in <sample> · id X"`, and the finished line names the sample. Use `el()`/`textContent` and add no CSS classes.

  **Update** `tests/test_e2e.py` and the docs: `gl.label(gold, taxonomy, split=...)` becomes `gl.label(dev, taxonomy)` and so on.

  **Grep** `grep -rn "gl.label(gold\|label(gold\|split=" src tests README.md docs examples .kiro`: no hits outside unrelated uses. Run `uv run pytest tests/test_label_server.py tests/test_label_page.py tests/test_e2e.py tests/test_skills.py tests/test_docs.py -n0`, then the four checks.

## Phase 3: Evaluation on the classifier, always logged (User Stories 3 and 4)

**Goal**: `clf.evaluate(sample)` and `clf.band_sample(candidates)`. Every evaluation is logged next to the gold file, and an identical rerun is not logged twice. Each Sample shows its own evaluation count. `gl.evaluate`, `gl.aevaluate`, `gl.band_sample`, `gl.eval_log`, `EvalLog` and `log=` are gone.

**Independent test**: US3's and US4's independent tests in `spec.md`, and quickstart items 4, 5, 7 and 8.

- [X] T003 [US3] [US4] Move evaluation and the band check onto the classifier, always logged, in `src/goldlabel/evaluation.py`, `src/goldlabel/classifier.py` and `src/goldlabel/gold.py`.

  **Tests first (red).** Put these in `tests/test_evaluation.py` unless noted. Each test counts `FunctionModel` calls and reads the log from `tmp_path / "evals.jsonl"`.
  - **What is scored.**
    - A Sample made before its rows are labelled (by a hand-built rewrite) is scored with the new labels.
    - With 10 of 50 pending, `n == 40` and `skipped_pending == 10`.
  - **What is logged.**
    - The first `clf.evaluate(dev)` makes 50 calls and writes 1 line with `gold`, `samples == ["dev"]` and `rows_digest`. The test computes `rows_digest` itself with `hashlib` over `sorted((id, sorted(labels)))`.
    - An identical second call makes 0 calls, still leaves 1 line, and returns an equal score.
    - A new `target` adds a line, 2 in all.
    - `clf.with_prompt(...)` adds a line.
  - **Counts on the summary** (assert on `repr(dev)` in `tests/test_gold.py`).
    - After the two prompts above, `repr(dev)` contains `evaluated 3 times (2 prompts)`.
    - An unevaluated Sample says `not evaluated`.
    - Evaluating `dev + test` writes `samples == ["dev", "test"]` and leaves `repr(dev)` unchanged.
    - An evaluation of `Gold(name="b")["test"]` leaves `repr(Gold()["test"])` at `not evaluated`.
    - A hand-written log line with no `samples` key counts for no sample.
  - **Refusals and removals.**
    - `clf.evaluate(gold.all)` raises `GoldError`.
    - `clf.evaluate(dev, log=False)` raises `TypeError`.
    - `goldlabel` has none of `evaluate`, `aevaluate`, `band_sample`, `eval_log` or `EvalLog`.
  - **Results.**
    - `Evaluation.samples == ("dev",)`.
    - In `tests/test_bundle.py`, `clf.save(dir, evaluation=ev)` writes `"samples"` in `evaluation.json`, and `Classifier.load` reads it.
    - `await clf.aevaluate(dev)` works, and the sync form works inside a running loop.
  - **Band check.**
    - `clf.band_sample(seed_candidates, per_band=2)` sends the same texts to the `FunctionModel` on two runs.
    - It refuses keyword candidates.
    - It writes no line.
    - `await clf.aband_sample(...)` matches it.
  - **Exports.** `tests/test_public_api.py`'s `PUBLIC` list adds `Sample` and drops the five removed names.
  - **Reprs.** In `tests/test_notebook.py`, the `EvalLog` fixtures and repr tests are deleted, and the `Evaluation` and `Sample` reprs and frames are covered.

  **Implement**, as in research R5 and R6 and plan.md "Design":
  - In `evaluation.py`:
    - `_history`, `_counts`, `rows_digest`, and the identical-line check;
    - `_aevaluate(clf, sample, *, metric, target)` appending to `sample.path.parent / "evals.jsonl"`, with `samples` replacing `split` in the line;
    - `Evaluation.samples` replacing `split`;
    - `_aband_sample` using `order_by_id` per band;
    - delete `evaluate`, `aevaluate`, `band_sample`, `eval_log`, `EvalLog` and the `log` argument.
  - In `classifier.py`:
    - `evaluate`/`aevaluate`/`band_sample`/`aband_sample`, importing inside the method and refusing a non-Sample;
    - `save` writes `samples`.
  - In `gold.py`: the Sample summary's `evaluated N times (M prompts)` / `not evaluated`.
  - In `__init__.py`: the exports.

  **Update** `tests/test_e2e.py`:
  - The README chain uses `clf.evaluate`, `tuning = dev + test` and `draw_sample("test-2")`.
  - It then runs the whole chain a second time and asserts that the gold file and `evals.jsonl` are byte-identical and that the `FunctionModel` was called 0 times (SC-001).

  **Update the docs:**
  - `gl.evaluate(clf, x, ...)` becomes `clf.evaluate(x, ...)`.
  - `gl.band_sample(clf, c, ...)` becomes `clf.band_sample(c, ...)`, with no seed.
  - `gl.eval_log()` becomes reading `.goldlabel/evals.jsonl` with `pl.read_ndjson`, plus the Sample summary's count. This touches `references/tuning.md`, `references/reuse.md` and `goldlabel-tune/SKILL.md`.

  **Update the drift tests:**
  - In `tests/test_skills.py`, the needles `gl.evaluate(`, `gl.band_sample(` and `gl.eval_log(` become `clf.evaluate(` and `clf.band_sample(`.
  - Update the `VARS` map if it lists `gl.evaluate` results.

  **Grep** `grep -rnE "gl\.(a?evaluate|band_sample|eval_log)\(|EvalLog|log=" src tests README.md docs examples .kiro`: no hits. Run `uv run pytest tests/test_evaluation.py tests/test_bundle.py tests/test_gold.py tests/test_notebook.py tests/test_public_api.py tests/test_e2e.py tests/test_skills.py tests/test_docs.py -n0`, then the four checks.

## Phase 4: The docs teach the discipline (User Story 6)

**Goal**: the skills carry the test discipline the library no longer enforces, the second-corpus case, and a guard against removed names.

**Independent test**: US6's independent test in `spec.md`.

- [X] T004 [US6] Teach the test discipline, combining and the second-corpus case in `src/goldlabel/skills/goldlabel-tune/SKILL.md`, `src/goldlabel/skills/goldlabel/references/tuning.md` and `src/goldlabel/skills/goldlabel-run/SKILL.md`, and add a removed-name guard to `tests/test_skills.py`.

  **Tests first (red).** In `tests/test_skills.py`:
  - **A removed-name guard** over the docs (all of them, including the README and both walkthrough files). It fails on any of these:
    - `.draw(`, `draw_dev`, `draw_test`
    - `fold_test`
    - `gl.evaluate(`, `gl.aevaluate(`, `gl.band_sample(`, `gl.eval_log(`
    - `EvalLog`
    - `log=`
    - `Gold(path`
    - `gl.label(gold`
    - `seed=` inside a `draw_sample(` call
  - **The discipline.** `goldlabel-tune/SKILL.md` and `references/tuning.md` each contain:
    - "held out";
    - "once";
    - "explicit yes";
    - `tuning = dev + test`;
    - `draw_sample("test-2")`.
  - **The second corpus.** `goldlabel-tune/SKILL.md` and `goldlabel-run/SKILL.md` each contain `gl.Gold(` with `name=` and a `draw_sample("test"` call.

  Watch the discipline and second-corpus checks fail. The guard may already pass after T001–T003; say so.

  **Write the text, as constitution 1.3.0 Principle VI states it:**
  - **The discipline.** The sample the user holds out is scored once, at the end, fully labelled. It never guides edits and is not rescored under another prompt or model. The Sample summary's count is the check.
  - **Combining.** Only after a spent held-out sample and the user's explicit yes, given after the agent has said what it means: `tuning = dev + test`, `test_2 = gold.draw_sample("test-2")`, people label it, tune on `tuning`, score `test_2` once.
  - **The second corpus.** `gold_b = gl.Gold(candidates_b, name="corpus-b")`, `test_b = gold_b.draw_sample("test", n=30)`, label, `clf.evaluate(test_b)`.
  - **The README.** Add a short "Samples" paragraph: one file per dataset, a sample is a name, `+` combines, every evaluation is logged.
  - **Agent docs.** Mirror one line of each in `docs/agent-instructions.md` and `.kiro/steering/goldlabel.md` where they describe the gold step.

  Run `uv run pytest tests/test_skills.py tests/test_skill_stages.py tests/test_docs.py tests/test_gold_rule.py -n0`, then the four checks.

## Phase 5: Close

- [ ] T005 Close the feature in `specs/014-named-gold-datasets/spec.md` and `AGENTS.md`.
  - Run `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest`, and report the real output summaries.
  - Run `/ponytail-review` on the diff since the specs commit and `/ponytail-debt`, and fix what they find.
  - Set the spec's Status to "Implemented".
  - Update `AGENTS.md`:
    - the "Current state" paragraph: 014 implemented, with a one-line summary of the API;
    - the human checks from `quickstart.md`: the page for a dev and a test Sample in a real browser, and the walkthrough run twice in real Jupyter;
    - the testing note on `tests/fixtures/pre006/`, which no longer covers gold;
    - the "Layout" line for `gold.py`, which should list `Gold`, `Sample`, `GoldSet`, `draw_sample` and `import_rows`, and no longer `draw`.
  - Report the Ponytail line and the human checks.

## Dependencies

T001 → T002 → T003 → T004 → T005. None of these can run in parallel:
- T002 reads T001's `Sample` and `sample` field.
- T003 reads T002's `gl.label(sample)` in the e2e chain.
- T004 describes T001–T003's calls.
- Every task edits the same docs and `tests/test_skills.py`.

## Parallel opportunities

Inside a task only:
- The test files of T001 (`test_gold.py`, `test_notebook.py`, `test_pre006_fixtures.py`) can be rewritten side by side before the implementation.
- In T003, `test_evaluation.py`, `test_bundle.py` and `test_public_api.py` can be written side by side.

## Implementation strategy

- **MVP: T001 + T002.** These fix both issues: #22 (named datasets, one file each) and #23 (the page shows only one sample's pending rows). Draws become rerun-safe and seedless.
- **T003** finishes the API the user designed: the classifier methods, the always-on log and the counts.
- **T004** moves the test discipline into the skills.
- **T005** closes the feature.
- Each task is one green commit; stop after any task and the branch still works.
