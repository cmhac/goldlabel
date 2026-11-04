# Research: 014 Samples and named gold datasets

Every decision below was checked against the code on this branch (`src/goldlabel/gold.py`, `_label.py`, `evaluation.py`, `classifier.py`, `candidates.py`, `search.py`, `settings.py`, `web/app.js`). No new dependency; only the standard library (`hashlib`, `re`) is added to what `gold.py` imports.

## R1. Draw order without a seed

- **Decision**: order candidates by `hashlib.sha256(f"{salt}\0{id}".encode()).hexdigest()`, where `salt` is the dataset name (`""` for the default). A draw takes the first `need` ids in that order that are not already in the file. `band_sample` uses the same key, salt `""`, per band.
- **Rationale**: the order is fixed by the id alone, so adding or removing candidates never moves the rows already drawn, and it is the same on every machine (`sha256` is not affected by `PYTHONHASHSEED`, unlike `hash()`). Sorting a candidate list once per draw is cheap at the sizes the library sees (keyword candidates in the hundreds; seeds in the thousands).
- **Ids**: every corpus already turns ids into strings (`search.py` builds `{"id": str(id_), ...}`; `Gold.draw` does `str(r["id"])`), so the key is computed on `str(id)` and matches the gold file.
- **Alternatives**: `random.Random(seed)` over the pool (today; changes whenever the pool changes, needs a seed); `random.Random(name)` (same problem); storing a draw order in the file (stored state, rejected by the spec).

## R2. What a Sample is

- **Decision**: a small class in `gold.py`, `Sample(gold, split, drawn=0)`, whose `rows` is a property that reads `gold._read()` and keeps that split. Its `path` is `gold.path` and its `name` is the split, so `aevaluate` (which reads `.rows`, `.name`, `.path`) takes it unchanged. `counts`, `to_polars`, `to_pandas`, `__len__`, `_summary` delegate to a `GoldSet` built on the fly. No base class, no inheritance from `GoldSet` (a frozen dataclass with a `rows` field).
- **Rationale**: it is the least code that is live (no stale rows after labelling, folding or a top-up) and reuses `GoldSet`'s summary, counts and frames.
- **Alternatives**: make `GoldSet` live (changes every snapshot view and the `remove`/`import_rows`/`fold_test` results the spec keeps); return a `GoldSet` snapshot (stale after the page saves, the problem the spec removes).

## R3. Top-up arithmetic

- **Decision**: `need = n - len(rows of split)`; `need <= 0` returns `Sample(drawn=0)` and writes nothing; otherwise pick `need` ids (R1) not in the file; fewer than `need` available raises `GoldError` naming both numbers, writes nothing. `n` and `sample_size` must be `int` (not `bool`) and `>= 1`.
- **Rationale**: matches FR-002 and the spec's rerun scenarios; removed rows (moved to `.removed.jsonl`) are no longer in the file, so a rerun replaces them.

## R4. Named files

- **Decision**: `Gold(candidates=None, *, name=None, path=None, sample_size=50)`; the file is `resolve(path, "gold.jsonl" if name is None else f"gold-{name}.jsonl")`. Names must match `[A-Za-z0-9_-]+` (`re.fullmatch`).
- **Rationale**: `resolve` already gives "argument, then `settings.root`". The default stays `gold.jsonl`; `gold-gold.jsonl` cannot collide with it; no dot is allowed, so a name can never produce `.lock`, `.tmp` or `.removed.jsonl` (those are `gold-<name>.jsonl.lock`, `.jsonl.tmp`, `gold-<name>.removed.jsonl`, all derived from the path as today).
- **Break**: positional `Gold(path)` stops working. Callers found: `tests/test_pre006_fixtures.py:61`, `tests/test_bundle.py:55`, `tests/test_label_page.py:239,278`, and every `Gold(tmp_path / ...)` in `tests/test_gold.py`, `test_label_server.py`, `test_e2e.py`, `test_evaluation.py` (66 `Gold(` lines in tests, src and docs). Each becomes `Gold(path=...)`.

## R5. Labelling pass

- **Decision**: `serve(sample, taxonomy, *, force_open_ui=False, port=None)`; the `Handle` stores `split = sample.split` and `ids`, the ids pending in that split at the start (all ids of the split with `force_open_ui`). `_scope()` keeps rows of that split whose id is in `ids`, so the total is fixed and labelled-in-pass rows stay reachable with Back. `label(id_, ...)` already refuses ids outside `_scope()` (404). `_state()` gains `"split"`; `app.js`'s row line becomes `"Row N of M in dev · id X"`, and the finished text names the split. `gl.label(sample, taxonomy, *, force_open_ui=False, open_browser=True, port=None)` refuses a non-`Sample` with `GoldError` showing the Sample form, and returns the Sample.
- **Rationale**: the smallest change to `Handle`: one stored set replaces the `split in (None, r.split)` filters (three places). No new route, no page redesign.

## R6. Evaluation and band check on the classifier

- **Decision**: `Classifier.evaluate` / `aevaluate` / `band_sample` / `aband_sample` are thin methods that import from `goldlabel.evaluation` inside the method (`evaluation.py` already imports `classifier.py`, so a top-level import would be circular). The module functions are renamed `_aevaluate` and `_aband_sample` and dropped from `__init__`; `evaluate` and `band_sample` (sync module functions) are deleted, the sync methods call `_sync.run(...)` like `Classifier.classify`.
- **Rationale**: no code moves between modules; the import inside a method is the plain way out of the cycle and costs one line each. `band_sample` gets `aband_sample` (it calls `aclassify`), satisfying "every I/O function has an async and a sync form".
- **Alternatives**: move `Evaluation`, `EvalLog`, the log and metrics into `classifier.py` (a large move for no behaviour); keep module functions and add methods (two ways to do one thing, the spec removes them).

## R7. Test split must be fully labelled

- **Decision**: in `_aevaluate`, before any model call, if any row of `gold_set.rows` has `split == "test"` and no labels, raise `GoldError` ("N test rows are still pending; finish labelling before evaluating the test split"). Dev keeps skip-and-count.
- **Rationale**: one check that works for a Sample and for `gold.all`; `gold.test` was labelled-only before, so no existing caller hits it with a correctly labelled split.

## R8. Per-dataset evaluation history

- **Decision**: the log stays one file. `Gold.fold_test` keeps only log rows whose `gold` resolves to the same file (`Path(r["gold"]).resolve() == self.path.resolve()`), and only fold events for this file; it writes `"gold": str(self.path)` on its `test_folded` event. A fold event with no `gold` (older logs) belongs to any file named `gold.jsonl` (the default). `EvalLog._test_line` reports one count per gold file ("test split evaluated 2 times (2 distinct prompts) for .goldlabel/gold.jsonl; 1 time for .goldlabel/gold-corpus-b.jsonl"), so no new parameter on `eval_log`.
- **Rationale**: every evaluation line already records `gold` (`evaluation.py:209`); this reads it. `resolve()` makes `Gold(name=...)` and `Gold(path=...)` for the same file compare equal.
- **Alternatives**: `eval_log(gold=...)` filter parameter (an option nobody asked for); a log per dataset (breaks the single append-only history).

## R9. What is not touched

`Candidates.sample(n, seed)` stays: the stage skills use it to read a few candidates with the user, not to draw gold. `gl.eval_log`, `GoldSet`, `gold.all`, `gold.pending`, `remove`, `import_rows`, `orphaned`, `fold_test`'s return value, the cache, cost and metrics are unchanged apart from R8.
