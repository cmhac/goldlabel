# Implementation Plan: Named samples, one rerun-safe draw, evaluations on the classifier, and named gold datasets

**Branch**: `claude/sleepy-ritchie-ko69ta` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-named-gold-datasets/spec.md`

## Summary

A gold dataset is one file in the storage folder, created with `Gold(candidates, name=, sample_size=)`. It holds samples. A sample is the set of rows whose `split` field carries its name.

- **Drawing.** `gold.draw_sample(name, n=None)` tops a sample up to its size, in an order fixed by `sha256(dataset name, id)`, and returns a live, read-only `Sample`. `Sample` is a new small class in `gold.py`.
- **Combining.** Samples combine with `+`, which writes nothing. That replaces `fold_test`.
- **Labelling.** `gl.label` takes a Sample and pages only its pending rows.
- **Evaluation.** Evaluation and the band check become `Classifier` methods over the existing code. Every evaluation is always logged next to the gold file, and an identical rerun writes nothing. The library refuses nothing about which sample is scored. It only shows each Sample's evaluation count.
- **Removed, with no alias:**
  - `Gold(path=)`
  - `draw`, `dev`, `test`, `fold_test`
  - `gl.evaluate`, `gl.aevaluate`, `gl.band_sample`
  - `gl.eval_log`, `EvalLog`
  - `log=`
- **Constitution 1.3.0** moves the test discipline into a rule for agents.

There is no new module, no new dependency and no new gold-row field. Details and alternatives are in [research.md](research.md), shapes in [data-model.md](data-model.md), and signatures in [contracts/api.md](contracts/api.md).

## Technical Context

**Language/Version**: Python 3.12+. Vanilla JavaScript for two strings of the page.

**Primary Dependencies**: none new (`hashlib` and `re` from the standard library).

**Storage**: the existing JSONL files. `GoldRow.split` now holds any sample name. Evaluation lines gain `samples` and `rows_digest`.

**Testing**: pytest, with:
- `FunctionModel` call counts;
- hand-built gold files and logs;
- the HTTP server driven by the simulated human (`tests/test_e2e.py`);
- text checks on the served page files.

No browser.

**Target Platform**: notebooks and scripts.

**Project Type**: library with a local labelling page.

**Performance Goals**: a draw sorts the candidates once, by one `sha256` per id. A Sample's summary reads `evals.jsonl` once. Both are fine at the sizes the library sees.

**Constraints**:
- Importing `goldlabel` does no I/O.
- Sync forms work inside a running loop (`_sync.run`).
- The gold rule.

**Scale/Scope**:

| File | Change |
|---|---|
| `gold.py` | about +90/-80 lines |
| `_label.py` | about 25 lines |
| `evaluation.py` | about +40/-60 lines |
| `classifier.py` | four short methods |
| `candidates.py` | one helper |
| `__init__.py` | exports |
| `web/app.js` | two strings |

Docs and tests:
- about ten test files;
- the README;
- the walkthrough (notebook and script);
- eight skill and reference files;
- `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md` and `AGENTS.md`.

## Constitution Check

*GATE: checked against constitution 1.3.0, before research and again after the design below. All pass.*

- **I Gold Rule**: no new writer of labels.
  - Draws write only pending rows (`labels: None`), as `draw` did.
  - `Sample` has no setters, and `+` writes nothing.
  - Only a person's HTTP request (`_label`) and `import_rows` write a label.
  - Evaluation changes no label.
  - Removing `fold_test` removes the last path that rewrote rows outside those two.
  - `gold_rule.md`, its copies and the drift tests are untouched.
  - Test gold files are built by hand or through the simulated human.
  - Pass.
- **II Ponytail**: the skill was invoked before the spec and again before this plan.
  - The design adds one new class (`Sample`, which delegates to `GoldSet`) and one helper.
  - No field is added, because the sample name reuses `split`.
  - There is no base class or registry, and no option beyond what the user asked for (`name`, `sample_size`, `n`, `+`).
  - Lazy imports are used instead of moving code (R6).
  - Eight public names and methods are deleted.
  - The "Deliberately skipped" list holds. It was cut back twice at the user's request.
  - Pass.
- **III Spec Kit**:
  - The spec, plan, research, data model, contract and quickstart are in `specs/014-named-gold-datasets/`.
  - The constitution was amended with `/speckit-constitution`, with the user's approval.
  - `/ponytail-review` runs on the spec, plan and tasks before `/speckit-implement`. `/ponytail-review` and `/ponytail-debt` run on the diff after.
  - Pass.
- **IV Test-first**:
  - Each task starts with a failing test whose expected values are written by hand: ids, counts, messages and log lines.
  - The draw order is tested by its properties, plus one three-id case whose order the test computes with `hashlib` directly.
  - "No model call" is proved by counting `FunctionModel` calls.
  - Pass.
- **V No hidden state**:
  - Names are file names and row tags.
  - Counts are read from the existing log.
  - A Sample stores nothing.
  - The pass lives in the server for one session, as the current row does today.
  - Pass.
- **VI Logged evaluations (1.3.0)**:
  - Evaluations are always logged, with no off switch and no other location.
  - Identical reruns are not logged twice.
  - The library does not police samples, and the skills carry the agents' test discipline and the explicit-yes rule for combining.
  - Pass.
- **VII Notebooks**:
  - `aevaluate` and `aband_sample` are the async forms, and the sync methods use `_sync.run`.
  - `Gold` stays sync-only local file I/O, as today.
  - `Sample` has a plain `__repr__`, an escaping `_repr_html_`, and `to_polars`/`to_pandas` together.
  - `__init__` exports exactly the public names.
  - Pass.

## Design

### `candidates.py`

```python
def order_by_id(rows, salt: str = "") -> list[dict]:
    """Rows in an order fixed by each id: the same everywhere, unmoved by other rows."""
    return sorted(rows, key=lambda r: hashlib.sha256(f"{salt}\0{r['id']}".encode()).hexdigest())
```

### `gold.py`

```python
NAME = re.compile(r"[A-Za-z0-9_-]+")

class GoldRow(BaseModel):
    ...
    split: str                           # the sample name; validated against NAME

class Sample:                            # live, read-only view of named samples
    def __init__(self, gold, names, drawn=0): ...
    rows   -> [r for r in gold._read() if r.split in names]   # property
    __add__(other) -> Sample             # same gold.path, union of names
    __len__, counts, to_polars, to_pandas, __repr__, _repr_html_   # rows via GoldSet; counts via R5

class Gold:
    def __init__(self, candidates=None, *, name=None, sample_size=50): ...
    def __getitem__(self, name) -> Sample
    def draw_sample(self, name, n=None) -> Sample        # R4
    all, pending, import_rows(rows, name), remove(ids), orphaned(taxonomy)   # kept
```

- `__repr__` and `_repr_html_` list each sample with its rows, labelled and pending counts.
- Deleted: `SPLITS`, `draw`, `dev`, `test`, `fold_test` and the `eval_log` import.

### `evaluation.py`

- Add `_history(log_path, gold_path)` and `_counts(history, names)` (R5).
- `_aevaluate(clf, sample, *, metric, target)`:
  - The log line gains `samples` and `rows_digest`, and `split` becomes `" + ".join(names)`.
  - The line is appended to `sample.path.parent / "evals.jsonl"` unless an identical line exists.
- `_aband_sample(clf, candidates, *, per_band)` uses `order_by_id` in each band and calls `aclassify`.
- Deleted: `evaluate`, `aevaluate`, `band_sample`, `eval_log`, `EvalLog` and the `log` argument.

### `classifier.py`

```python
def evaluate(self, sample, **kwargs): return _sync.run(self.aevaluate(sample, **kwargs))
async def aevaluate(self, sample, *, metric=None, target=None):
    from goldlabel.evaluation import _aevaluate  # evaluation imports classifier
    from goldlabel.gold import Sample
    if not isinstance(sample, Sample): raise GoldError('evaluate a Sample: dev = gold.draw_sample("dev")')
    return await _aevaluate(self, sample, metric=metric, target=target)
# band_sample / aband_sample likewise
```

### `_label.py` and `web/app.js`

As in R7.

### Docs and skills

These move to the Sample flow:
- `README.md`;
- `examples/sample/walkthrough.{ipynb,py}`, kept cell-for-cell equal (`tests/test_docs.py`);
- `src/goldlabel/skills/goldlabel/SKILL.md` and `references/{workflow,tuning,running,reuse}.md`;
- `goldlabel-{tune,run}/SKILL.md`;
- `docs/agent-instructions.md`;
- `.kiro/steering/goldlabel.md`.

What they must say:
- **The test discipline**, which now lives only here and in the constitution. The sample the user holds out is scored once, at the end, fully labelled. It never guides edits and is not rescored under another prompt. The Sample summary's evaluation count is the check.
- **Combining** replaces `fold_test`. `goldlabel-tune` step 9 and `tuning.md` give the steps: `tuning = dev + test`, then `gold.draw_sample("test-2")`, label it, tune on `tuning`, and score "test-2" once. This needs the user's explicit yes, given only after the agent has said what it means.
- **A second corpus** gets its own dataset. `goldlabel-tune` and `goldlabel-run` give the `gl.Gold(candidates_b, name=...)` / `draw_sample("test")` case.
- **History** lives in `evals.jsonl`. `reuse.md` and `tuning.md` say to read it with `pl.read_ndjson`.

A new drift check in `tests/test_skills.py` and `tests/test_docs.py` fails when a doc uses `seed=` in `draw_sample`, or uses any removed name:
- `.draw(`, `draw_dev`, `draw_test`
- `fold_test`
- `gl.evaluate(`, `gl.aevaluate(`, `gl.band_sample(`, `gl.eval_log(`
- `log=`
- `Gold(path`
- `gl.label(gold`

`AGENTS.md` "Current state" gets the 014 line and the human checks from `quickstart.md`. Its 009 line is left as history.

### Tests

| File | Change |
|---|---|
| `tests/test_gold.py` | **New:** constructor and name validation, named files, top-up and rerun, `n`, order properties and the `hashlib` case, removed rows replaced, `gold[name]`, Sample liveness, repr and counts, `+` rules, `import_rows(rows, name)`. **Replaced:** the `draw`/`fold_test` tests. |
| `tests/test_label_server.py` | `serve(sample, ...)`, pass scope, fixed total, Back within the pass, `force_open_ui`, `sample` in state |
| `tests/test_label_page.py` | `gl.label(sample, ...)`, non-Sample refusal, 012's lines, served `app.js` names the sample |
| `tests/test_evaluation.py` | `clf.evaluate`/`aevaluate`, always logged, identical rerun not logged, new target logged, counts per sample and per gold file, old log lines, non-Sample refused, `band_sample`/`aband_sample` with no seed |
| `tests/test_e2e.py` | the README chain with the new calls and the fold by `+`, then a full second run: byte-identical files, zero model calls |
| `tests/test_bundle.py`, `test_pre006_fixtures.py`, `test_public_api.py`, `test_gold_rule.py`, `test_skills.py`, `test_docs.py` | new calls, export list, drift checks |

## Project Structure

### Documentation (this feature)

```text
specs/014-named-gold-datasets/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/api.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source code

```text
.specify/memory/constitution.md  # 1.3.0 (Principle VI)
src/goldlabel/candidates.py      # order_by_id
src/goldlabel/gold.py            # Gold(candidates, name, sample_size), draw_sample, Sample, +
src/goldlabel/_label.py          # label/serve take a Sample; the pass
src/goldlabel/evaluation.py      # _aevaluate (always logged), _aband_sample, history and counts
src/goldlabel/classifier.py      # evaluate/aevaluate/band_sample/aband_sample
src/goldlabel/__init__.py        # + Sample; - evaluate, aevaluate, band_sample, eval_log, EvalLog
src/goldlabel/web/app.js         # sample in the row line
src/goldlabel/skills/**          # Sample flow, test discipline, combining, second corpus
README.md  docs/agent-instructions.md  .kiro/steering/goldlabel.md  AGENTS.md
examples/sample/walkthrough.{ipynb,py}
tests/…                          # see the table above
```

**Structure Decision**: the existing single-package layout. No new module.

## Risks the user should know

- **Breaking release.** Every removed name stops working, with no alias, so existing notebooks need edits. Gold files and logs need none. The version bump is yours.
- **Nothing in code protects a test set.** A user or agent can rescore a held-out sample as often as they like. The Sample summary shows the count, and the skills tell agents not to, but the library will not stop it. That is the choice made in the spec.
- **Old rows keep their order.** Rows drawn by the old seeded code stay where they are; only new top-ups use the id order. A file started before 014 and the same notebook started fresh after it will hold different rows.
- **The branch disagrees with itself until implementation lands.** Until 014 is implemented, the shipped skills and code still name `fold_test` and `gl.eval_log`. Constitution 1.3.0 is on this branch with the spec, so the two land together.

## Complexity Tracking

No violations.
