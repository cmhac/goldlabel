# Public API contract: 014

`import goldlabel as gl`. Removed names have no alias.

## Exports (`src/goldlabel/__init__.py`, `tests/test_public_api.py`)

- Added: `Sample`.
- Removed: `evaluate`, `aevaluate`, `band_sample`.
- Unchanged: everything else (`Gold`, `GoldSet`, `label`, `eval_log`, `Evaluation`, `EvalLog`, `BandReport`, ...).

## `gl.Gold`

```python
gl.Gold(candidates=None, *, name=None, path=None, sample_size=50)

gold.draw_sample(split, n=None) -> Sample   # split: "dev" | "test", required
gold.draw_dev(n=None) -> Sample
gold.draw_test(n=None) -> Sample
gold.dev -> Sample                          # no draw; includes pending rows
gold.test -> Sample
gold.all, gold.pending -> GoldSet           # unchanged snapshots
gold.import_rows(rows, split), gold.remove(ids), gold.orphaned(taxonomy), gold.fold_test(log=None)  # unchanged signatures
```

Removed: `gold.draw(candidates, n, split, seed)`.

Errors (`GoldError` unless noted): bad `name`; `sample_size`/`n` not an `int >= 1` (`bool` refused); `split` not `dev`/`test`; draw with no candidates; fewer unused candidates than the shortfall. Each writes nothing.

## `gl.Sample`

```python
sample.rows -> list[GoldRow]    # read from the file now
sample.split, sample.gold, sample.drawn, sample.path, sample.name
len(sample); sample.counts(taxonomy); sample.to_polars(); sample.to_pandas()
repr(sample); sample._repr_html_()
```

Not constructed by users (they get it from a draw or `gold.dev`/`gold.test`); no setters.

## `gl.label`

```python
gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None) -> Sample
```

Removed: the `gold` first argument and `split=`. A non-`Sample` first argument raises `GoldError` naming `gold.draw_dev()` / `gold.dev`.

## `Classifier`

```python
clf.evaluate(gold_set, *, metric=None, target=None, log=None) -> Evaluation
await clf.aevaluate(gold_set, *, metric=None, target=None, log=None) -> Evaluation
clf.band_sample(candidates, *, per_band=30) -> BandReport
await clf.aband_sample(candidates, *, per_band=30) -> BandReport
```

`gold_set` is a `Sample` or a `GoldSet`. A test row with no labels in it raises `GoldError` before any model call or log line. `band_sample` has no `seed`.

## Labelling server (`/api/state`)

Gains `"split": "dev" | "test"`. `total`, `position`, `done`, `counts` cover only the pass. Routes unchanged.

## Evaluation log

`test_folded` events gain `"gold"`. `repr(gl.eval_log())` gives the test-evaluation count per gold file.
