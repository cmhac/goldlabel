# Implementation Plan: Samples, rerun-safe seedless gold draws, and named gold datasets

**Branch**: `claude/sleepy-ritchie-ko69ta` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/014-named-gold-datasets/spec.md`

## Summary

`Gold` gains `candidates`, `name` and `sample_size`; `draw` is replaced by `draw_sample` / `draw_dev` / `draw_test`, which top a split up to its size in an order fixed by `sha256(name, id)` and return a live `Sample` (a new small class in `gold.py`). `gl.label` takes a Sample and pages only the rows pending in its split when it is called. Evaluation and the band check move onto `Classifier` (`evaluate`/`aevaluate`, `band_sample`/`aband_sample`, no seed) as thin methods over the existing code; the test split must be fully labelled to be evaluated; `fold_test` and the log's test count are per gold file. Docs, skills, walkthrough and tests move to the new calls. No new module, no new dependency, no file-format change for gold rows. Details and alternatives: [research.md](research.md); shapes: [data-model.md](data-model.md); signatures: [contracts/api.md](contracts/api.md).

## Technical Context

**Language/Version**: Python 3.12+; vanilla JavaScript for one line of the page.

**Primary Dependencies**: none new; standard-library `hashlib` and `re` in `gold.py`.

**Storage**: the existing JSONL files (`gold*.jsonl`, `evals.jsonl`); one new key on `test_folded` events.

**Testing**: pytest with `FunctionModel` call counts, hand-built gold files, the HTTP server driven by the simulated human (`tests/test_e2e.py`), served-file text checks for the page. No browser.

**Target Platform**: notebooks and scripts (Jupyter, marimo, Colab, plain Python).

**Project Type**: library with a local labelling page.

**Performance Goals**: a draw sorts the candidate list once (`sha256` per id); fine for the sizes the library handles (hundreds to tens of thousands).

**Constraints**: importing `goldlabel` still does no I/O; sync forms work inside a running loop (`_sync.run`); the gold rule.

**Scale/Scope**: `gold.py` (about +80/-20 lines), `_label.py` (about 20 lines changed), `evaluation.py` (renames, two checks, per-file log), `classifier.py` (four methods), `__init__.py`, `web/app.js` (two strings), about ten test files, README, walkthrough (notebook and script), seven skill/reference files, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md`, `AGENTS.md`.

## Constitution Check

*GATE: checked before research and again after the design below. All pass.*

- **I Gold Rule**: no new writer of labels. Drawing writes pending rows (`labels: None`) as `draw` does; `Sample` is read-only (no setters); `gl.label` still only lets a person's HTTP request write a label; evaluation and folding change no label. `gold_rule.md` and its copies are untouched; the drift tests stay. Test gold files are built by hand or through the simulated human over HTTP. Pass.
- **II Ponytail** (skill invoked before the spec and again before this plan): one new class (`Sample`, about 40 lines, delegating to `GoldSet`), no base class, registry or option beyond what the user asked for (`name`, `sample_size`, `n`); no code moved between modules (lazy imports instead, R6); `Candidates.sample`, `GoldSet` and the snapshot views are kept as they are; removed APIs get no aliases. The spec's "Deliberately skipped" list holds. Pass.
- **III Spec Kit**: spec, plan, research, data model, contract and quickstart in `specs/014-named-gold-datasets/`; `/ponytail-review` on spec, plan and tasks before `/speckit-implement`, and on the diff plus `/ponytail-debt` after. Pass.
- **IV Test-first**: each task starts with a failing test with hand-written expected values (ids, counts, messages). The draw order is tested by its properties (same for the same name, different for another, unchanged by added candidates, disjoint splits) and one case whose expected order the test computes with `hashlib` directly, not through the code under test. "No model call" is counted with `FunctionModel`. No real model, browser or network. Pass.
- **V No hidden state**: the name is only a file name and a hash salt; a Sample stores nothing; the pass lives in the server's memory for one session, as the current row does today; nothing reads config or the working directory behind the caller's back (`resolve` as today). Pass.
- **VI Logged evaluations**: every evaluation is still logged; the "test once" count and the fold guard become per dataset, which is stricter, not looser; a half-labelled test split can no longer be evaluated (the constitution's "MUST NOT be evaluated until every row is labelled" is now enforced). Pass.
- **VII Notebooks**: `aevaluate` and the new `aband_sample` are the async forms, the sync methods use `_sync.run` like `classify`. `Gold` methods stay sync-only local file I/O, as today. `Sample` has a plain `__repr__`, an escaping `_repr_html_`, and `to_polars`/`to_pandas` together. `__init__` exports exactly the public names (`Sample` added; `evaluate`, `aevaluate`, `band_sample` removed). Pass.

## Design

### `gold.py`

```python
_NAME = re.compile(r"[A-Za-z0-9_-]+")

def _order(salt: str, ids) -> list[str]:
    return sorted(ids, key=lambda i: hashlib.sha256(f"{salt}\0{i}".encode()).hexdigest())

class Sample:                                  # live view of one split
    def __init__(self, gold, split, drawn=0): ...
    rows  -> [r for r in gold._read() if r.split == split]   # property
    path, name -> gold.path, split
    __len__, counts, to_polars, to_pandas, __repr__, _repr_html_   # via GoldSet(self.rows, split, path)

class Gold:
    def __init__(self, candidates=None, *, name=None, path=None, sample_size=50): ...
    dev / test -> Sample(self, "dev" | "test")
    def draw_sample(self, split, n=None) -> Sample:   # top up; R3
    def draw_dev(self, n=None), draw_test(self, n=None)
```

`draw` and the `seed` path through `Candidates.sample` are deleted from `Gold`. `fold_test` filters the log by file and writes `"gold"` on its event (R8). `__repr__` / `_repr_html_` name the dataset (`default` or the name). `_order` is also imported by `evaluation.py` for `band_sample`.

### `_label.py`

`Handle(gold, taxonomy, split, ids)`; `_scope()` = rows of `split` with id in `ids`; `label()` uses the same scope; `_state()` adds `"split"`. `serve(sample, taxonomy, *, force_open_ui=False, port=None)` computes `ids` once. `label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)` refuses a non-`Sample`, keeps 012's "nothing pending" line, and returns the Sample. The `SPLITS` checks in `serve`/`label` go (the Sample carries a valid split).

### `web/app.js`

The row line becomes `"Row " + position + " of " + total + " in " + state.split + " · id " + id`; the finished text says `"... rows in " + state.split + " have labels."`. No CSS change (no new classes), so `app.css` is not rebuilt.

### `evaluation.py` and `classifier.py`

`aevaluate` -> `_aevaluate`, with the pending-test refusal (R7) first; `evaluate` and `band_sample` deleted; `_aband_sample(clf, candidates, *, per_band)` picks per band with `_order("", ids)` and calls `aclassify`. `EvalLog._test_line` groups test evaluations and folds by `gold` (R8). In `Classifier`:

```python
def evaluate(self, gold_set, **kwargs): return _sync.run(self.aevaluate(gold_set, **kwargs))
async def aevaluate(self, gold_set, *, metric=None, target=None, log=None):
    from goldlabel.evaluation import _aevaluate  # evaluation imports classifier
    return await _aevaluate(self, gold_set, metric=metric, target=target, log=log)
# band_sample / aband_sample the same way
```

### Docs and skills

README, `examples/sample/walkthrough.{ipynb,py}` (kept cell-for-cell equal; `tests/test_docs.py` checks), `src/goldlabel/skills/goldlabel/SKILL.md` and `references/{workflow,tuning,running,reuse}.md`, `goldlabel-{tune,run}/SKILL.md`, `docs/agent-instructions.md`, `.kiro/steering/goldlabel.md`: `gl.Gold(candidates)`, `dev = gold.draw_dev()`, `gl.label(dev, taxonomy)`, `clf.evaluate(dev, ...)`, `clf.band_sample(candidates)`, the second-corpus `gl.Gold(candidates_b, name=...)` / `draw_test()` case in tune and run, and `fold_test()` followed by `draw_test()`. A new drift check in `tests/test_skills.py` (and `test_docs.py` for README and walkthrough) fails on `.draw(`, `gl.label(gold`, `gl.evaluate(`, `gl.band_sample(` or `seed=` inside a `draw_` call. `AGENTS.md` "Current state" gets the 014 line and the human checks from `quickstart.md`.

### Tests

| File | Change |
|---|---|
| `tests/test_gold.py` | new: constructor validation, named files, top-up and rerun, `n` override, order properties and the `hashlib` case, removed rows replaced, Sample liveness and repr; existing `draw` tests rewritten to the new calls; `fold_test` per file and legacy events |
| `tests/test_label_server.py` | `serve(sample, ...)`; pass scope (50 labelled dev + 50 pending test), fixed total, Back within the pass, `force_open_ui` pass, `"split"` in state; existing split tests rewritten |
| `tests/test_label_page.py` | `gl.label(sample, ...)`, non-Sample refusal, 012's lines with a Sample; served `app.js` contains the split in the row line |
| `tests/test_evaluation.py` | `clf.evaluate`/`aevaluate`, pending-test refusal with zero calls and no log line, `band_sample`/`aband_sample` without seed (same rows twice), per-file test line |
| `tests/test_e2e.py` | README chain with the new calls, then rerun: gold file byte-identical, zero model calls; the fold test uses `draw_test()` |
| `tests/test_bundle.py`, `test_pre006_fixtures.py`, `test_public_api.py`, `test_gold_rule.py`, `test_skills.py`, `test_docs.py` | `Gold(path=...)`, `clf.evaluate`, export list, drift checks |

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
src/goldlabel/gold.py            # Gold(candidates, name, sample_size), draws, Sample, fold_test per file
src/goldlabel/_label.py          # label/serve take a Sample; the pass
src/goldlabel/evaluation.py      # _aevaluate, _aband_sample, per-file test line
src/goldlabel/classifier.py      # evaluate/aevaluate/band_sample/aband_sample methods
src/goldlabel/__init__.py        # + Sample; - evaluate, aevaluate, band_sample
src/goldlabel/web/app.js         # split in the row line
src/goldlabel/skills/**          # new calls
README.md  docs/agent-instructions.md  .kiro/steering/goldlabel.md  AGENTS.md
examples/sample/walkthrough.{ipynb,py}
tests/…                          # see the table above
```

**Structure Decision**: the existing single-package layout; no new module.

## Risks the user should know

- **Breaking release.** `Gold(path)`, `gold.draw`, `gl.label(gold, ..., split=)`, `gl.evaluate`, `gl.aevaluate`, `gl.band_sample` and every draw `seed=` stop working, with no alias. Existing notebooks (the user's included) need edits; gold files do not. The version bump is the user's.
- **Rerunning a notebook re-evaluates the test split.** With cached predictions it costs nothing, but each rerun logs another test evaluation and raises the "evaluated N times" count, as today. The user's notebook used `log=False` for that; the spec does not change it.
- **Rows already drawn by the old seeded code** keep their place; only new top-ups use the id order, so a file started before 014 and the same notebook started fresh after 014 can hold different rows.

## Complexity Tracking

No violations.
