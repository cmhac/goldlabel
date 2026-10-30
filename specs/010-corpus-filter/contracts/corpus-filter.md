# Contract: `where` on the corpus classes

Public API change: one keyword field per corpus class. Every other public name and signature is
unchanged, and `get_candidates` / `aget_candidates` take no new argument.

## `gl.Table(source, text_column="text", id_column=None, vector_column=None, embedding_model=None, where=None)`

- `where`: `polars.Expr | None`. Rows for which it is true are kept, and rows where it is false or
  null are dropped. It is evaluated on the source's own columns, before the id and text checks.
- `TypeError`, when the Table is built, if `where` is not a polars expression.
- `ValueError("Table where: ...")` on reading, if polars cannot evaluate it, keeping polars'
  message.
- `ValueError("Table: polars could not read the source: ...")` on reading, if polars cannot build
  the frame.
- CSV values are text: `pl.col("year").cast(pl.Int64) >= 2024`.

```python
import polars as pl
corpus = gl.Table("posts.csv", text_column="body", id_column="post_id",
                  where=pl.col("section").is_in(["politics", "opinion"]))
```

## `gl.PgCorpus(table, ..., where=None)`

- `where`: `str | None`. One Postgres boolean condition with its values written in. A quote in a
  value is doubled, and `%` is written once.
- `ValueError`, when the corpus is built, if it is not a string or is blank.
- It runs in the read-only transaction in every mode: whole corpus, keywords (Python or
  `server_side`), and seeds (`exact` and `index`).
- It is always wrapped as `id IN (SELECT id FROM <text table or table> WHERE (...))`. With
  `text_table`, it sees only the text table's columns. A column that is only in the vector
  table gives the database's error plus "Filter columns must be in the text table".

```python
corpus = gl.PgCorpus(table="posts", text_column="body",
                     where="section = 'politics' AND published >= '2024-01-01'")
```

## `gl.S3Corpus(bucket, index, region=None, where=None)`

- `where`: `dict | None`, the S3 Vectors metadata filter document.
- `ValueError`, when the corpus is built, for an empty document, an unknown `$` operator or a
  wrong operand type,
  naming the path (for example `where["$and"][1]["year"]["$gte"]`).
- Seeds: sent as `filter` on every `query_vectors` call.
- Whole corpus and keywords: the same document, applied by goldlabel to each listed vector's
  metadata. `$startsWith` is refused there with a message.

```python
corpus = gl.S3Corpus(bucket="my-vectors", index="posts",
                     where={"$and": [{"section": "politics"}, {"year": {"$gte": 2024}}]})
```
