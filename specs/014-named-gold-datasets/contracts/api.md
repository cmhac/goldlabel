# Public API contract: 014

`import goldlabel as gl`. Removed names have no alias.

## Exports (`src/goldlabel/__init__.py`, `tests/test_public_api.py`)

- Added: `Sample`.
- Removed: `evaluate`, `aevaluate`, `band_sample`, `eval_log` and `EvalLog`.
- Changed: `GoldRow.split` is replaced by `GoldRow.sample` (file key `sample`, `sample` column in `to_polars()`/`to_pandas()`); `Evaluation.split` is replaced by `Evaluation.samples` (a tuple of names), also in a saved bundle's `evaluation.json`. Files from before 014 are not read.
- Unchanged: `Gold`, `GoldSet`, `label`, `BandReport` and the rest.

## `gl.Gold`

```python
gl.Gold(candidates=None, *, name=None, sample_size=50)

gold.draw_sample(name, n=None) -> Sample     # tops the sample up to n (default sample_size)
gold[name] -> Sample                         # no draw; KeyError lists the names
gold.all, gold.pending -> GoldSet            # unchanged snapshots
gold.import_rows(rows, name) -> GoldSet      # rows go into the sample `name`
gold.remove(ids) -> GoldSet; gold.orphaned(taxonomy) -> GoldSet
```

Removed: `path=`, `gold.draw(...)`, `gold.dev`, `gold.test` and `gold.fold_test(...)`.

These raise `GoldError` and write nothing:

- a dataset or sample name that is missing or not `[a-z0-9_-]+` (lowercase only);
- a `sample_size` or `n` that is not an `int` of at least 1;
- a shortfall when no candidates were given;
- fewer unused candidates than the shortfall.

## `gl.Sample`

```python
sample.rows; sample.names; sample.gold; sample.drawn; sample.path
len(sample); sample.counts(taxonomy); sample.to_polars(); sample.to_pandas()
repr(sample); sample._repr_html_()
sample + other -> Sample
```

`+` refuses Samples of different datasets and writes nothing. Users get Samples from `draw_sample`, `gold[name]` or `+`; they never construct one.

## `gl.label`

```python
gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None) -> Sample
```

Passing anything other than a Sample raises `GoldError`, with a message showing `dev = gold.draw_sample("dev")` and `gl.label(dev, taxonomy)`.

## `Classifier`

```python
clf.evaluate(sample, *, metric=None, target=None) -> Evaluation
await clf.aevaluate(sample, *, metric=None, target=None) -> Evaluation
clf.band_sample(candidates, *, per_band=30) -> BandReport
await clf.aband_sample(candidates, *, per_band=30) -> BandReport
```

- `evaluate` takes only a Sample.
- It always appends to `<gold folder>/evals.jsonl`, except for an identical evaluation: same gold file, samples, `rows_digest`, digest, model, metric and target.
- It refuses nothing based on which sample is scored or how often.
- `band_sample` has no `seed` and writes no log line.

## Labelling server (`/api/state`)

- Gains `"sample"`.
- `total`, `position`, `done` and `counts` cover only the pass.
- Routes are unchanged.
