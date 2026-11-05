# goldlabel

Goldlabel helps you do text content analysis with LLMs classifiers accurately, transparently, and quickly. 
You bring a source of text — in a dataframe, postgres database, vector store — and goldlabel helps you 
label that text and evaluate the accuracy of the classifier using gold datasets. 

## The workflow

Goldlabel is a series of functions you run step by step. Here's a high-level overview of the steps.

### 1. Gather candidates for classification

Connect goldlabel to your data source and decide which data you're going to classify. You can run the classifier
on the whole data source, or filter it in a number of ways including keywords, regular expressions, and even 
semantic search if your data includes embeddings.

### 2. Build taxonomy

Decide how you want to classify your data. You build a set of labels and descriptions which are passed to the LLM,
which classifies each text into one of your labels or a generic `off_topic`.

### 3. Label a dev dataset

Goldlabel draws a random sample of the candidates, then opens a small web app to help you quickly label each item
with your taxonomy. 

### 4. Evaluate the gold dataset and tune the prompt

Run the classifier on your hand-labeled items. Goldlabel reports an accuracy rate, and you review the disagreements,
making changes to the prompt to increase the accuracy rate. You continue running until you reach a desired accuracy
rate. 

### 5. Label + evaluate a test dataset 

Goldlabel draws another random sample and you label them in the web app. You run the classifier on this held-out
set, and assess teh accuracy rate. If it is high enough, your classifier is ready. If it is not, continue to tune
the taxonomy or prompt or switch models, and draw another test dataset and try again. 

### 6. Classify

Run the classifier on the entire corpus. Goldlabel tells you in advance how much it will cost and how long it will 
take.

## Install

```
ub add goldlabel
ub add "goldlabel[s3]"      # boto3, for an S3 Vectors corpus
ub add "goldlabel[pg]"      # psycopg, for a pgvector (PostgreSQL) corpus
ub add "goldlabel[rds]"     # psycopg and boto3, for RDS / Aurora IAM database authentication
ub add "goldlabel[local]"   # Sentence Transformers, for local query embeddings (Python < 3.14)
```

## Installing skills

Goldlabel comes with a set of agent skills to help you work interactively with a coding agent. Install the skills
with `uv run goldlabel install <harness>`. Use `uv run goldlabel install --help` for a list of supported agent
harnesses.

## Example workflow

```python
import goldlabel as gl

# 1. Candidates: keyword search over a table (seeds= does semantic search if your rows have embeddings)
corpus = gl.Table("posts.csv", text_column="body", id_column="post_id")
candidates = gl.get_candidates(corpus, keywords=["laid off", "layoffs"])

# 2. Taxonomy and classifier (set OPENAI_API_KEY in your environment first)
taxonomy = gl.Taxonomy(
    mode="single",
    labels={
        "layoff": "The author lost their job, or expects to.",
        "burnout": "The author is worn out by their work.",
    },
)
clf = gl.Classifier(
    "openai:gpt-6-luna",
    taxonomy,
    prompt="Choose the one label that fits the post best.",
)

# 3. Label a dev sample: opens the web app, returns when you press Done
gold = gl.Gold(candidates)  # .goldlabel/gold.json, 50 rows per sample by default
dev = gold.draw_sample("dev")  # safe to rerun: it draws only what is missing
gl.label(dev, taxonomy)

# 4. Evaluate, read the disagreements, tune the prompt, evaluate again
ev = clf.evaluate(dev, target=0.9)
ev.disagreements_to_polars()
clf = clf.with_prompt(
    "Choose the one label that fits the post best. Rumoured redundancies count as layoff."
)
ev = clf.evaluate(dev, target=0.9)

# 5. Label and evaluate a held-out test sample, once
test = gold.draw_sample("test")
gl.label(test, taxonomy)
clf.evaluate(test, target=0.9)

# 6. Classify everything: the estimate calls no model, and max_cost refuses to overspend
clf.estimate(candidates)
results = clf.classify(candidates, out="results.jsonl", max_cost=25.0)
results.to_polars()
```

### Gold samples

A gold dataset is one file in `.goldlabel/` (`gl.Gold(candidates)` is `gold.json`; `gl.Gold(candidates_b, name="corpus-b")` is
`gold-corpus-b.json`, for a second corpus). It holds samples, each a name you choose: `gold.draw_sample("dev")` makes sure
the sample "dev" has 50 rows (or `n=`), so rerunning the cell draws nothing, and the rows come in an order fixed by their ids,
so there is no seed. `gl.label(dev, taxonomy)` shows only that sample's pending rows. Every `clf.evaluate` is logged in
`.goldlabel/evals.jsonl`, and a sample's summary says how often it was evaluated: keep your test sample held out and score it
once. If you decide to keep tuning after scoring it, `tuning = dev + test` adds it to the tuning set (nothing is written) and
`gold.draw_sample("test-2")` draws a fresh one.
