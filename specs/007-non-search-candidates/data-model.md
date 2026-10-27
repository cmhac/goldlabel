# Data Model: Non-search candidate sources

**Spec**: [spec.md](spec.md) | **Research**: [research.md](research.md)

## Table (new corpus kind; replaces `LocalCorpus`)

A frozen dataclass in `src/hunches/search.py`, `eq=False`.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `source` | `str \| Path \| list[dict] \| DataFrame` | required | A `.csv`, `.parquet` or `.jsonl` path, a list of row dicts, or a pandas or polars DataFrame. |
| `text_column` | `str` | `"text"` | Column holding the text. |
| `id_column` | `str \| None` | `None` | Column holding the id; `None` means the row's position as text. |
| `vector_column` | `str \| None` | `None` | Column holding one list of numbers per row; needed only for seed search. |
| `embedding_model` | `str \| None` | `None` | The model that made the vectors; needed only for seed search. |

Construction check (no I/O): a CSV path with `vector_column` set is refused. Everything else is
checked when the table is read.

Read rules (one function, `table_rows`): see research R2. Output is a list of dicts with at least
`id` (str) and `text` (str non-empty), plus the vector column when asked for. Failure cases and
their first-offender messages: missing column, text not a non-empty `str`, missing id, repeated id,
vector not a list of numbers, vectors of different lengths.

## Other corpora (unchanged descriptors)

`PgCorpus` and `S3Corpus` keep their fields. New read-only behaviours (no new fields):

| Corpus | Whole-corpus / Python-side keyword read | Server-side keyword read |
|---|---|---|
| `Table` | rows in table order | not supported (refused) |
| `PgCorpus` | named cursor, `ORDER BY id`, batches of `PG_BATCH`; two-table layout joined | same cursor with a `WHERE` on `ILIKE ANY` / `~ ANY` |
| `S3Corpus` | `list_vectors` pages (keys and metadata only), service order | not supported (refused) |

## Item (internal, not a class)

The reader yields `(id: str, text: str)` pairs. Nothing else is carried.

## Term (internal, not a class)

A `re.Pattern`. Built from a plain string (`re.escape`, `re.IGNORECASE`), a string with `regex=True`
(as written), or a compiled pattern (as given). Server-side, terms stay strings and are sent as
parameters (see contracts).

## Candidates (existing dataclass, one field added)

| Field | Seeds | Keywords | Whole corpus |
|---|---|---|---|
| `rows[i]` keys | `id, text, max_similarity, best_seed` | `id, text, terms_matched, matches` | `id, text` |
| `source` (new, last field, default `"seeds"`) | `"seeds"` | `"keywords"` | `"all"` |
| `capped` | as today | `False` | `False` |
| `floor` | the floor | `None` | `None` |
| `seeds_digest` | digest of the seeds | `None` | `None` |
| `embedding_model` | the embedder's model | `None` | `None` |
| row order | similarity desc, then id | `terms_matched` desc, `matches` desc, corpus order | corpus order |

`.meta.json` gains `"source"`; a file without it is read as `"seeds"`. For non-seed sources
`floor` is written as `null`.

Operations by source: `sample`, `to_polars`, `to_pandas`, `write`, `read`, `Gold.draw`,
`Classifier.estimate`/`classify` work on all three; `above`, `bands`, `top_seeds` and
`band_sample` raise `ValueError` for `keywords` and `all` (message names the source).

## State transitions

None: every call returns a value; the only file written is the optional `out`.
