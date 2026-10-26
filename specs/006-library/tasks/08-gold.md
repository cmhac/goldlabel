# 08 — `Gold`, `GoldSet`, `draw`, `import_rows`

Spec: "`Gold`, `GoldSet`, `label`" (everything except `label`), "The gold rule" (what the library does and does not do), FR-14, FR-16.

**Do** in a new `gold.py` (move `GoldRow` here from `files.py`):
- `GoldRow`: `id, text, labels (list[str] | None), split ("dev"|"test")`, optional `labelled_by`, `labelled_at`. Rows in the pre-006 format (no stamps) load unchanged.
- `Gold(path=None)`: loads or creates (default `resolve(None, "gold.jsonl")`; nothing is written until a write happens). Writes are atomic (temp file + `os.replace`). Reads accept any well-formed file, including one produced elsewhere or by hand; a malformed line raises with the line number.
- `gold.draw(candidates, n=50, split="dev", seed=None)`: appends `n` **pending** rows (`labels=None`) sampled without replacement from candidates whose id is not anywhere in the file (dev and test stay disjoint); fewer than `n` available raises, naming how many are. Returns a `GoldSet` of the new rows.
- `gold.import_rows(rows, split)`: adds already-labelled rows (dicts with `id`, `text`, `labels`), stamped `labelled_by: "imported"`, `labelled_at` now; refuses an id already present; does not validate labels against a taxonomy (that happens in `evaluate`, task 09). This and the labelling server (task 13) are the only code that writes labels.
- `gold.dev`, `gold.test`, `gold.pending`, `gold.all`: `GoldSet` views (read-only, labelled rows only except `pending`/`all`). `GoldSet`: `.rows`, `len`, `.counts(taxonomy)` (per-label counts including `off_topic`, `multi` rows counted once per label), plain `__repr__` (split, rows, labelled/pending, per-source counts: `hunches-ui`, `imported`, unstamped).
- `gold.orphaned(taxonomy)`: rows with a label not in the taxonomy (from `files.orphaned_gold`). `gold.remove(ids)`: moves rows to `<gold>.removed.jsonl` (append) and rewrites the gold file without them; never deletes data.
- Delete the gold functions from `files.py` (`read_gold`, `write_gold`, `orphaned_gold`, `gold_coverage`) and their tests, porting the useful assertions (`tests/test_gold_orphans.py`).

**Tests (red first)**: pre006 `gold.jsonl` loads and counts match hand-computed numbers; `draw` writes `labels=None`, never repeats an id across dev and test, is deterministic per seed, raises when short; `import_rows` stamps and refuses duplicates; counts for `single` and `multi`; a hand-edited file with extra unknown keys loads; malformed line error; atomic write (a crash between temp write and replace leaves the old file intact: simulate by raising in a patched `os.replace`); `orphaned`; `remove` appends to `.removed.jsonl` and keeps all fields; **no public function other than `import_rows` sets a label** (introspect `hunches.gold` public names for mutators, and assert `draw` output has all `labels` `None`).

**Not in this task**: the server, `hn.label`, the gold-rule text, HTML.
