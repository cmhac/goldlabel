# 11 — Finish the removal: `files.py`, `system.py`, `keys.py`, `models.py`, dependencies, public API

Spec: "What is kept, changed, removed", FR-1, FR-2, SC-4.

**Do**
- Delete `files.py` (everything left in it moved in tasks 04–09: confirm with a grep that nothing imports it; move any leftover helper, such as `read_jsonl`/`append_jsonl`, to where it is used), `system.py`, `keys.py` (if task 05 did not), and `Config`/`PG_DEFAULTS`. `models.py` keeps only price lookup used by `cost` (`price_label`, `snapshot_date`, `known_models` if used); drop the `system.RECOMMENDED` import.
- Remove `keyring`, `platformdirs` and `python-dotenv` from dependencies, and any test fixtures for them from `conftest.py`. `uv lock`. The library never loads `.env` itself (document in README later).
- `src/hunches/__init__.py` exports exactly the public names of the spec's "The pieces": `LocalCorpus, S3Corpus, PgCorpus, read_seeds, search, asearch, Candidates, Taxonomy, Classifier, Predictions, Estimate, CostLimit, Gold, GoldSet, evaluate, aevaluate, Evaluation, eval_log, EvalLog, band_sample, BandReport, cost, Cost, settings`, plus `__version__`. (`label`, `GOLD_RULE_SHORT`, `GOLD_RULE_FULL` arrive in tasks 14 and 15.) Importing is free of side effects: nothing read, written or networked; heavy optional imports (`boto3`, `psycopg`) stay lazy.
- Remove stale names from docstrings and messages (grep for `config.toml`, `.hunches/state`, `Textual`, `TUI`, `screen`, `stage`).

**Tests (red first)**: `python -c "import hunches, sys; assert not {'textual','keyring','platformdirs','dotenv'} & set(sys.modules)"` in a subprocess (FR-2); `hunches.__all__` equals the list above; importing with a cwd that has a read-only `.hunches/` or no `.hunches/` works and creates nothing (FR-1); each pre006 fixture file is read by the new code (`Candidates.read`, `Taxonomy.read`, `Gold`, `cache_get`, results rows) and the compatibility values in `expected.json` are reproduced (SC-4, FR-4); `uv run ty check` clean.

**Not in this task**: reprs, labelling, docs.
