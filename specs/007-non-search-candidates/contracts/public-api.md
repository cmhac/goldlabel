# Contract: public API changes

**Spec**: [../spec.md](../spec.md) | **Data model**: [../data-model.md](../data-model.md)

`src/hunches/__init__.py` `__all__`: remove `LocalCorpus`, `search`, `asearch`; add `Table`,
`get_candidates`, `aget_candidates`. Everything else is unchanged.

## `hn.get_candidates` / `hn.aget_candidates`

```python
def get_candidates(
    corpus: Table | S3Corpus | PgCorpus,
    *,
    seeds: Sequence[str] | None = None,
    embedder: str | Embedder | None = None,
    floor: float | None = None,       # seeds only; None means 0.60 as before
    keywords: Sequence[str | re.Pattern] | None = None,
    regex: bool = False,              # keywords only; strings are patterns, without flags
    server_side: bool = False,        # keywords only; PgCorpus only
    limit: int | None = None,
    out=None,                         # None: default file for seeds only; False: none; path
    cache=None,                       # seeds only (embedding cache)
) -> Candidates
```

`aget_candidates` is the same with `async def`. The sync form is `_sync.run(aget_candidates(...))`.

### Argument rules (all `ValueError` unless stated; the message names the argument)

| Situation | Result |
|---|---|
| `seeds` and `keywords` both given | refused: one filter per call |
| `seeds=[]` or `keywords=[]` | refused (empty is not "no filter") |
| `seeds` or `keywords` is a bare `str` | `TypeError`, same style as today's seeds message |
| `seeds` given, `embedder` missing | refused |
| `embedder`, `floor` or `cache` given without `seeds` | refused |
| `regex=True` or `server_side=True` without `keywords` | refused |
| `limit` below 1 | refused |
| a blank term, or a pattern with `p.match("")` | refused, names the term |
| invalid regex (Python side) | `re.error` message naming the pattern, raised before the corpus is read; not applied to the regex strings of a `server_side=True` call, where the database rejects an invalid one and the error names the term |
| `server_side=True` on a `Table` or `S3Corpus` | refused: only a `PgCorpus` can filter on the server |
| `server_side=True` with a compiled `re.Pattern` | refused, names the term |
| seeds on a `Table` with no `vector_column` | refused: the table has no embedding column; keywords and the whole corpus need none |
| seeds on a `Table` with no `embedding_model`, or a different one | refused (message shows both names) |

### Behaviour

- No filter: all items in corpus order; `limit` keeps the first N.
- `keywords`: items matching any term, ranked (data model); `limit` keeps the best N; memory is
  bounded by `limit` (streaming `nsmallest`).
- `seeds`: as `search` did, plus `limit` keeps the N most similar. A `Table` is read once for all
  seeds (`search_table`), not once per seed.
- Async: every blocking read runs in one `asyncio.to_thread` call; the sync form works inside a
  running notebook loop.
- `source` on the result is `"seeds"`, `"keywords"` or `"all"`.
- Output file: `out` a path writes it (all sources); `out is None` writes
  `<settings.root>/candidates.jsonl` for seeds only; `out=False` writes nothing.
- Read-only everywhere: no write to the table, the bucket or the database.

### Server-side statement (PgCorpus, `server_side=True`, keywords only)

One named-cursor statement per call, read-only transaction from `pg_connect`:

```sql
SELECT {id}, {text} FROM {table} WHERE {text} ILIKE ANY(%s::text[]) ORDER BY {id}     -- plain text
SELECT {id}, {text} FROM {table} WHERE {text} ~ ANY(%s::text[])     ORDER BY {id}     -- regex strings
-- two-table layout: ... FROM {table} t JOIN {text_table} x ON x.{text_id} = t.{id} WHERE x.{text} ...
```

The single parameter is a list of strings, cast to `text[]` in the statement. For plain text each element is `%` + term with `\`, `%`, `_`
escaped by a backslash + `%`. For regex strings the elements are the strings unchanged. Identifiers
only ever come from `psycopg.sql.Identifier`. The returned rows are matched again in Python to
compute `terms_matched` and `matches`; a row that counts zero is kept and ranks last, and one
`UserWarning` names any term that Python could not compile or that counted zero on a returned row.

## `hn.Table`

See the data model. `Table("posts.csv", text_column="body", id_column="post_id")`.

## `Candidates`

- New last field `source: str = "seeds"`.
- `above()`, `bands()`, `top_seeds()`: `ValueError("<name> needs similarity scores, but this list
  was built from <source>, not from seeds")` for non-seed sources.
- `evaluation.band_sample(candidates, ...)`: same error.
- `__repr__` / `_repr_html_`: seeds unchanged; keywords print
  `N candidates (from keywords)` and a table with `terms_matched` and `matches`; whole corpus
  prints `N candidates (whole corpus)`. No bands, floor, similarity or seed column outside seeds.
- `write` / `read` round-trip `source`; `read` of a file without it gives `"seeds"`.

## Documentation contract

README, `docs/agent-instructions.md` (kept equal to the README block), `skills/hunches/` and
`AGENTS.md` describe `get_candidates` and `Table` (the format a table should have: text column,
optional id column, embedding column and model for seed search, accepted files and DataFrames) and
never mention the removed corpus or its folder layout (spec FR-024).
