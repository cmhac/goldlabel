# Research: 014 named samples and named gold datasets

Every decision below was checked against the code on this branch (`src/goldlabel/gold.py`, `_label.py`, `evaluation.py`, `classifier.py`, `candidates.py`, `search.py`, `settings.py`, `web/app.js`). No new dependency. Standard-library `hashlib` (already used in `candidates.py`) and `re`.

## R1. Draw order without a seed

- **Decision**: `order_by_id(rows, salt)` in `candidates.py` sorts by `hashlib.sha256(f"{salt}\0{row['id']}".encode()).hexdigest()`. `salt` is the dataset name (`""` for the default). A draw takes the first `need` candidates in that order whose id is in no sample of the file. `band_sample` uses the same helper with `salt=""` inside each band.
- **Rationale**: an id keeps its position whatever else is in the list, so rows already drawn never move and the order is the same on every machine (`sha256`, not `hash()`, which `PYTHONHASHSEED` changes). Every corpus already makes ids strings (`search.py`: `{"id": str(id_), ...}`), so the key matches the gold file. `candidates.py` imports neither `gold.py` nor `evaluation.py`, so both can import the helper without a cycle.
- **Alternatives**: `random.Random(seed)` over the remaining pool (today: changes whenever the pool changes, needs a seed); storing an order in the file (stored state).

## R2. Sample names on rows

- **Decision**: `GoldRow.sample: str | None = None`, dropped from the file by `dump()` when `None` (the existing pattern for `labelled_by`, `labelled_at`, `note`). A row's sample is `row.sample or row.split`, so every pre-014 row belongs to "dev" or "test". Draws write `sample` on every new row; `import_rows(rows, split)` writes `sample=split`. A name must match `[A-Za-z0-9_-]+` and all rows of a name must share one split (checked on draw).
- **Rationale**: one optional field, no migration; the rule is visible in one line.
- **Alternatives**: free-form `split` values ("test-2") would break `split: Literal["dev","test"]` and every filter on it.

## R3. What a Sample is

- **Decision**: `class Sample` in `gold.py`: `Sample(gold, names, split, drawn=0)`. `names` is a tuple (one name, or several for a combination); `split` is `"dev"`/`"test"` for one name and `None` for a combination. `rows` is a property: the rows of `gold._read()` whose sample is in `names`. `path` is `gold.path`. `counts`, `to_polars`, `to_pandas`, `__len__` and the summary delegate to a `GoldSet` built on the fly. `__add__` returns `Sample(gold, names_a + new names_b, None)` after its checks (R6).
- **Rationale**: live (no stale rows after the page saves or a top-up), read-only, reuses `GoldSet`. No base class.

## R4. Top-up

- **Decision**: `need = n - len(rows of the sample)`. `need <= 0`: return the Sample, write nothing. A spent test sample with `need > 0`: refuse. Otherwise pick `need` candidates (R1); fewer available: refuse with both numbers; no candidates given: refuse naming `gl.Gold(candidates)`. `n` and `sample_size` must be `int` (not `bool`) `>= 1`. A draw with no shortfall needs no candidates.
- **Rationale**: FR-003; a removed row (moved to `.removed.jsonl`) is no longer in the file, so a rerun replaces it.

## R5. Files and the log location

- **Decision**: `Gold(candidates=None, *, name=None, sample_size=50)`; `self.path = settings.root / ("gold.jsonl" if name is None else f"gold-{name}.jsonl")`, fixed when the `Gold` is made. The evaluation log of a dataset is `gold.path.parent / "evals.jsonl"`: in the storage folder, and the same file every time for that dataset even if `gl.settings.root` changes later. Lock, temp and removed files are derived from the path as today.
- **Callers to change** (`Gold(path)` positional or keyword): `tests/test_pre006_fixtures.py:61`, `tests/test_bundle.py:55`, `tests/test_label_page.py:239,278`, and the `Gold(tmp_path / ...)` lines in `tests/test_gold.py`, `test_label_server.py`, `test_e2e.py`, `test_evaluation.py`; each becomes `monkeypatch.chdir(tmp_path)` or `settings.root = tmp_path` with `Gold()` or `Gold(name=...)`.

## R6. Spent, identical, and combining

- **Decision**: each log line gains `"samples": [names]` and `"rows_digest"`: `sha256` of the JSON of `sorted((id, sorted(labels)) for labelled rows)`. In `evaluation.py`:
  - `_history(log_path, gold_path)`: the log's evaluation lines whose `gold` resolves to `gold_path` (`Path(x).resolve()`); a line with no `samples` is read as `[split]`; `test_folded` events are skipped.
  - `_spent(history, name)`: the first line whose `samples == [name]` and `split == "test"`, or `None`.
  - Identical: a line with the same `samples`, `rows_digest`, `digest`, `model`, `metric` and `target` exists, so no line is appended. The `Evaluation` is still built and returned (the predictions are cached, so no model call).
- In `_aevaluate`, before any model call: a single test sample with a pending row is refused; a single test sample that is spent, where the first line's `digest`, `model` or `rows_digest` (when present) differs, is refused. Combinations are never checked as tests.
- In `Sample.__add__`: refuse different `gold.path`s; refuse any single test sample that has a pending row or is not spent (`gold.py` imports `_history`/`_spent` from `evaluation.py`; `gold.py` already imports from it today, and `evaluation.py` does not import `gold.py`).
- **Rationale**: one hash per evaluation over rows already in memory; the log is still the only record; old lines keep counting (a pre-014 test evaluation makes "test" spent).

## R7. Evaluation and the band check on the classifier

- **Decision**: `Classifier.evaluate`/`aevaluate`/`band_sample`/`aband_sample` are thin methods that import inside the method (`evaluation.py` imports `classifier.py`, so a top-level import would be circular). `aevaluate` also imports `Sample` there and refuses anything else. The module functions become private (`_aevaluate`, `_aband_sample`); `evaluate`, `aevaluate`, `band_sample`, `eval_log` and `EvalLog` leave `evaluation.py`'s public surface and `__init__`. The `log` argument is removed. Sync methods use `_sync.run`, like `classify`.
- **Rationale**: no code moves between modules; one import line per method.

## R8. Labelling pass

- **Decision**: `serve(sample, taxonomy, *, force_open_ui=False, port=None)`. The `Handle` keeps the `sample` and `ids`: the ids pending in it at start (every id with `force_open_ui`). `_scope()` is the file's rows with id in `ids`. That replaces the three `split in (None, r.split)` filters, so the total is fixed and Back works within the pass. `label()` already 404s an id outside the scope. `_state()` gains `"sample"` (names joined with " + ") and `"split"`. `app.js`'s row line becomes `"Row N of M in <sample> · id X"`, and the finished line names the sample. Text goes in through `el()`/`textContent` as today, and no CSS classes are added. `gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)` refuses a non-Sample and returns the Sample.
- **Rationale**: the smallest `Handle` change; no new route, no page redesign, no CSS rebuild.

## R9. Kept as is

`Candidates.sample(n, seed)` (a reading aid in the skills, not a gold draw), `GoldSet`, `gold.all`, `gold.pending`, `remove`, `orphaned`, the cache, cost and metrics. The `get_candidates(out=)`, `cache=`, `classify(out=)` and bundle paths are a follow-up (spec Assumptions).
