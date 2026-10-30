---
name: goldlabel-search-terms
description: "Use when deciding how to find the items that matter in a corpus with goldlabel: turning what the user wants to analyse into keywords, regular expressions or semantic-search seed phrases, choosing between them depending on whether the data has embeddings, writing seeds.csv, and trying the terms on a small sample before running them for real. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Choose and draft the search terms

Goal: a short list of keywords, regular expressions or seed phrases that the user has read and approved, tried on a few results. Before this: `goldlabel-connect`. After: `goldlabel-candidates`.

## Ask first

1. **The brief.** In one or two sentences, what is being looked for and what would make an item a match? Write it in the first cell of the notebook so the reader sees what the numbers are about.
2. **Which kind of list**, decided by the data and the user, never by you:
   - **Keywords or regular expressions**: no embeddings needed; literal and exact; cheap. Right for a distinctive vocabulary, and the only option for data without vectors.
   - **Seeds**: needs embeddings and the embedder that made them; finds items worded differently from your terms.
   - **The whole corpus**: no filter; right only when the corpus is already small or already filtered. The classifier reads every item, so the estimate in `goldlabel-run` matters.

## Draft a proposal, then let the user edit it

Propose a handful and say why each is there; the user adds, removes and rewrites. Nothing you generate is final.

- **Keywords**: 10 to 20 terms grouped by idea (the topic words, the slang, the misspellings the user knows). A plain string is a literal, case-insensitive term. For patterns use `regex=True` with the pattern written as it is, `(?i)` for case-insensitive (`(?i)vote[sd]?`), or compiled `re.Pattern` objects, which keep their own flags. A pattern that can match the empty string is refused; zero-width patterns such as `\b` still match every word, so never use one alone.
- **Seeds**: 5 to 10 short sentences that would be true of a match, not keywords: what a matching item could say. Cover different wordings of the same idea; a seed that is too general pulls in junk. Keep them in `seeds.csv` (header `seed`).

```python
import goldlabel as gl
import polars as pl

pl.DataFrame({"seed": ["I lost my job", "The company is cutting staff"]}).write_csv(
    "seeds.csv"
)
seeds = gl.read_seeds("seeds.csv")
```

## Try them on a small sample before the real run

```python
# keywords: ranked by distinct terms matched, then total matches
hits = gl.get_candidates(corpus, keywords=["ballot", "poll worker"], limit=200)
hits.sample(10, seed=1).rows  # read them with the user: are these matches?

# regular expressions
rx = gl.get_candidates(corpus, keywords=[r"(?i)vote[sd]?"], regex=True, limit=200)

# a very large Postgres table: let the database do the matching
big = gl.get_candidates(corpus, keywords=["ballot"], server_side=True, limit=500)
```

Show the user ten results per term group and what they look like. Count how many results each term brings in and point out a term that brings in nearly everything or nearly nothing. For seeds, trying them for real is the next skill (`goldlabel-candidates`), because it embeds the seeds and shows the similarity bands; do not run a large seed search before the user has approved the seeds.

## Next

Save the approved terms (`seeds.csv`, or a list in the notebook) and go to `goldlabel-candidates`.
