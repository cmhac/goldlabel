# The whole chain as one notebook

The cells of one Jupyter notebook, in the order of the six stages. Each stage skill has the steps, the questions to ask and the checks; this is the shape of the result. Everything is in code: no side files for seeds, labels or the prompt.

The gold rule in `SKILL.md` applies throughout: you never create or edit a gold label. Where this page says "gold", people did the labelling.

```python
# Brief: posts that offer fake prizes, mode multi            (stage 1: connect)
import goldlabel as gl

corpus = gl.Table("posts.parquet", text_column="body", id_column="post_id")
# or gl.PgCorpus(table="posts", text_column="body", url_env="GOLDLABEL_PG_URL")
# or gl.S3Corpus(bucket="my-vectors", index="posts", region="us-east-1")

# stage 2: search terms, as variables
seeds = ["You have won a prize", "Claim your reward now"]
keywords = ["prize", "reward"]

# stage 3: the approved taxonomy
taxonomy = gl.Taxonomy(
    mode="multi",
    labels={
        "scam": "Offers a fake prize or payout for a fee or personal data.",
        "satire": "Obvious parody of a scam; nobody is meant to be deceived.",
    },
)

# stage 4: candidates (one of the three)
candidates = gl.get_candidates(
    corpus, seeds=seeds, embedder="openai:text-embedding-3-small"
)
# candidates = gl.get_candidates(corpus, keywords=keywords, limit=500)
# candidates = gl.get_candidates(corpus)
candidates

# stage 5: classifier, gold (people label), evaluation
prompt = "Classify each post by what it is doing, not by its topic."
clf = gl.Classifier("anthropic:claude-haiku-5-5", taxonomy, prompt=prompt)
gold = gl.Gold(candidates)  # 50 rows per sample by default
dev = gold.draw_sample("dev")  # safe to rerun: draws only what is missing
gl.label(dev, taxonomy)
ev = gl.evaluate(clf, dev, target=0.80)
ev

# stage 5, last: the held-out test sample, once
test = gold.draw_sample("test")
gl.label(test, taxonomy)
final = gl.evaluate(clf, test)  # run-once

# stage 6: estimate, then (after the user's yes) run
est = clf.estimate(candidates)
results = clf.classify(candidates, out="results.jsonl", max_cost=1.5 * est.dollars)
```

Keyword and whole-corpus lists have no similarity scores, so they have no bands, no floor and no `top_seeds`; read a sample with `hits.sample(20)` instead.

## The corpus formats

`gl.Table` takes a `.csv`, `.parquet` or `.jsonl` file, a list of row dicts, or a pandas or polars DataFrame. It needs a text column (`text_column`, a non-empty string in every row) and optionally an `id_column` (unique; the row's position is the id otherwise). For seeds it also needs `vector_column` (one list of numbers per row; not possible in a CSV) and `embedding_model` (the model that made them, which must equal the `embedder`). A Postgres table needs only its id and text columns unless seeds are used. The first bad row is named in the error; nothing is dropped or repaired.

## Keywords

A plain string is a literal, case-insensitive term. A compiled `re.Pattern` keeps its own flags, and each term is searched separately. `regex=True` makes the strings patterns, written as they are (use `(?i)` for case-insensitive). A term that matches the empty string is refused, but zero-width patterns such as `\b` still match every word, so do not use them alone. `server_side=True` (Postgres only) has the database do the matching: plain terms use `ILIKE`; with `regex=True` the strings use Postgres syntax. Postgres rows are read in ascending id order; for S3 Vectors the order is the service's, so a `limit` there is not repeatable.

`gl.label` waits until the person presses Done, and returns at once if every row is already labelled; tell the user to expect the page in their browser. `gold.remove(ids)` moves rows to a `.removed.jsonl` file and is destructive: ask first.
