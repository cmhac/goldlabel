---
name: goldlabel-tune
description: "Use when building and tuning a goldlabel classifier against human labels: creating the classifier, advising how many gold rows to draw and which split, opening the labelling page for people to label, importing an already human-labelled file, running dev evaluations, reading disagreements and tuning the prompt one change at a time, the final test evaluation, and what to do when the test score is too low. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Gold set, evaluation and prompt tuning

Goal: a classifier whose score on human-labelled dev rows meets the target the user set, and one honest test score. People write every gold label; you advise, run evaluations, read disagreements and propose prompt changes. Before this: `goldlabel-candidates` and an approved taxonomy (`goldlabel-taxonomy`). After: `goldlabel-run`.

## The classifier

Ask which model (a pydantic-ai model string) and which provider key is in the environment. Keep the prompt in `prompt.md` once it is more than a line.

```python
import goldlabel as gl

taxonomy = gl.Taxonomy.read("taxonomy.yaml")
prompt = open("prompt.md").read()
clf = gl.Classifier("anthropic:claude-haiku-5-5", taxonomy, prompt=prompt)
```

The classifier is immutable: `clf.with_prompt(text)` and `clf.with_taxonomy(t)` return new ones, so versions sit side by side.

## Gold: advise, then people label

You never label. Advise on size and split, draw the rows, open the page, and wait:

```python
gold = gl.Gold()  # .goldlabel/gold.jsonl
gold.draw(candidates, n=50, split="dev", seed=1)  # pending rows with no labels
gl.label(
    gold, taxonomy
)  # opens the labelling page; returns when the person presses Done
gold.dev.counts(taxonomy)  # rows per label
gold.orphaned(taxonomy)  # rows whose label is no longer in the taxonomy
```

- Advice you can give: 50 dev rows is a sensible start; every label needs more than a handful of rows (`counts` shows it), so for a rare label suggest more seeds that find it or drawing more rows; one row is a large swing on a small set. Remind them the page never shows a model's prediction.
- `gl.label` blocks until the person is done. Tell the user to expect the page in their browser and do not run it when they are not there.
- If the user already has a human-labelled file, ask who labelled it and how, then import it unchanged (`gold.import_rows(rows, split="dev")`, rows exactly as read from their file) and tell them what the file says about who labelled it. Never add, correct or fill in a label.
- If a label looks wrong, say so; the person relabels it in the page. You never fix it.
- `gold.remove(ids)` moves rows out of the gold file and is destructive: ask first.

## The dev loop

```python
ev = gl.evaluate(
    clf, gold.dev, target=0.80
)  # classifies the dev rows (cached) and scores them
ev  # metrics, per-label table, where the labels came from, the disagreements
df = ev.disagreements_to_polars()  # id, text, gold, predicted, reasoning
```

Ask the user for the target score. Then:

1. Read the disagreements and group them: a missing label (low recall), an over-used label (low precision), two near labels confused, or one kind of text the model cannot handle. The `reasoning` column says why the model chose what it chose.
2. Change **one** thing with the user's agreement: a sentence in the prompt, a label description (which changes the taxonomy), or one example. Say what you expect it to fix.
3. Re-evaluate and compare which rows flipped; a change that fixes three and breaks four is not progress.

```python
clf_v2 = clf.with_prompt(open("prompt.md").read())  # after editing prompt.md
ev2 = gl.evaluate(clf_v2, gold.dev, target=0.80)
gl.eval_log()  # every evaluation so far, with the prompt it used
```

An unchanged prompt costs nothing to re-evaluate (cached); a changed one makes one live call per dev item, so say that, and the size of the dev set, before you run it on a large one. Stop at the target, or when what remains looks like label noise or genuinely ambiguous items (show a few), or when changes stop moving the score.

**Examples in the prompt.** Before you add a worked example to the prompt, check it is not a row of the gold set: scoring the classifier on an item its prompt quotes measures nothing.

```python
quoted = {"post-17", "post-42"}  # the ids of the items the prompt quotes
assert not quoted & {r.id for r in gold.all.rows}
```

## The test split: evaluate once

Never evaluate the test split to guide edits, and never read its disagreements to write the prompt. Draw it, have people label it, and evaluate it only when the user says the prompt is final:

```python
gold.draw(candidates, n=50, split="test", seed=2)  # pending; people label them
gl.label(gold, taxonomy)
final = gl.evaluate(clf, gold.test)
```

Report the number as it is. If it meets the target, go to `goldlabel-run`.

## If the test score is too low

The test rows have now been scored, so they are spent: if you tune on them they are a second dev set. Tell the user that plainly, and give them the choice: stop and report the score, or keep tuning with a fresh test split. Only if the user gives an **explicit yes** in the conversation, after you have said exactly what happens, do this:

1. `gold.fold_test()` moves the labelled, spent test rows into dev. Only each row's `split` changes (never a label, text or id), it refuses while a test row is pending, and the evaluation log records the fold (`gl.eval_log()` shows how many rows moved).
2. Draw a fresh test split and have people label it: `gold.draw(candidates, n=50, split="test", seed=3)`, then `gl.label(gold, taxonomy)`. Do not evaluate it until every row is labelled.
3. Tune on the larger dev set as above, then evaluate the fresh test split once.

```python
gold.fold_test()  # only after the user's explicit yes
gold.draw(candidates, n=50, split="test", seed=3)
gl.label(gold, taxonomy)  # people label the fresh split
```

Without that explicit yes, do not fold. If there are not enough candidates left to draw a fresh split, say so and suggest more seeds; the user decides.

## Ask, do not decide

The target score, each prompt or description change, whether to run a large live evaluation, whether to fold the test split, and when the prompt is final are the user's.
