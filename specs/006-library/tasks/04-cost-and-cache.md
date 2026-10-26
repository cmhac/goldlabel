# 04 — Cost, cache and ledger take an explicit cache directory

Spec: "Where files go" (cache), "Cost", FR-4, FR-6 (cost parts), FR-10.

**Do** in `cost.py` (plain functions, no class):
- Every function that touched `files.root()` takes the cache directory: `cache_get(cache, key)`, `cache_put(cache, key, output, usage)`, `record(cache, model, usage, dollars)`, `record_timing(cache, label, n_items, seconds)`, `items_per_second(cache, label)`, `total(cache)`, `breakdown(cache)`, `per_call_dollars(cache, model)`. `cache` is a `Path`, or `False`/`None` meaning "no cache": then `cache_get` returns `None`, `cache_put`/`record*` do nothing. A helper `cache_dir(cache)` resolves `None` → `resolve(None, "cache")` and `False` → `False`.
- Layout unchanged: entries `<cache>/<sha256>.json`; `cache_key` unchanged. The ledger (totals, per-model breakdown, timings) is one file inside the cache directory (`cost.json`); a pre-006 `cost.json` from `.hunches/` is not read. Writes of the ledger are atomic (temp file + `os.replace`).
- `hunches.cost(cache=None)` returns a small `Cost` object: `.total` (float or `None`), `.unknown` (bool), `.by_model`; its `__repr__` shows `$0.0000`-style amounts and `cost ?` plus a warning line whenever any recorded call had an unknown price. Never `$0` for unknown (FR-6).
- Update the current callers (`candidates`, `classifier`) to pass the cache directory through using the default (`None`) for now; they get their final shape in tasks 06 and 07.

**Tests (red first)**: round trip of entry and ledger in `tmp_path`; `cache=False` writes nothing and reads nothing; default resolves under `settings.root`; the pre006 fixture's cache entry is read by `cache_get` and `cache_key` for its inputs equals `expected.json` (FR-4); an unknown-price `record` makes `Cost.total` `None` and the repr contain `?` and a warning; a cache hit records no cost and no timing; two writers to the ledger from threads lose no update (or document and test the chosen behaviour).

**Not in this task**: the `Classifier` class, estimates.
