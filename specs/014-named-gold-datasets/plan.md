# Implementation Plan: Named samples, rerun-safe seedless draws, evaluations on the classifier, and named gold datasets

**Branch**: `claude/sleepy-ritchie-ko69ta` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-named-gold-datasets/spec.md`

## Summary

A gold dataset (`Gold(candidates, name=, sample_size=)`, one file in the storage folder) holds named samples. `draw_sample`/`draw_dev`/`draw_test` top a sample up to its size, in an order fixed by `sha256(dataset name, id)`, and return a live, read-only `Sample` (a new small class in `gold.py`; rows gain an optional `sample` field). `gl.label` takes a Sample and pages only its pending rows. Evaluation and the band check become `Classifier` methods over the existing code. Every evaluation is always logged next to the gold file, an identical rerun writes nothing, and a single test sample is scored once. `fold_test` is replaced by `dev + test`, which writes nothing. Removed with no alias:

- `Gold(path=)`
- `draw`, `dev`, `test`, `fold_test`
- `gl.evaluate`, `gl.aevaluate`, `gl.band_sample`
- `gl.eval_log`, `EvalLog`
- `log=`

Constitution 1.3.0 records the new rule. No new module and no new dependency. Details and alternatives are in [research.md](research.md), shapes in [data-model.md](data-model.md), signatures in [contracts/api.md](contracts/api.md).

## Technical Context

**Language/Version**: Python 3.12+; vanilla JavaScript for two strings of the page.

**Primary Dependencies**: none new (`hashlib`, `re` from the standard library).

**Storage**: the existing JSONL files; gold rows gain an optional `sample`; evaluation lines gain `samples` and `rows_digest`.

**Testing**: pytest with `FunctionModel` call counts, hand-built gold files and logs, the HTTP server driven by the simulated human (`tests/test_e2e.py`), served-file text checks for the page. No browser.

**Target Platform**: notebooks and scripts.

**Project Type**: library with a local labelling page.

**Performance Goals**: a draw sorts the candidates once by a `sha256` per id; `+` and the spent check read `evals.jsonl` once each. That's fine for the sizes the library sees.

**Constraints**: importing `goldlabel` does no I/O; sync forms work in a running loop (`_sync.run`); the gold rule.

**Scale/Scope**:

| File | Change |
|---|---|
| `gold.py` | about +120/-60 lines |
| `_label.py` | about 25 lines |
| `evaluation.py` | about +50/-60 lines |
| `classifier.py` | four short methods |
| `candidates.py` | one helper |
| `__init__.py` | exports |
| `web/app.js` | two strings |

Plus about ten test files, the README, the walkthrough (notebook and script), eight skill and reference files, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md` and `AGENTS.md`.

## Constitution Check

*GATE: checked against constitution 1.3.0 before research and again after the design below. All pass.*

- **I Gold Rule**: no new writer of labels.
  - Draws write pending rows (`labels: None`) with a sample name, as `draw` wrote pending rows.
  - `Sample` has no setters, and `+` writes nothing.
  - Only a person's HTTP request (`_label`) and `import_rows` write a label.
  - Evaluation changes no label.
  - Removing `fold_test` removes the last path that rewrote rows outside those two.
  - `gold_rule.md`, its copies and the drift tests are untouched. Test gold files are built by hand or through the simulated human.
  - Pass.
- **II Ponytail** (skill invoked before the spec and again before this plan):
  - One new class (`Sample`, delegating to `GoldSet`), one row field and one helper.
  - No base class, registry or option beyond what the user asked for (`name`, `sample_size`, `n`, sample names, `+`).
  - Lazy imports instead of moving code (R7).
  - Seven public names deleted.
  - The "Deliberately skipped" list holds.
  - Pass.
- **III Spec Kit**:
  - Spec, plan, research, data model, contract and quickstart are in `specs/014-named-gold-datasets/`.
  - The constitution amendment went through `/speckit-constitution`, with the user's approval in the conversation.
  - `/ponytail-review` runs on spec, plan and tasks before `/speckit-implement`, and on the diff plus `/ponytail-debt` after.
  - Pass.
- **IV Test-first**:
  - Each task starts with a failing test with hand-written expected values (ids, counts, messages, log lines).
  - The draw order is tested by its properties, plus one three-id case whose order the test computes with `hashlib` directly.
  - "No model call" is counted with `FunctionModel`.
  - Pass.
- **V No hidden state**:
  - Names are file names and row tags.
  - The spent state is read from the log, which already exists.
  - A Sample stores nothing.
  - The pass lives in the server for one session, as the current row does today.
  - Pass.
- **VI Logged evaluations (1.3.0)**:
  - Always logged, with no off switch and no other location.
  - Identical reruns are not logged twice.
  - A test sample is scored alone once and only when fully labelled.
  - Combining needs a spent test sample.
  - The skills keep the explicit-yes rule for combining.
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
class GoldRow(BaseModel):
    ...
    sample: str | None = None            # written by draws and import_rows; None means "the split's name"

class Sample:                            # live, read-only view of named samples
    def __init__(self, gold, names, split, drawn=0): ...
    rows   -> [r for r in gold._read() if (r.sample or r.split) in names]   # property
    __add__(other) -> Sample             # same gold.path; test parts fully labelled and spent (R6)
    __len__, counts, to_polars, to_pandas, __repr__, _repr_html_   # via GoldSet(self.rows, ...)

class Gold:
    def __init__(self, candidates=None, *, name=None, sample_size=50): ...
    def __getitem__(self, name) -> Sample
    def draw_sample(self, split, name=None, n=None) -> Sample      # R4
    def draw_dev(self, name=None, n=None); def draw_test(self, name=None, n=None)
    all, pending, import_rows(rows, split), remove(ids), orphaned(taxonomy)   # kept
```

- `__repr__`/`_repr_html_` list each sample: name, split, rows, labelled, pending, spent.
- `draw`, `dev`, `test` and `fold_test` are deleted, and so is the `eval_log` import.

### `evaluation.py`

- `_history(log_path, gold_path)` and `_spent(history, name)` (R6).
- `_aevaluate(clf, sample, *, metric, target)`:
  - The test checks (R6) come first.
  - The log line gains `samples` and `rows_digest`.
  - It is appended to `sample.path.parent / "evals.jsonl"` unless an identical line exists.
- `_aband_sample(clf, candidates, *, per_band)` uses `order_by_id` per band and `aclassify`.
- Deleted: `evaluate`, `aevaluate`, `band_sample`, `eval_log`, `EvalLog`, and the `log` argument.

### `classifier.py`

```python
def evaluate(self, sample, **kwargs): return _sync.run(self.aevaluate(sample, **kwargs))
async def aevaluate(self, sample, *, metric=None, target=None):
    from goldlabel.evaluation import _aevaluate  # evaluation imports classifier
    from goldlabel.gold import Sample
    if not isinstance(sample, Sample): raise GoldError("evaluate a Sample: dev = gold.draw_dev() ...")
    return await _aevaluate(self, sample, metric=metric, target=target)
# band_sample / aband_sample likewise
```

### `_label.py` and `web/app.js`

As R8.

### Docs and skills

Every file below moves to the Sample flow:
- `README.md`
- `examples/sample/walkthrough.{ipynb,py}`, kept cell-for-cell equal (`tests/test_docs.py`)
- `src/goldlabel/skills/goldlabel/SKILL.md` and `references/{workflow,tuning,running,reuse}.md`
- `goldlabel-{tune,run}/SKILL.md`
- `docs/agent-instructions.md`
- `.kiro/steering/goldlabel.md`

What they must teach:
- **Combining.** `goldlabel-tune` step 9 and `tuning.md` replace `fold_test` with combining: when it is honest (a spent test sample, the user's explicit yes, said out loud), `tuning = dev + test`, `gold.draw_test("test-2")`, label, tune on `tuning`, score "test-2" once.
- **Second corpus.** `goldlabel-tune` and `goldlabel-run` describe the second-corpus `gl.Gold(candidates_b, name=...)` / `draw_test()` case.
- **History.** `reuse.md` and `tuning.md` say the history is `evals.jsonl` (read with `pl.read_ndjson`) and that a Sample's summary says whether it is spent.

Drift and records:
- A new drift check in `tests/test_skills.py` and `tests/test_docs.py` fails on a removed name: `.draw(`, `fold_test`, `gl.evaluate(`, `gl.aevaluate(`, `gl.band_sample(`, `gl.eval_log(`, `log=`, `Gold(path`, `gl.label(gold`, `.dev`/`.test` on a `Gold`. It also fails on `seed=` in a `draw_` call.
- `AGENTS.md` "Current state" gets the 014 line and the human checks from `quickstart.md`. Its 009 line is left as history.

### Tests

| File | Change |
|---|---|
| `tests/test_gold.py` | new: constructor and name validation, named files, samples and names per split, top-up and rerun, `n`, order properties and the `hashlib` case, removed rows replaced, spent test refuses rows, `gold[name]`, Sample liveness, repr, `+` rules; `draw`/`fold_test` tests replaced |
| `tests/test_label_server.py` | `serve(sample, ...)`; pass scope; fixed total; Back within the pass; `force_open_ui`; `sample`/`split` in state |
| `tests/test_label_page.py` | `gl.label(sample, ...)`; non-Sample refusal; 012's lines; served `app.js` names the sample |
| `tests/test_evaluation.py` | `clf.evaluate`/`aevaluate`; always logged; identical rerun not logged; new target logged; test refusals with zero calls and no line; combination not a test; old log lines; `band_sample`/`aband_sample` with no seed; non-Sample refused |
| `tests/test_e2e.py` | README chain with the new calls, the fold by `+`, then a full second run: byte-identical files, zero model calls |
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
src/goldlabel/gold.py            # Gold(candidates, name, sample_size), named samples, Sample, +
src/goldlabel/_label.py          # label/serve take a Sample; the pass
src/goldlabel/evaluation.py      # _aevaluate (always logged, test once), _aband_sample, history
src/goldlabel/classifier.py      # evaluate/aevaluate/band_sample/aband_sample
src/goldlabel/__init__.py        # + Sample; - evaluate, aevaluate, band_sample, eval_log, EvalLog
src/goldlabel/web/app.js         # sample in the row line
src/goldlabel/skills/**          # Sample flow, combining, second corpus
README.md  docs/agent-instructions.md  .kiro/steering/goldlabel.md  AGENTS.md
examples/sample/walkthrough.{ipynb,py}
tests/…                          # see the table above
```

**Structure Decision**: the existing single-package layout; no new module.

## Risks the user should know

- **Breaking release.** Every removed name stops working with no alias, so existing notebooks need edits. Gold files and logs don't. The version bump is yours.
- **Old projects become strict.** A pre-014 log that scored "test" makes it spent. A new prompt on it is refused, and the way on is `dev + test` and "test-2". That's the rule, but it will surprise someone who used to rescore test freely.
- **Old rows keep their order.** Rows drawn by the old seeded code keep their place, and only new top-ups use the id order. So a file started before 014 and the same notebook started fresh after it hold different rows.
- **Some code still names `fold_test` until implementation lands.** The shipped skills and code keep naming it until 014 is implemented. Constitution 1.3.0 is committed on this branch with the spec, so the two land together when the branch is merged.

## Complexity Tracking

No violations.
