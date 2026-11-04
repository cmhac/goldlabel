# Public API contract: 014

`import goldlabel as gl`. Removed names have no alias.

## Exports (`src/goldlabel/__init__.py`, `tests/test_public_api.py`)

- Added: `Sample`.
- Removed: `evaluate`, `aevaluate`, `band_sample`, `eval_log`, `EvalLog`.
- Unchanged: `Gold`, `GoldSet`, `label`, `Evaluation`, `BandReport`, and the rest.

## `gl.Gold`

```python
gl.Gold(candidates=None, *, name=None, sample_size=50)

gold.draw_sample(split, name=None, n=None) -> Sample   # split "dev" | "test", required
gold.draw_dev(name=None, n=None) -> Sample              # name defaults to "dev"
gold.draw_test(name=None, n=None) -> Sample             # name defaults to "test"
gold[name] -> Sample                                    # no draw; KeyError lists the names
gold.all, gold.pending -> GoldSet                       # unchanged snapshots
gold.import_rows(rows, split) -> GoldSet                # rows go into the sample named after split
gold.remove(ids) -> GoldSet; gold.orphaned(taxonomy) -> GoldSet
```

Removed: `path=`, `gold.draw(...)`, `gold.dev`, `gold.test`, `gold.fold_test(...)`.

Refusals (`GoldError`, nothing written):

- a bad dataset or sample name;
- a sample name already used by the other split;
- `sample_size` or `n` that is not an `int >= 1`;
- a `split` that is not `dev` or `test`;
- a shortfall with no candidates;
- fewer unused candidates than the shortfall;
- new rows for a spent test sample.

## `gl.Sample`

```python
sample.rows; sample.names; sample.split; sample.gold; sample.drawn; sample.path
len(sample); sample.counts(taxonomy); sample.to_polars(); sample.to_pandas()
repr(sample); sample._repr_html_()
sample + other -> Sample
```

`+` refuses Samples of different datasets, and a test sample that has a pending row or is not spent. It writes nothing. Users get Samples from draws, `gold[name]` or `+`, and never construct them.

## `gl.label`

```python
gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None) -> Sample
```

A non-Sample raises `GoldError` showing `dev = gold.draw_dev()` / `gl.label(dev, taxonomy)`.

## `Classifier`

```python
clf.evaluate(sample, *, metric=None, target=None) -> Evaluation
await clf.aevaluate(sample, *, metric=None, target=None) -> Evaluation
clf.band_sample(candidates, *, per_band=30) -> BandReport
await clf.aband_sample(candidates, *, per_band=30) -> BandReport
```

`evaluate` takes only a Sample. It always appends to `<gold folder>/evals.jsonl`, except for an identical evaluation (same gold file, samples, `rows_digest`, digest, model, metric and target). It raises `GoldError` before any model call when a single test sample has a pending row, or is spent and differs from its first evaluation in digest, model or labels. `band_sample` has no `seed` and writes no log line.

## Labelling server (`/api/state`)

Gains `"sample"` and `"split"`. `total`, `position`, `done` and `counts` cover only the pass. Routes unchanged.
