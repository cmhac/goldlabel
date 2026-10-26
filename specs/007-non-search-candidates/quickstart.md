# Quickstart: validating non-search candidates

**Spec**: [spec.md](spec.md) | **Contract**: [contracts/public-api.md](contracts/public-api.md)

This is a run guide, not the tests. The tests live in `tests/` and are listed in `tasks.md`.

## Prerequisites

```
uv sync --extra s3 --extra pg --extra rds     # enough for every test in this feature
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

Baseline before this feature: 450 passed, 17 skipped.

## 1. Same five rows, six inputs, same answer (SC-002, SC-009)

In a scratch script (not committed), write five rows to `rows.csv`, `rows.parquet`, `rows.jsonl`,
a polars frame, a pandas frame and a list of dicts. For each source:

```python
import hunches as hn
t = hn.Table(source, text_column="body", id_column="post_id")
hn.get_candidates(t).to_polars()                          # all five, table order
hn.get_candidates(t, keywords=["ballot"]).to_polars()     # the hand-computed ids
```

Expected: identical ids and order from every source; no file written (`.hunches/` untouched).

## 2. Ranking and flags (SC-002)

```python
import re
hn.get_candidates(t, keywords=[re.compile("vote", re.I), re.compile("^Election", re.M)])
```

Expected: rows ordered by `terms_matched`, then `matches`, then table order; the case-insensitive
pattern does not make the second one case-insensitive.

## 3. Guards (SC-005)

`hn.get_candidates(t, keywords=["x"]).above(0.7)` raises `ValueError` naming "keywords";
`hn.get_candidates(t, seeds=["a"], keywords=["b"], embedder="x")` raises; a CSV `Table` with
`vector_column` raises at construction.

## 4. Seed search unchanged (SC-003)

`hn.get_candidates(table_with_vectors, seeds=seeds, embedder=embedder)` returns the same
similarities, bands and ranking as the old `hn.search` did for the same vectors (the pre-006
fixtures and the end-to-end test prove this with hand-computed values).

## 5. Needs a human (cannot run here)

- A real Postgres: server-side and Python-side keyword results agree for ASCII terms, including the
  two-table layout and a term containing `%`, `_` and a backslash; a regex string such as
  `(?i)vote[sd]?` runs.
- A real S3 Vectors index: `get_candidates(S3Corpus(...), keywords=[...])` lists keys and metadata
  with the list and get permissions, and a 403 names the missing permission.
- Parquet through polars, and through pandas with pyarrow installed.
- The walkthrough notebook in real Jupyter with a real key.
