# Tuning the prompt

Tune against the **dev** split. The gold rule applies throughout: you may read the gold labels to understand a disagreement, but you never write or change one, and a label that looks wrong is a question for the user (who may relabel it in the labelling page), not something to fix.

## The loop

1. Evaluate and read the disagreements:

```python
ev = gl.evaluate(clf, gold.dev, target=0.80)
df = ev.disagreements_to_polars()  # id, text, gold, predicted, reasoning
df.filter(df["predicted"].is_not_null()).head(10)
ev.metrics.per_label  # which label is weak: precision or recall?
```

`ev.disagreements` is the same data as a list of dicts. Group them: is the model missing a label (low recall), over-using one (low precision), confusing two near labels, or defeated by a kind of text? The `reasoning` column says why the model chose what it chose.

2. Change **one** thing, with the user's agreement: a sentence in the prompt, a label description (which changes the taxonomy), or a new example in the prompt. Resist rewriting everything; you will not know what helped.

```python
clf_v2 = clf.with_prompt(open("prompt.md").read())  # after editing prompt.md
ev2 = gl.evaluate(clf_v2, gold.dev, target=0.80)
```

   An unchanged prompt costs nothing to re-evaluate (cached). A changed prompt makes one live call per dev item, so say that before you run it on a large dev split.

3. Compare `ev.score()` with `ev2.score()` and look at which rows flipped. A change that fixes three rows and breaks four is not progress.

4. `gl.eval_log()` shows every evaluation so far, with the prompt it used:

```python
log = gl.eval_log()
log  # time, split, n, score, short digest, model; and how often the test split was used
log.to_polars()
```

## When to stop

Stop when the score reaches the target the user set, or when the remaining disagreements look like label noise or genuinely ambiguous items (say so; show a few), or when changes stop moving the score. Do not keep tuning to squeeze out a point. If the dev split is small, one row is a large swing; suggest more labelled rows (the user labels them) before more prompt changes.

## Never tune on the test split

The test split exists to report an honest number once. Do not evaluate it to decide what to change, do not read its disagreements to write the prompt, and do not draw more rows from it. Evaluate it when the user says the prompt is final:

```python
gold.draw(candidates, n=50, split="test")  # pending; people label them
gl.label(gold, taxonomy)
final = gl.evaluate(clf, gold.test)
```

If the result is disappointing, report it as it is and ask the user what they want; changing the prompt after seeing it makes the test split a second dev split, and `gl.eval_log()` will show that the test split was evaluated more than once. If the user insists on iterating, suggest a fresh test split drawn and labelled by people.

## Gold looks wrong or incomplete

- A label no longer in the taxonomy: `gold.orphaned(taxonomy)` lists those rows. Tell the user; do not relabel them yourself.
- Too few rows for a label: suggest more seeds that find it, or drawing more rows. The user labels them.
- Disagreements that are all the same item type: usually a prompt or description problem; propose the edit.
