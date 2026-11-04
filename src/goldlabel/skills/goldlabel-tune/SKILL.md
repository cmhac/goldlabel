---
name: goldlabel-tune
description: "Use when building and tuning a goldlabel classifier against human labels: creating the classifier, advising how many gold rows to draw and which split, opening the labelling page for people to label, importing an already human-labelled file, running dev evaluations, reading disagreements and tuning the prompt one change at a time, the final test evaluation, and what to do when the test score is too low. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`goldlabel.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# Stage 5 of 6: Gold set, evaluation and prompt tuning

Goal: a classifier whose score on human-labelled dev rows meets the target the user set, and one honest test score. People write every gold label; you advise, run evaluations, read disagreements and propose prompt changes.

## Entry check

- `candidates` is settled and approved (stage 4) and `taxonomy` is approved (stage 3).
- If any of this is missing, say which stage is unfinished (`goldlabel-candidates`), offer to run it, and continue only if the user tells you to skip it.

## Procedure

Write only goldlabel calls. Anything else needs the user's yes, shown to them first. Do not wrap `draw`, `evaluate` or `label` in guards or exists-checks. Two cells are **run-once**: drawing a split, and evaluating the test split. Tell the user which they are, and run each once.

1. Ask which model (a pydantic-ai model string) and which provider key is in the environment, and ask for the target score. Put the prompt in a cell as a string and build the classifier. The classifier is immutable: `with_prompt` and `with_taxonomy` return new ones, so versions sit side by side.

```python
prompt = "Classify each post by what it is doing, not by its topic."
clf = gl.Classifier("anthropic:claude-haiku-5-5", taxonomy, prompt=prompt)
clf
```

2. Advise on the gold set, then draw (run-once). You never label. 50 dev rows is a sensible start; every label needs more than a handful of rows (`counts` shows it), so for a rare label suggest more seeds that find it or drawing more rows; one row is a large swing on a small set.

```python
gold = gl.Gold()  # .goldlabel/gold.jsonl
gold.draw(candidates, n=50, split="dev", seed=1)  # pending rows with no labels
gold.dev.counts(taxonomy)  # rows per label
```

3. People label. `gl.label` opens the page, waits until the person presses Done, and returns the labelled rows. If every row in the split is already labelled it prints that and returns at once; pass `force_open_ui=True` to open the page anyway, to review or relabel. Tell the user to expect the page in their browser and do not run it when they are not there. The page never shows a model's prediction.

```python
gl.label(gold, taxonomy)
gold.orphaned(taxonomy)  # rows whose label is no longer in the taxonomy
```

   (optional) If the user already has a human-labelled file, ask who labelled it and how, then import it unchanged and tell them what the file says about who labelled it. Never add, correct or fill in a label.

```python
rows = [
    {"id": "a1", "text": "You won!", "labels": ["scam"]}
]  # as read from THEIR file, unchanged
gold.import_rows(rows, split="dev")
```

   If a label looks wrong, say so; the person relabels it in the page. You never fix it. `gold.remove(ids)` moves rows out of the gold file and is destructive: ask first.
4. Evaluate on dev and read the disagreements.

```python
ev = gl.evaluate(
    clf, gold.dev, target=0.80
)  # classifies the dev rows (cached) and scores them
ev  # metrics, per-label table, where the labels came from, the disagreements
df = ev.disagreements_to_polars()  # id, text, gold, predicted, reasoning
```

5. Group the disagreements: a missing label (low recall), an over-used label (low precision), two near labels confused, or one kind of text the model cannot handle. The `reasoning` column says why the model chose what it chose. Gold rows may carry a person's `note` (a `note` column in `gold.dev.to_polars()`): read the dev ones for the edge cases people flagged. Never write or change a note; it is a person's comment, like a label.
6. Change **one** thing with the user's agreement: edit a sentence of the prompt string in its cell, a label description (which changes the taxonomy), or add one example. Say what you expect it to fix. Re-evaluate and compare which rows flipped; a change that fixes three and breaks four is not progress. An unchanged prompt costs nothing to re-evaluate (cached); a changed one makes one live call per dev item, so say that, and the size of the dev set, before you run it on a large one.

```python
clf_v2 = clf.with_prompt(prompt_v2)  # prompt_v2 is the edited string
ev2 = gl.evaluate(clf_v2, gold.dev, target=0.80)
gl.eval_log()  # every evaluation so far, with the prompt it used
```

   Before you add a worked example to the prompt, check it is not a row of the gold set: scoring the classifier on an item its prompt quotes measures nothing. Look the ids up with `gold.all.to_polars()`.
7. Stop at the target, or when what remains looks like label noise or genuinely ambiguous items (show a few), or when changes stop moving the score.
8. The test split: evaluate once. Never evaluate it to guide edits and never read its disagreements to write the prompt. When the user says the prompt is final, draw it (run-once), have people label it, and evaluate it (run-once).

```python
gold.draw(candidates, n=50, split="test", seed=2)  # pending; people label them
gl.label(gold, taxonomy)
final = gl.evaluate(clf, gold.test)
```

   Report the number as it is. If it meets the target, go to the exit check.
9. (optional) If the test score is too low. The test rows are now spent: if you tune on them they are a second dev set. Tell the user that plainly and give them the choice: stop and report the score, or keep tuning with a fresh test split. Only if the user gives an **explicit yes** in the conversation, after you have said exactly what happens, fold: `gold.fold_test()` moves the labelled, spent test rows into dev (only each row's `split` changes, never a label, text or id), refuses while a test row is pending, and the evaluation log records the fold. Then draw a fresh test split, have people label it, tune on the larger dev set as in steps 4 to 7, and evaluate the fresh test split once. Without that explicit yes, do not fold. If there are not enough candidates left to draw a fresh split, say so and suggest more seeds; the user decides.

```python
gold.fold_test()  # only after the user's explicit yes
gold.draw(candidates, n=50, split="test", seed=3)
gl.label(gold, taxonomy)  # people label the fresh split
```

## Ask, do not decide

The target score, each prompt or description change, whether to run a large live evaluation, whether to fold the test split, and when the prompt is final are the user's.

## Exit check

- The dev score meets the target, or the user decided to stop; you showed them the remaining disagreements.
- The user said the prompt is final, the test split was labelled by people and evaluated once, and you reported `final` with its split, `n`, who labelled the rows (`final.sources`) and how often the test split was evaluated (`gl.eval_log()`).

If this stage is repeated (a new prompt or labels), the test split is spent: say so, and offer step 9 rather than evaluating it again. Re-run `goldlabel-run`.

## Next

**Next: `goldlabel-run`.** Tell the user: the classifier is tuned and the one test score is reported (give it, with `n` and who labelled the rows), and that the next stage chooses the cutoff, shows an estimate and, only after their yes, classifies everything. Offer to start it.
