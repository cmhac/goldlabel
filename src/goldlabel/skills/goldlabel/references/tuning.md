# Tuning the prompt

Tune against the **dev** sample. The gold rule applies throughout: you may read the gold labels to understand a disagreement, but you never write or change one, and a label that looks wrong is a question for the user (who may relabel it in the labelling page), not something to fix.

## The loop

1. Evaluate and read the disagreements:

```python
ev = clf.evaluate(dev, target=0.80)
df = ev.disagreements_to_polars()  # id, text, gold, predicted, reasoning
df.filter(df["predicted"].is_not_null()).head(10)
ev.metrics.per_label  # which label is weak: precision or recall?
```

`ev.disagreements` is the same data as a list of dicts. Group them: is the model missing a label (low recall), over-using one (low precision), confusing two near labels, or defeated by a kind of text? The `reasoning` column says why the model chose what it chose.

2. Change **one** thing, with the user's agreement: a sentence in the prompt, a label description (which changes the taxonomy), or a new example in the prompt. Resist rewriting everything; you will not know what helped.

```python
clf_v2 = clf.with_prompt(prompt_v2)  # prompt_v2 is the edited prompt string
ev2 = clf_v2.evaluate(dev, target=0.80)
```

   An unchanged prompt costs nothing to re-evaluate (cached). A changed prompt makes one live call per dev item, so say that before you run it on a large dev split.

3. Compare `ev.score()` with `ev2.score()` and look at which rows flipped. A change that fixes three rows and breaks four is not progress.

4. Every evaluation so far is in `.goldlabel/evals.jsonl`, with the prompt it used; each sample's summary says how often it was evaluated:

```python
dev  # '... evaluated 3 times (2 prompts)'
pl.read_ndjson(
    ".goldlabel/evals.jsonl"
)  # time, samples, n, score, digest, model, prompt
```

## When to stop

Stop when the score reaches the target the user set, or when the remaining disagreements look like label noise or genuinely ambiguous items (say so; show a few), or when changes stop moving the score. Do not keep tuning to squeeze out a point. If the dev split is small, one row is a large swing; suggest more labelled rows (the user labels them) before more prompt changes.

## Never tune on the test sample

The test sample exists to report an honest number once. Do not evaluate it to decide what to change, do not read its disagreements to write the prompt, and do not draw more rows into it. Evaluate it when the user says the prompt is final:

```python
test = gold.draw_sample("test")  # pending; people label them
gl.label(test, taxonomy)
final = clf.evaluate(test)
```

If the result is disappointing, report it as it is and ask the user what they want. The test rows are now spent: changing the prompt after seeing the score makes them a second dev set. If the user wants to keep tuning, there is one honest way, and it needs their **explicit yes** after you have said what it does: add the spent test sample to the tuning set (`tuning = dev + test`, which writes nothing and changes no label), draw a fresh, separately named test sample (`test_2 = gold.draw_sample("test-2")`), have people label it, tune on `tuning`, and evaluate `test_2` once. Never combine without that yes. The `goldlabel-tune` skill has the steps.

## Gold looks wrong or incomplete

- A label no longer in the taxonomy: `gold.orphaned(taxonomy)` lists those rows. Tell the user; do not relabel them yourself.
- Too few rows for a label: suggest more seeds that find it, or drawing more rows. The user labels them.
- Disagreements that are all the same item type: usually a prompt or description problem; propose the edit.
