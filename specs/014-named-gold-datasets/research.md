# Research: 014 named samples and named gold datasets

Every decision below was checked against the code on this branch: `src/goldlabel/gold.py`, `_label.py`, `evaluation.py`, `classifier.py`, `candidates.py`, `search.py`, `settings.py` and `web/app.js`. There is no new dependency; the only additions are the standard-library modules `hashlib` (already used in `candidates.py`) and `re`.

## R1. Draw order without a seed

- **Decision**: add `order_by_id(rows, salt="")` to `candidates.py`. It sorts rows by `hashlib.sha256(f"{salt}\0{row['id']}".encode()).hexdigest()`, where `salt` is the dataset name (`""` for the default).
  - A draw takes the first `need` candidates in that order whose id is in no sample of the file.
  - `band_sample` uses the same helper inside each band, with `salt=""`.
- **Rationale**:
  - An id keeps its position whatever else is in the list, so rows already drawn never move.
  - The order is the same on every machine, because it uses `sha256` and not `hash()`, which `PYTHONHASHSEED` changes.
  - Every corpus already turns ids into strings (`search.py` builds `{"id": str(id_), ...}`), so the key matches the gold file.
  - `candidates.py` imports neither `gold.py` nor `evaluation.py`, so both can import the helper without a cycle.
- **Alternatives**: `random.Random(seed)` over the remaining pool, as today, changes whenever the pool changes and needs a seed. Storing an order in the file is stored state.

## R2. The sample name is the row's `split`

- **Decision**: `GoldRow.split` changes from `Literal["dev", "test"]` to `str`, validated against `[A-Za-z0-9_-]+`, and holds the sample name. No new field, and no `SPLITS` constant.
  - Every pre-014 row already says "dev" or "test", so old files hold those two samples unchanged.
  - Rows that `fold_test` moved are "dev" rows.
  - Draws write the name; `import_rows(rows, name)` writes the name it is given.
- **Rationale**: the least change. One field means one rule, and old files need no migration.
- **Alternatives**: a second `sample` field next to `split` would mean two things to keep consistent, and the user removed the dev/test kinds that would have justified it.

## R3. What a Sample is

- **Decision**: `class Sample` in `gold.py`, constructed as `Sample(gold, names, drawn=0)`.
  - `names` is a tuple: one name, or several for a combination.
  - `rows` is a property: the rows of `gold._read()` whose `split` is in `names`.
  - `path` is `gold.path`.
  - `counts`, `to_polars`, `to_pandas`, `__len__` and the row part of the summary delegate to a `GoldSet` built on the fly.
  - `__add__` refuses a different `gold.path` and otherwise returns `Sample(gold, names + new names)`.
  - The summary's evaluation count comes from R5.
- **Rationale**: a Sample is live, so it has no stale rows after the page saves or a top-up. It is read-only, it reuses `GoldSet`, and it needs no base class.

## R4. Top-up

- **Decision**: `need = n - len(rows of the sample)`.
  - When `need <= 0`, return the Sample and write nothing.
  - Otherwise pick `need` candidates as in R1.
  - Fewer available: refuse with both numbers.
  - No candidates given: refuse, naming `gl.Gold(candidates)`.
  - `n` and `sample_size` must be an `int` (not a `bool`) of at least 1.
  - A draw with no shortfall needs no candidates.
- **Rationale**: this is FR-003. A removed row has moved to `.removed.jsonl` and is no longer in the file, so a rerun replaces it.

## R5. Files, the log and the counts

- **Decision**: `Gold(candidates=None, *, name=None, sample_size=50)` sets `self.path = settings.root / ("gold.jsonl" if name is None else f"gold-{name}.jsonl")`, fixed when the `Gold` is made.
  - A dataset's log is `gold.path.parent / "evals.jsonl"`. That is in the storage folder, and it stays the same file for that dataset even if `gl.settings.root` changes later.
  - Lock, temp and removed files are derived from the path as today.
- **Log lines** gain `"samples": [names]` and `"rows_digest"`, the `sha256` of the JSON of `sorted((id, sorted(labels)) for labelled rows)`. `"split"` keeps a string, `" + ".join(names)`, and so does `Evaluation.split`. That way `Classifier.save`'s `evaluation.json` and older readers still get a string.
- **Helpers in `evaluation.py`**:
  - `_history(log_path, gold_path)` returns the evaluation lines whose `gold` resolves to `gold_path` (compared with `Path(x).resolve()`).
    - A line with no `samples` is read as `[split]`.
    - `test_folded` events are skipped.
  - `_counts(history, names)` returns the number of lines whose `samples` equals `list(names)`, and the number of distinct `digest`s among them.
  - Identical means a line already exists with the same `samples`, `rows_digest`, `digest`, `model`, `metric` and `target`. Then no line is appended, but the `Evaluation` is still built and returned; the predictions are cached, so no model call is made.
- `gold.py` imports `_history` and `_counts` from `evaluation.py`, the direction it already imports in today. `evaluation.py` does not import `gold.py`.
- **Callers to change**, anything that passes `Gold` a path, positionally or as `path=`:
  - `tests/test_pre006_fixtures.py:61`
  - `tests/test_bundle.py:55`
  - `tests/test_label_page.py:239,278`
  - the `Gold(tmp_path / ...)` lines in `tests/test_gold.py`, `test_label_server.py`, `test_e2e.py` and `test_evaluation.py`

  Each becomes `monkeypatch.chdir(tmp_path)` or `settings.root = tmp_path`, with `Gold()` or `Gold(name=...)`.

## R6. Evaluation and the band check on the classifier

- **Decision**: `Classifier.evaluate`, `aevaluate`, `band_sample` and `aband_sample` become thin methods that import inside the method body. `evaluation.py` imports `classifier.py`, so a top-level import would be circular.
  - `aevaluate` also imports `Sample` there and refuses anything else.
  - The module functions become private (`_aevaluate`, `_aband_sample`).
  - `evaluate`, `aevaluate`, `band_sample`, `eval_log` and `EvalLog` leave the public surface and `__init__`.
  - The `log` argument is removed.
  - The sync methods use `_sync.run`, like `classify`.
- **Rationale**: no code moves between modules, at the cost of one import line per method.

## R7. Labelling pass

- **Decision**: `serve(sample, taxonomy, *, force_open_ui=False, port=None)`.
  - The `Handle` keeps the `sample` and `ids`: the ids pending in it at the start, or every id with `force_open_ui`.
  - `_scope()` is the file's rows whose id is in `ids`. That replaces the three `split in (None, r.split)` filters, so the total stays fixed and Back works within the pass.
  - `label()` already returns 404 for an id outside the scope.
  - `_state()` gains `"sample"`, the names joined with " + ".
  - `app.js`'s row line becomes `"Row N of M in <sample> · id X"`, and the finished line names the sample.
  - Text still goes in through `el()`/`textContent`, and no CSS classes are added.
  - `gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)` refuses a non-Sample and returns the Sample.
- **Rationale**: the smallest change to `Handle`. No new route, no page redesign and no CSS rebuild.

## R8. Kept as is

These are unchanged:
- `Candidates.sample(n, seed)`, a reading aid in the skills rather than a gold draw;
- `GoldSet`, `gold.all`, `gold.pending`, `remove` and `orphaned`;
- the cache, cost and metrics.

The `get_candidates(out=)`, `cache=`, `classify(out=)` and bundle paths are a follow-up (see the spec's Assumptions).
