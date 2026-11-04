---
name: goldlabel-candidates
description: "Use when running goldlabel candidate generation and judging the result: calling get_candidates with seeds, keywords or the whole corpus, reading the similarity bands and which seeds or terms bring in which items, deciding whether to reword terms, and saving the candidate list. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Stage 4 of 6: Generate and inspect the candidates

Goal: a candidate list the user has looked at and trusts. This is the list the gold set is drawn from and the classifier runs on, so it is settled here, before anything is labelled.

## Entry check

- The search terms (or the whole corpus) are approved (stage 2) and the `taxonomy` cell is approved (stage 3).
- If any of this is missing, say which stage is unfinished (`goldlabel-taxonomy`), offer to run it, and continue only if the user tells you to skip it.

## Procedure

Write only goldlabel calls. Anything else needs the user's yes, shown to them first.

1. Run it. One filter per call, `seeds=` or `keywords=`. To work on part of the corpus only, put the filter on the corpus (`where=`, see `goldlabel-connect`), not on `get_candidates`.

```python
# seeds: semantic search (the corpus needs vectors; the embedder must be the model that made them)
candidates = gl.get_candidates(
    corpus, seeds=seeds, embedder="openai:text-embedding-3-small"
)
candidates  # count, similarity bands, and a WARNING if the backend capped the results

# keywords or regular expressions, ranked by distinct terms matched
candidates = gl.get_candidates(
    corpus, keywords=keywords, limit=2000, out="candidates.jsonl"
)

# the whole corpus, in the corpus's order
candidates = gl.get_candidates(corpus)
```

   A seed search embeds the seeds (a small live cost, one call per seed, cached; changing one seed re-embeds only that one) and writes `.goldlabel/candidates.jsonl`; keyword and whole-corpus lists are written only when `out=` is given. The embedding model needs its provider key in the environment: if it is missing, tell the user which variable to set and stop; never ask for the value.
2. Inspect it with the user.

```python
candidates.bands()  # seeds only: how many items fall in each similarity band
candidates.top_seeds(0.70)  # seeds only: which seeds bring in the items above 0.70
candidates.sample(20, seed=1).rows  # read twenty, not just the top
candidates.rows[:10]
```

3. Report in words: how many items, how they spread over the bands, which seeds or terms do the work and which bring in nothing, a WARNING if the backend capped the results (hits above the floor may be hidden), and what the top, middle and bottom items look like. Ask whether the top items are what they meant. Keyword and whole-corpus lists have no similarity, no bands and no `top_seeds`: read a sample instead.
4. Decide what to change, with the user:
   - Junk at the top: the seed or term is wrong. Reword or drop it, then run again. That is a reason to change the search, not the classifier.
   - Missing things the user knows exist: add a seed or term worded the way those items are worded.
   - Far too many or too few: a seed that is too general or too narrow; for keywords, `limit=` caps the list and the ranking decides what is kept.
5. Do not choose the similarity cutoff here. It is the user's decision, made later on a band sample in `goldlabel-run`. `candidates.above(0.70)` shows what a cutoff would keep.

## Exit check

- `candidates` is the list the user chose to go forward with, after reading a sample.
- They know it is final for now: **do not change the candidate list once gold rows are drawn from it**, unless the user decides to and you have told them the gold rows drawn from the old list may not represent the new one.

If this stage is repeated (the list changed), re-run `goldlabel-tune` from drawing the gold rows and `goldlabel-run`; rows already labelled stay valid but may not appear in the new list.

## Next

**Next: `goldlabel-tune`.** Tell the user: the candidate list is settled (give the count), what they approved, and that the next stage builds the classifier, has people label a gold set, and tunes the prompt against it. Offer to start it.
