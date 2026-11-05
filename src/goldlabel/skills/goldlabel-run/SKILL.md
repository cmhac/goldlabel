---
name: goldlabel-run
description: "Use when the goldlabel prompt is final and it is time to classify everything: choosing the similarity cutoff from a band sample, estimating calls, cost and time, getting the user's yes before spending money, running the full classification with a spending limit and resuming it, saving the classifier, and reusing it in a pipeline. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Stage 6 of 6: Estimate, run and save

Goal: the classified output, run only after the user has seen the estimate and said yes.

## Entry check

- A classifier with a final prompt (stage 5) and one test evaluation, `final`, reported to the user.
- If any of this is missing, say which stage is unfinished (`goldlabel-tune`), offer to run it, and continue only if the user tells you to skip it.

## Procedure

Write only goldlabel calls. Anything else needs the user's yes, shown to them first.

1. (optional, seed searches only) Choose the cutoff with the user. The band sample is a classification run: it makes live calls and costs money, so it needs the same yes as the full run. It is not an evaluation (not logged, uses no gold). Show the table and ask where to cut. Keyword and whole-corpus lists have no bands: `selected = candidates`.

```python
report = clf.band_sample(candidates, per_band=30)
report  # per band: n, off_topic, rate; and the cost
selected = candidates.above(0.70)  # the user's number
```

2. Estimate first, always. Say it in words: how many items, how many calls are live, the cost, and the time. `est.dollars` is `None` when the price is unknown; that shows as `?` with a warning and is never zero. In that case say so, classify a small slice first to get a priced sample (`clf.classify(selected.sample(20, seed=1))`), estimate again and ask again.

```python
est = clf.estimate(selected)
est  # n, cached, live, dollars (or "cost ?" when the price is unknown), seconds
```

3. **Do not start the full run until the user says yes.** Then run with `max_cost=` about 1.5 times the estimate, and tell the user the number. It raises `CostLimit` before starting if the estimate is over, stops (resumable) if the spend crosses it, and refuses when the price is unknown.

```python
results = clf.classify(selected, out="results.jsonl", max_cost=1.5 * est.dollars)
results  # rows with labels, reasoning, run; cost; errors
results.errors  # items that failed; returned, never raised
```

   - `out=` makes the run resumable: run the same call again and only missing ids are classified.
   - A 401 or 403 from the provider, or several API errors in a row, stop the run; finished rows are already in `out`. Fix the cause (a missing key, a rate limit) and run the same call again. A missing key: tell the user which variable to set; never ask for the value.
   - `gl.cost()` shows the running total.
4. Report: where the output is, how many items, what it cost, how many errors, and the one test score with its split, `n`, who labelled the gold rows (`final.sources`) and how often the held-out sample was evaluated (its summary, `test`).
5. (optional, only if the user wants to reuse the classifier) Save a bundle. Ask where it should live and tell the user to commit the folder. `references/reuse.md` has the rest: loading it in a pipeline, and what to do if a digest warning appears.

```python
clf.save("classifiers/my-topic/", evaluation=final)  # final is the one test evaluation
```

6. (optional) Before running the classifier on a different corpus, check it there: give that corpus its own named gold dataset with a held-out test sample, have people label it and evaluate it once (`goldlabel-tune` step 10). Report that score with the other one; never fold that corpus's rows into the first dataset.

```python
gold_b = gl.Gold(
    candidates_b, name="corpus-b"
)  # its own file: .goldlabel/gold-corpus-b.jsonl
test_b = gold_b.draw_sample("test", n=30)  # pending; people label them
gl.label(test_b, taxonomy)
final_b = clf.evaluate(test_b)  # once, as for any held-out sample
```

More detail is in `references/running.md` and `references/reuse.md` of the `goldlabel` skill.

## Ask, do not decide

The similarity cutoff, whether to spend money, and the `max_cost` are the user's.

## Exit check

- The user saw the estimate and said yes before the full run; `results` exists and its errors were reported.
- You gave the report in step 4.

If this stage is repeated (a different prompt, cutoff or candidate list), the old output is out of date: say so, and re-run from the stage that changed.

## Next

**Sequence complete.** Tell the user: all six stages are done, where the output is, what it cost, and the one test score. Name what is optional and still open: saving and reusing the classifier (`references/reuse.md`), and anything they want to do with the classified output, which is their call; do not start charts, deduplication, aggregates, exports or write-ups unless they ask.
