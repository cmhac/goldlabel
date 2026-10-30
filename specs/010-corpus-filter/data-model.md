# Data model: corpus filters

No new class. Each corpus dataclass gets one optional field, `where`, defaulting to `None`. With
`None`, the corpus behaves and reads exactly as before.

| Corpus | `where` type | Checked when built | Applied |
|---|---|---|---|
| `Table` | `polars.Expr` | `isinstance(where, pl.Expr)`, else `TypeError` | `df.filter(where)` in `table_rows`, before the row checks; so whole corpus, keywords and seeds all see it |
| `PgCorpus` | `str` | a string with non-blank text, else `ValueError` | in the database: `pg_items` (4 query shapes), `search_pg_exact` step 1, `_search_pg_index`; two-table layout through the text table only |
| `S3Corpus` | `dict` (the service's filter document) | `_s3_check`: known operators, operand types, non-empty `$and`/`$or`/`$in`/`$nin`; else `ValueError` naming the path | `filter=` on every `query_vectors`; `_s3_match` on each listed vector's metadata in `s3_items` |

Rules:

- The field is part of the frozen dataclass, so it shows in `repr` and cannot change after the
  corpus is built.
- Nothing about the filter is written to `candidates.jsonl`, `.meta.json` or `evals.jsonl`.
- `Candidates` is unchanged: a filtered corpus gives an ordinary `source="all"`, `"keywords"` or
  `"seeds"` list.

Postgres fragment (R4), where `id` is `t.{id}` or `{id}` depending on the query:

```text
one table:   ... AND (<where, every % doubled>)
two tables:  ... AND <id> IN (SELECT <text_id> FROM <text_table> WHERE (<where, every % doubled>))
```

S3 listing semantics (R5): the documented operators, plus the four undocumented rules marked as
unverified.
