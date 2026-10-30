# Quickstart: checking corpus filters

## 1. Automated checks (no service, no key)

```bash
uv sync --all-extras
```

```bash
uv run pytest tests/test_table.py tests/test_search.py tests/test_search_pg_keywords.py tests/test_search_pg_exact.py tests/test_search_pg_index.py tests/test_skills.py -n0
```

```bash
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

Expected: everything passes. The only edited existing tests are the ones `plan.md` lists under
"Existing tests that change".

## 2. Table, by hand in a notebook

```python
import polars as pl
import goldlabel as gl

rows = [
    {"id": "1", "text": "ballot one", "section": "politics"},
    {"id": "2", "text": "ballot two", "section": "sports"},
]
corpus = gl.Table(rows, id_column="id", where=pl.col("section") == "politics")
gl.get_candidates(corpus, keywords=["ballot"], out=False)  # 1 candidate: id 1
```

## 3. Postgres (a human, real database; Podman, never Docker)

Against a throwaway pgvector started with `podman run`, single and two-table layouts:

- the whole corpus, keywords with and without `server_side=True`, and seeds with `search="exact"`
  and `search="index"`, each with `where="section = 'politics'"`: only politics rows come back;
- `where="body LIKE '%vote%'"` with keywords and `server_side=True`: no placeholder error, and the
  same rows as without `server_side`;
- `where="name = 'O''Brien'"`: matches the row with `O'Brien`;
- two-table layout with a column that is only in the vector table: the error ends with the
  text-table line.

`tests/test_pg_integration.py` covers the first three automatically when `GOLDLABEL_TEST_PG_URL`
is set (the CI `pgvector` job).

## 4. S3 Vectors (a human, real index)

On an index whose vectors carry `section` (string), `year` (number) and `tags` (list) metadata:

- seeds with `where={"section": "politics"}`: only politics hits;
- whole corpus with the same filter: the same items the service returns for a broad seed query
  with that filter;
- record what the service does for a vector without `year` under `{"year": {"$ne": 2024}}`, and
  for `{"tags": {"$in": [...]}}` and `{"tags": {"$ne": "x"}}` against list values. If it differs
  from research R5's rules, fix `_s3_match` and note it in the spec.

## 5. Agent trial (a human)

In Claude Code with `goldlabel install claude`, ask for "only the politics section since 2024" on
each corpus type. The agent should:
1. look up the real column names;
2. write the filter for that corpus type;
3. explain it in plain words;
4. wait for a yes before using it.
