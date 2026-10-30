---
name: goldlabel-candidates
description: "Use when running goldlabel candidate generation and judging the result: calling get_candidates with seeds, keywords or the whole corpus, reading the similarity bands and which seeds or terms bring in which items, deciding whether to reword terms, and saving the candidate list. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Run and inspect candidate generation

Goal: a candidate list the user has looked at and trusts. Before this: the approved terms from `goldlabel-search-terms`. After: `goldlabel-tune`.

## Run it

```python
import goldlabel as gl

# seeds: semantic search (the corpus needs vectors; the embedder must be the model that made them)
seeds = gl.read_seeds("seeds.csv")
candidates = gl.get_candidates(
    corpus, seeds=seeds, embedder="openai:text-embedding-3-small"
)
candidates  # count, similarity bands, and a WARNING if the backend capped the results

# keywords or regular expressions, ranked by distinct terms matched
candidates = gl.get_candidates(
    corpus, keywords=["ballot", "poll worker"], limit=2000, out="candidates.jsonl"
)

# the whole corpus, in the corpus's order
candidates = gl.get_candidates(corpus)
```

One filter per call, `seeds=` or `keywords=`. A seed search embeds the seeds (a small live cost, one call per seed, cached; changing one seed re-embeds only that one) and writes `.goldlabel/candidates.jsonl`; keyword and whole-corpus lists are written only when `out=` is given. The embedding model needs its provider key in the environment: if it is missing, tell the user which variable to set and stop; never ask for the value.

## Inspect it with the user

```python
candidates.bands()  # seeds only: how many items fall in each similarity band
candidates.top_seeds(0.70)  # seeds only: which seeds bring in the items above 0.70
candidates.sample(20, seed=1).rows  # read twenty, not just the top
candidates.rows[:10]
```

Report in words: how many items, how they spread over the bands, which seeds or terms do the work and which bring in nothing, a WARNING if the backend capped the results (hits above the floor may be hidden), and what the top, middle and bottom items look like. Ask whether the top items are what they meant. Keyword and whole-corpus lists have no similarity, no bands, no floor and no `top_seeds`: read a sample instead.

## What to change

- Junk at the top: the seed or term is wrong. Reword or drop it, then run again. That is a reason to change the search, not the classifier.
- Missing things the user knows exist: add a seed or term worded the way those items are worded.
- Far too many or too few: a seed that is too general or too narrow; for keywords, `limit=` caps the list and the ranking decides what is kept.

The similarity cutoff (which items are classified at all) is the user's decision and is made later, on a band sample, in `goldlabel-run`. Do not choose it here. `candidates.above(0.70)` shows what a cutoff would keep.

## Next

`goldlabel-tune`: build the classifier, get people to label a gold set, and tune the prompt on it.
