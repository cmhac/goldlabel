---
name: goldlabel-connect
description: "Use when pointing goldlabel at the data for the first time or when it will not load: connecting to a file, a DataFrame, a pgvector (Postgres) table or an S3 Vectors index, confirming the connection and the id and text columns work, finding out whether the data has embeddings, or reshaping data into a form the library reads. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Connect to the data and shape it

Goal: a corpus object that works, shown to the user with its first rows, before anything is searched. This is the first stage; the next is `goldlabel-search-terms`.

## Ask first

1. Where is the data: a file (`.csv`, `.parquet`, `.jsonl`), rows already in a notebook (a list of dicts, a polars or pandas DataFrame), a Postgres table with pgvector, or an S3 Vectors index?
2. Which column holds the text, and which the id (unique)? If there is no id column the row's position is the id.
3. Does it have embeddings, and from which model? Seeds (semantic search) need them; keywords and the whole corpus do not.
4. For a database or AWS: which environment variable holds the URL or credentials. The user sets it; you never ask for the value and never type it into a file, a notebook or the chat.

## Connect and look

```python
import goldlabel as gl

# a file or a DataFrame
corpus = gl.Table("posts.parquet", text_column="body", id_column="post_id")
# with embeddings, for seeds (the model that made the vectors, exactly):
# corpus = gl.Table("posts.parquet", text_column="body", id_column="post_id",
#                   vector_column="embedding", embedding_model="text-embedding-3-small")

# a pgvector table: the URL is read from the variable named here, never stored
# corpus = gl.PgCorpus(table="posts", id_column="post_id", text_column="body", url_env="GOLDLABEL_PG_URL")
# corpus = gl.S3Corpus(bucket="my-vectors", index="posts", region="us-east-1")

first = gl.get_candidates(corpus, limit=5)  # the first five items, no filter
first.rows
```

An import error names the missing extra: `pip install "goldlabel[pg]"` (Postgres), `"goldlabel[s3]"` (S3 Vectors), `"goldlabel[rds]"` (RDS or Aurora IAM sign-in). For a Postgres table, check the table before searching:

```python
report = corpus.check()  # never raises; read-only
(
    report["errors"],
    report["warnings"],
    report["notes"],
)  # empty errors means the connection works
report["version"], report["rows"], report["sample"]
```

## Confirm, then say it in words

Tell the user: the connection works (or the first error, quoted), how many items were read (do not count a whole large database; say the estimate from `report["rows"]`), that the first rows look like the text they expect, and whether embeddings are present. If seeds are wanted and there are no vectors, say so plainly: seeds cannot work without them; keywords can. Never create embeddings or fill in a missing column yourself without asking.

## When the data is not in a readable shape

The error names the first bad row (wrong column name, empty text, a nested field, vectors in a CSV, a duplicate id). Nothing is dropped or repaired by the library, and you do not do it silently either. Write a short, readable transform that reads the original and writes a new file, leaving the original untouched, show it to the user, and run it only after they agree:

```python
import polars as pl

raw = pl.read_json("export.json")  # the source file is never modified
rows = raw.select(
    pl.col("post_id").cast(pl.Utf8).alias("id"),
    pl.col("body").alias("text"),
)
rows.filter(
    pl.col("text").is_null() | (pl.col("text") == "")
).height  # report this count first
rows.write_ndjson("posts.jsonl")
corpus = gl.Table("posts.jsonl", id_column="id")  # text column defaults to "text"
```

If rows have to be dropped (empty text, duplicates), say how many and which, and let the user decide. This applies to the corpus only: you never touch a gold file.

## Next

`goldlabel-search-terms`: decide how to find the items that matter.
