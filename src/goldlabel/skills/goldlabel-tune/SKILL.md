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

2. Advise on the gold set, then draw. You never label. 50 dev rows is a sensible start; every label needs more than a handful of rows (`counts` shows it), so for a rare label suggest more seeds that find it or drawing more rows; one row is a large swing on a small set.

```python
gold = gl.Gold(candidates)  # .goldlabel/gold.json; 50 rows per sample by default
dev = gold.draw_sample("dev")  # pending rows with no labels; safe to rerun
dev.counts(taxonomy)  # rows per label
```

3. People label. `gl.label(dev, taxonomy)` opens the page on the rows of that sample that are still pending (only those: the page never shows another sample), waits until the person presses Done, and returns the sample. If every row in it is already labelled it prints that and returns at once; pass `force_open_ui=True` to open the page on every row of the sample anyway, to review or relabel. Tell the user to expect the page in their browser and do not run it when they are not there. While people label, the page never shows a model's prediction. To fix a label later, tell the user to run `goldlabel label`: it lists every dataset and sample, opens any row by id, and lists each evaluation with its disagreements and a STALE flag when a row was revised after it ran. Evaluating stays in code.

```python
gl.label(dev, taxonomy)
gold.orphaned(taxonomy)  # rows whose label is no longer in the taxonomy
```

   (optional) If the user already has a human-labelled file, ask who labelled it and how, then import it unchanged and tell them what the file says about who labelled it. Never add, correct or fill in a label.

```python
rows = [
    {"id": "a1", "text": "You won!", "labels": ["scam"]}
]  # as read from THEIR file, unchanged
gold.import_rows(rows, "dev")
```

   If a label looks wrong, say so; the person relabels it in the page. You never fix it. `gold.remove(ids)` moves rows out of the gold file and is destructive: ask first.
4. Evaluate on dev and read the disagreements.

```python
ev = clf.evaluate(dev, target=0.80)  # classifies the dev rows (cached) and scores them
ev  # metrics, per-label table, where the labels came from, the disagreements
df = ev.disagreements_to_polars()  # id, text, gold, predicted, reasoning
```

5. Group the disagreements: a missing label (low recall), an over-used label (low precision), two near labels confused, or one kind of text the model cannot handle. The `reasoning` column says why the model chose what it chose. Gold rows may carry a person's `note` (a `note` column in `dev.to_polars()`): read the dev ones for the edge cases people flagged. Never write or change a note; it is a person's comment, like a label. The user can also read the disagreements in the page: `goldlabel label` opens the evaluation with each row's labels and note, and the person who labelled the rows decides whether a label or the prompt is wrong. If they revise a row there, the earlier evaluation is STALE: evaluate again before you compare anything.
6. Change **one** thing with the user's agreement: edit a sentence of the prompt string in its cell, a label description (which changes the taxonomy), or add one example. Say what you expect it to fix. Re-evaluate and compare which rows flipped; a change that fixes three and breaks four is not progress. An unchanged prompt costs nothing to re-evaluate (cached); a changed one makes one live call per dev item, so say that, and the size of the dev set, before you run it on a large one.

```python
clf_v2 = clf.with_prompt(prompt_v2)  # prompt_v2 is the edited string
ev2 = clf_v2.evaluate(dev, target=0.80)
dev  # its summary says how often it was evaluated, with how many prompts
```

   Before you add a worked example to the prompt, check it is not a row of the gold set: scoring the classifier on an item its prompt quotes measures nothing. Look the ids up with `gold.all.to_polars()`.
7. Stop at the target, or when what remains looks like label noise or genuinely ambiguous items (show a few), or when changes stop moving the score.
8. The test sample is held out: it is evaluated once, at the end, only when every row in it is labelled, and it never guides an edit. goldlabel does not stop a second evaluation, so this rule is yours to keep: never evaluate it to guide edits, never read its disagreements to write the prompt, and never evaluate it again under another prompt or model. Its summary (`test`) says how often it was evaluated; that number goes in the report. When the user says the prompt is final, draw it, have people label it, and evaluate it (run-once).

```python
test = gold.draw_sample("test")  # pending; people label them
gl.label(test, taxonomy)
final = clf.evaluate(test)
```

   Report the number as it is. If it meets the target, go to the exit check.
9. (optional) If the test score is too low. The test rows are now spent: if you tune on them they are a second dev set. Tell the user that plainly and give them the choice: stop and report the score, or keep tuning with a fresh test sample. Only if the user gives an **explicit yes** in the conversation, after you have said exactly what happens, combine: `tuning = dev + test` is the tuning set from now on (it writes nothing and changes no label, text or id). Then draw a fresh, separately named test sample, have people label it, tune on `tuning` as in steps 4 to 7, and evaluate the fresh test sample once. Without that explicit yes, do not combine. If there are not enough candidates left to draw a fresh sample, say so and suggest more seeds; the user decides.

```python
tuning = dev + test  # only after the user's explicit yes
test_2 = gold.draw_sample("test-2")
gl.label(test_2, taxonomy)  # people label the fresh sample
```

10. (optional) The user wants the tuned prompt on a different corpus too. Give that corpus its own gold dataset, by name, rather than drawing its rows into this one: a held-out test sample is usually enough there (no dev sample, no tuning), drawn from that corpus's candidates, labelled by people and evaluated once. The first dataset is not touched, and each dataset's evaluation counts are its own.

```python
gold_b = gl.Gold(
    candidates_b, name="corpus-b"
)  # its own file: .goldlabel/gold-corpus-b.json
test_b = gold_b.draw_sample("test", n=30)  # pending; people label them
gl.label(test_b, taxonomy)
final_b = clf.evaluate(test_b)  # once, as for any held-out sample
```

## Ask, do not decide

The target score, each prompt or description change, whether to run a large live evaluation, whether to combine a spent test sample into the tuning set, and when the prompt is final are the user's.

## Exit check

- The dev score meets the target, or the user decided to stop; you showed them the remaining disagreements.
- The user said the prompt is final, the test split was labelled by people and evaluated once, and you reported `final` with its split, `n`, who labelled the rows (`final.sources`) and how often the held-out sample was evaluated (its summary, `test`).

If this stage is repeated (a new prompt or labels), the test split is spent: say so, and offer step 9 rather than evaluating it again. Re-run `goldlabel-run`.

## Next

**Next: `goldlabel-run`.** Tell the user: the classifier is tuned and the one test score is reported (give it, with `n` and who labelled the rows), and that the next stage chooses the cutoff, shows an estimate and, only after their yes, classifies everything. Offer to start it.
