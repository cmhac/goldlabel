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
with your taxonomy. Start it from the notebook with `gl.label` or from a terminal with `goldlabel label`
(see [Review and revise labels](#review-and-revise-labels)).

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
uv add goldlabel
uv add "goldlabel[s3]"      # boto3, for an S3 Vectors corpus
uv add "goldlabel[pg]"      # psycopg, for a pgvector (PostgreSQL) corpus
uv add "goldlabel[rds]"     # psycopg and boto3, for RDS / Aurora IAM database authentication
uv add "goldlabel[local]"   # Sentence Transformers, for local query embeddings (Python < 3.14)
```

## Installing skills

Goldlabel ships agent skills that walk you through the six steps above with a coding agent. They are optional: goldlabel
is plain functions, and the example workflow below works without an agent.

```bash
uv run goldlabel install claude    # or codex, copilot, kiro, all
```

This copies the skills into the agent's skills folder in your project (`.claude/skills` for Claude Code, `.agents/skills`
for Codex and Copilot, `.kiro/skills` for Kiro). `--global` installs them for your whole user instead, `--dir PATH`
writes them anywhere else, and `uv run goldlabel install --help` lists every option. Restart the agent if it does not list
the new skills.

**Start with `/goldlabel`.** It checks the notebook and the `.goldlabel/` folder you already have, tells you which of the
six steps look done, and names the skill for the next one, so you can call it at any point without knowing which skill
comes next. There is one skill per step (`goldlabel-connect`, `goldlabel-search-terms`, `goldlabel-taxonomy`,
`goldlabel-candidates`, `goldlabel-tune`, `goldlabel-run`), and at the end of each the agent tells you which comes next.

A session looks like a conversation. At each step the agent says what the step is for, shows you the result (the connected
data, the search terms, a draft taxonomy, the candidates, an evaluation), asks for the decision that is yours, and waits for
your yes before moving on. It writes only goldlabel calls, into one notebook, so the notebook is the record of the analysis.
It never writes a gold label: when it is time to label, it tells you to open the labelling page and you label there.

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

### Review and revise labels

```bash
uv run goldlabel label            # every dataset in the storage folder
uv run goldlabel label corpus-b   # open one dataset (gl.Gold(candidates, name="corpus-b"))
```

The page lists each dataset and sample with its row counts, opens any row by id, and lets a person change a label or
note at any time, even after evaluations ran. A row that was already labelled keeps its earlier values in a `revisions`
list in `gold.json`. For each sample the page also lists its evaluations with the classifier's disagreements, and marks an
evaluation **STALE** when a row was revised after it ran. Evaluations are still run from code. If a page is already running,
`gl.label(dev, taxonomy)` prints its URL and waits there instead of starting a second one. From 1024px wide the text and the
label list scroll on their own, so the text stays in view; on a narrow window the page is one column and scrolls as one.
