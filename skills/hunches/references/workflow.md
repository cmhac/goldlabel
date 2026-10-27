# Workflow: from the brief to the first evaluation

A guide to the idioms, in the order they usually come. Skip, repeat or reorder as the user's work needs. After each step, show the result (the objects display themselves in a notebook; `print()` them in a script) and ask what to do next.

Remember the gold rule in `SKILL.md`: you never create or edit a gold label. Where this guide says "gold", the labelling is done by people.

## 1. Ask before writing code

- **The brief.** What is being looked for, in one or two sentences, and what would make an item a match? Write it in the notebook's first cell as a comment or a markdown cell so the reader sees what the numbers are about.
- **The candidates.** Seeds, keywords or the whole corpus (see section 2)? Keywords are cheap and exact; seeds find what is worded differently; the whole corpus is for a corpus that is already small or already filtered.
- **The seeds.** Short phrases that would be true of a match (not keywords: sentences a matching item could contain). Ask the user for them or propose a handful and ask which are right. Keep them in `seeds.csv` (one per line, header `seed`) or in a list in the notebook.
- **`single` or `multi`.** Is each item exactly one label (`single`), or can it carry several (`multi`)? `off_topic` is always there, exclusive, and means "not a match"; do not define it yourself.
- **Label descriptions.** One or two sentences per label that say what it is and how it differs from the nearest label ("Offers a prize or payout in exchange for a fee or personal data. Not satire, and not a genuine promotion by a named brand."). Ask the user to confirm them; they decide where the lines fall.

## 2. Corpus and candidates

`get_candidates` returns the items to classify. Ask which kind of list the user wants: **seeds** (semantic search; needs embeddings and an embedder), **keywords** (literal terms or regular expressions; no embeddings), or **the whole corpus** (no filter at all; the classifier then reads every item, so show the estimate first).

```python
import hunches as hn

# one of:
corpus = hn.PgCorpus(url_env="HUNCHES_PG_URL", table="posts", text_column="body")
# corpus = hn.S3Corpus(bucket="my-vectors", index="posts", region="us-east-1")
# corpus = hn.Table("posts.parquet", text_column="body", id_column="post_id")

# seeds: semantic search (the corpus must have embeddings; see the table format below)
seeds = hn.read_seeds("seeds.csv")  # or a plain list[str]
candidates = hn.get_candidates(
    corpus, seeds=seeds, embedder="openai:text-embedding-3-small"
)
candidates  # count, similarity bands, and a WARNING if the backend capped the results

# keywords: ranked by distinct terms matched, then total matches (terms_matched, matches)
hits = hn.get_candidates(corpus, keywords=["ballot", "poll worker"], limit=500)

# the whole corpus, in the corpus's order
everything = hn.get_candidates(corpus)
```

One filter per call, `seeds=` or `keywords=`. For seeds, `embedder` must be the model the corpus was embedded with. A seed search writes `.hunches/candidates.jsonl` (keyword and whole-corpus lists are written only when `out=` is a path); running it again with one changed seed re-embeds only that seed. Show `candidates.bands()` and `candidates.top_seeds(0.70)` to the user: which seeds bring in the items, and are the top items what they meant? A seed that brings in junk is a reason to reword the seed, not to change the classifier. Keyword and whole-corpus lists have no similarity scores, so they have no bands, no floor and no `top_seeds`; look at the first rows with `hits.sample(20)` instead.

**Keywords.** A plain string is a literal, case-insensitive term. A compiled `re.Pattern` keeps its own flags, and each term is searched separately (a pattern with `re.IGNORECASE` does not make the next one case-insensitive). `regex=True` makes the strings patterns, written as they are (use `(?i)` for case-insensitive). A term that matches the empty string is refused, but zero-width patterns such as `\b` still match every word, so do not use them alone.

**On the server (`PgCorpus` only).** `server_side=True` has the database do the matching, which suits a table too large to read: plain terms use `ILIKE`; with `regex=True` the strings are sent as they are and use Postgres syntax (compiled patterns are refused). Ranking and `limit` stay in the library, which warns if its own count of a returned row disagrees with the server's. Postgres rows are read in ascending id order. For S3 Vectors the order is the service's, so a `limit` there is not repeatable.

**The table format.** `hn.Table` takes a `.csv`, `.parquet` or `.jsonl` file, a list of row dicts, or a pandas or polars DataFrame. It needs a text column (`text_column`, a non-empty string in every row) and optionally an `id_column` (unique; the row's position is the id otherwise). For seeds it also needs `vector_column` (one list of numbers per row; not possible in a CSV) and `embedding_model` (the model that made them, which must equal the `embedder`). A Postgres table needs only its id and text columns unless seeds are used. The first bad row is named in the error; nothing is dropped or repaired.

For a database, `corpus.check()` (on `PgCorpus` only) reports problems with the table and column before searching. The URL stays in the environment variable; never type it into the notebook.

## 3. Taxonomy and classifier

```python
taxonomy = hn.Taxonomy(
    mode="multi",  # or "single"
    labels={
        "scam": "Offers a fake prize or payout for a fee or personal data.",
        "satire": "Obvious parody of a scam; nobody is meant to be deceived.",
    },
)
taxonomy.write("taxonomy.yaml")

prompt = "Classify each post by what it is doing, not by its topic."
clf = hn.Classifier("anthropic:claude-haiku-5-5", taxonomy, prompt=prompt)
clf
```

Keep the prompt in a file (`prompt.md`) once it is more than a line, so changes show up in git. The model is a pydantic-ai model string; ask the user which one (and which provider key they have in the environment). The classifier is immutable: `clf.with_prompt(text)` and `clf.with_taxonomy(t)` return new ones, so `clf_v1` and `clf_v2` can sit side by side.

## 4. Gold: people label

```python
gold = hn.Gold()  # .hunches/gold.jsonl
gold.draw(
    candidates, n=50, split="dev"
)  # pending rows with no labels; samples without repeats
hn.label(
    gold, taxonomy
)  # opens the labelling page; returns when the person presses Done
```

`hn.label` blocks until the person is done: tell the user to expect the page in their browser, and do not run it while they are not there. The page never shows a prediction. If the user already has a human-labelled dataset, that is allowed (see the Full rule in `SKILL.md`): ask who labelled it and how, then

```python
rows = [
    {"id": "a1", "text": "You won!", "labels": ["scam"]}
]  # as read from THEIR file, unchanged
gold.import_rows(rows, split="dev")
```

and tell the user what the file says about who labelled it. Never add, correct or fill in a label. `gold.dev.counts(taxonomy)` shows how many rows each label has; if a label has almost none, say so and suggest drawing more or adding seeds that find it, which is the user's call. `gold.orphaned(taxonomy)` lists rows whose labels are no longer in the taxonomy; `gold.remove(ids)` moves rows to a `.removed.jsonl` file and is destructive: ask first.

## 5. First evaluation

```python
ev = hn.evaluate(
    clf, gold.dev, target=0.80
)  # classifies the dev rows (cached) and scores them
ev  # metrics, per-label table, how many rows came from each source, the disagreements
ev.disagreements_to_polars()
```

`target` shows PASS or FAIL beside the score; ask the user what target they want. Read `references/tuning.md` next.

## When you cannot edit notebooks

If your tools cannot edit `.ipynb` JSON reliably, write the pipeline as a plain script with `# %%` cell markers, one step per cell, and tell the user they can open it as a notebook (VS Code and Spyder understand `# %%`) or convert it with `jupytext --to ipynb pipeline.py`. The library has no jupytext dependency. Everything above works unchanged in a script; `print()` the results instead of leaving them as the last line of a cell.

```python
# %% Brief: posts that offer fake prizes, mode multi
import hunches as hn

# %% Search
candidates = hn.get_candidates(
    hn.PgCorpus(table="posts", text_column="body"),
    seeds=hn.read_seeds("seeds.csv"),
    embedder="openai:text-embedding-3-small",
)
print(candidates)
```
