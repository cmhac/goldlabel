# Research: Filter the corpus before candidates are drawn

Every fact below was checked on 2026-10-30 against the installed versions (polars 2.1.0, pyarrow
from `uv run --with pyarrow`, psycopg 3.3.6, the botocore `s3vectors` service model) or the
current docs named. Experiments ran in the scratchpad, not in the repository.

## R1. One polars reading path for `Table`

**Decision**: `table_rows` builds one `polars.DataFrame` per source and then runs the existing
row checks on `df.to_dicts()`:

| Source | Call |
|---|---|
| `.csv` | `pl.read_csv(path, infer_schema=False)` |
| `.jsonl` | `pl.read_ndjson(path, infer_schema_length=None)` |
| `.parquet` | `pl.read_parquet(path)` |
| polars DataFrame | as it is |
| pandas DataFrame | `pl.from_pandas(df)` |
| list of rows | `pl.DataFrame(rows, infer_schema_length=None)` |

The same pattern of a plain `if` on the source covers every case, and the `csv`/`json` reading and
`_parquet_rows` (with its pandas fallback) are deleted.

**Facts behind it**:

- `read_csv` infers types by default: `"007"` becomes `7`. `infer_schema=False` keeps every value
  as text, which is today's behaviour. A UTF-8 byte order mark is dropped from the first column
  name, and an empty CSV field becomes null. The existing check reports a null text with today's
  message ("not a non-empty string") and a null id as "is empty".
- `pl.DataFrame(rows)` and `read_ndjson` infer the schema from the first 100 rows by default. A
  key that first appears after row 100 is silently dropped (seen: 150 rows without `k`, then one
  with it, gave columns `['t']`). `infer_schema_length=None` reads every row, so it is required
  for both.
- A key missing from some rows becomes null. Today's "row N ... is empty" check still fires for a
  missing id, and "not a non-empty string" for a missing text.
- **Behaviour change 1**: in a list of rows or a JSONL file, a column that mixes strings and
  numbers is turned into strings (`{"text": 5}` next to `{"text": "a"}` gives `"5"`). This
  happens even with `strict=True` and `schema_overrides={"text": pl.String}`, so it cannot be
  turned off. Today that row is refused. A column that holds only numbers is still refused by the
  existing string check.
- **Behaviour change 2**: a vector column that mixes lists with a string or a nested list fails
  inside polars (`ComputeError: could not append value ...`, `SchemaError: failed to determine
  supertype`). That message names no row. It is re-raised as `ValueError("Table: polars could not
  read the source: ...")`. A `None` vector or a list of the wrong length still reaches today's
  per-row check, so its message is unchanged.
- `pl.from_pandas` needs pyarrow
  ([docs](https://docs.pola.rs/py-polars/html/reference/api/polars.from_pandas.html)).
  - It turns a float `NaN` into null (`nan_to_null=True` by default), so today's "row 1 ...
    non-empty" message for a pandas NaN text is unchanged.
  - It drops the index (`include_index=False` by default), as today's `to_dict("records")` does.
  - An object column that mixes `str` and `int` raises `TypeError`, which is re-raised as above.
- A pandas DataFrame is recognised by its type's module (`type(src).__module__` starts with
  `"pandas"`), so pandas is never imported.

**Alternatives considered**: keeping the standard-library readers for CSV and JSONL was rejected,
because the user decided polars only. Checking types in Python before handing a list to polars was
rejected because it would be a second validation path, and JSONL would still coerce.

## R2. The Table filter is a polars expression

**Decision**: `Table(where=...)` takes a `pl.Expr`.
- `__post_init__` imports polars (the user already did, to build the expression) and refuses
  anything else with a `TypeError` that shows the expression form.
- `table_rows` runs `df.filter(table.where)` before the row checks.

**Facts**:

- `isinstance(pl.col("s") == "a", pl.Expr)` is `True`.
- Rows where the predicate is null are dropped.
- A missing column raises `ColumnNotFoundError`, and a non-boolean expression raises
  `InvalidOperationError: filter predicate must be of type Boolean`. Both are re-raised as
  `ValueError("Table where: <polars message>")`.
- The dataclass `repr` already includes the field, and `repr(expr)` reads
  `<Expr ['[(col("s")) == ("a")]'] at 0x...>`, so FR-009 needs no code for `Table`.
- `map_elements` was rejected: polars calls it strongly discouraged, because it runs a Python loop
  ([Expr.map_elements](https://docs.pola.rs/api/python/dev/reference/expressions/api/polars.Expr.map_elements.html)).

## R3. polars and pyarrow become core dependencies

**Decision**: add `polars` and `pyarrow` to `[project] dependencies`, remove `polars` from the dev
group (pandas stays there), and delete `_frame.to_polars`'s now-dead "polars is not installed"
branch.
- `import goldlabel` still imports neither. Polars is imported inside `table_rows` and
  `Table.__post_init__`, and `test_public_api.py` keeps enforcing that.
- pyarrow is a 51 MiB download for linux x86-64, the size seen when installing it here.
- The constitution's Stack line ("Additional Constraints") and `AGENTS.md`'s Stack line name the
  core dependencies, so both are updated. The constitution change is a PATCH through
  `/speckit-constitution`, which the user approved by choosing the dependencies on 2026-10-30.

## R4. Postgres: the condition is SQL text with values written in

**Decision**: `PgCorpus(where="...")`. A helper `_pg_where(corpus, id_expr)` returns the one
fragment added to each query: `{id_expr} IN (SELECT {key} FROM {source} WHERE ({cond}))`.
- `{source}` and `{key}` are `text_source(corpus)`: the text table and its id column, or the
  table and `id_column`.
- One form for both layouts, so the condition never shares a scope with the query's own columns.
  `search_pg_exact` step 1 has helper columns `i` and `sim`, and a bare `AND (cond)` on a user
  column called `i` would be "ambiguous" (pre-implement review, finding 1).

`cond` is `sql.SQL(corpus.where.replace("%", "%%"))`. Every query that carries the fragment is sent
with parameters, an empty tuple if it has none.

The fragment is added to:
- `pg_items`, all four query shapes (single or two tables, with or without `match`);
- step 1 of `search_pg_exact`, as `AND` after its `WHERE`, with `t.{id}`;
- `_search_pg_index`, as `AND` after its `WHERE`.

Step 2 (`_texts_query`) needs nothing, because the ids are already filtered.

**Facts**:

- psycopg 3.3.6, checked with `psycopg._queries.PostgresQuery.convert`:
  - With parameters, a single `%` that is not a placeholder is refused ("only '%s', '%b', '%t'
    are allowed as placeholders"), and `%%` is sent as `%`.
  - With an empty tuple, `%%` is also sent as `%`.
  - With `None`, the text is sent untouched, so `%%` would stay doubled.

  Hence "double, and never send `None`".
- With parameters, psycopg uses server-side binding, which cannot run several statements in one
  `execute()` ("cannot insert multiple commands into a prepared statement";
  [psycopg docs](https://www.psycopg.org/psycopg3/docs/basic/from_pg2.html)). `pg_connect`
  already sets `read_only = True` and REPEATABLE READ, so the condition cannot write either way.
- pgvector applies `WHERE` after the HNSW scan. Index mode already turns on
  `hnsw.iterative_scan = relaxed_order` and carries the approximate warning
  ([pgvector 0.8.0 README](https://pgxn.org/dist/vector/0.8.0/README.html)). Nothing new is
  needed.
- `pg_items`' up-front size refusal uses whole-table planner statistics. It is skipped when
  `where` is set, and the streaming check still runs.
- `pg_message` appends one line when `corpus.where` and `corpus.text_table` are both set and the
  error says a column "does not exist": "Filter columns must be in the text table (...)".

**Alternatives considered**: a `where_params` argument was dropped by the user. Running the
condition through `sql.SQL` without doubling `%` would break `LIKE 'vote%'` in every query that
has parameters.

## R5. S3 Vectors: the service's filter document, also applied when listing

**Decision**: `S3Corpus(where={...})`.
- `search_vectors` adds `filter=corpus.where` to the `query_vectors` parameters.
- `s3_items` keeps only vectors for which `_s3_match(corpus.where, v["metadata"])` is true.
- `__post_init__` walks the document with `_s3_check` and refuses an unknown `$` operator or a
  wrong operand type, naming the path to it.

**Facts**:

- botocore's `s3vectors` model: `QueryVectors` has a `filter` member of shape `Document`.
  `ListVectors` has only `vectorBucketName`, `indexName`, `indexArn`, `maxResults`, `nextToken`,
  `segmentCount`, `segmentIndex`, `returnData` and `returnMetadata`, so it has no filter.
- Documented operators and operands
  ([metadata filtering](https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-metadata-filtering.html)):

  | Operator | Operand |
  |---|---|
  | `$eq`, `$ne` | string, number or boolean |
  | `$gt`, `$gte`, `$lt`, `$lte` | number |
  | `$startsWith` | string; ENHANCED query behaviour only |
  | `$in`, `$nin` | non-empty array of primitives |
  | `$exists` | boolean |
  | `$and`, `$or` | non-empty array of filters |

  - A bare value means `$eq`.
  - `$eq` against a list value is true if any element matches.
  - Several operators on one key are combined with AND (example `{"price": {"$gte": 10, "$lte": 50}}`).
- **Not documented, the library's rule, marked unverified** (quickstart section 4):
  - several keys at the top level, or in one `$and` member, are combined with AND;
  - a vector without the key fails everything except `$exists: false`, `$ne` and `$nin`;
  - `$in` against a list value is true if any element is in the operand, and `$nin` if none is;
  - `$ne` against a list value is true if no element equals the operand.
- `$startsWith` is accepted for queries and refused in `s3_items` with a message, because whether
  it works depends on the index mode.

## R6. Agent skills

**Decision**: one new section "Filter the corpus (optional)" in
`src/goldlabel/skills/goldlabel-connect/SKILL.md`, with one code block per corpus type, and one
line in `goldlabel-candidates/SKILL.md` saying the filter belongs on the corpus.
- `test_skills.py::test_code_blocks_parse_and_use_real_names` already checks every `gl.` name in
  those blocks.
- A new test runs the Table block against a tiny fixture with `exec`, as
  `test_connect_skill_shaping_example_runs_and_leaves_the_source_alone` already does.
- The Postgres and S3 blocks cannot run without a service, so they are parsed only.
