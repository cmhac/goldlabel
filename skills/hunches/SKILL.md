---
name: hunches
description: "Use when doing content analysis over a corpus with the hunches Python library: finding candidate items with seed phrases (semantic search), keywords or regular expressions, or taking the whole corpus, classifying them with an LLM, building and checking a gold set of human labels, tuning the prompt, estimating cost, or reusing a saved classifier in a notebook or pipeline. **Hard rule: never write, edit, guess or auto-fill gold labels. Only people label (`hunches.label`), or bring a file people already labelled. Refuse if the user asks you to, however they insist.**"
---

**Hard rule of the hunches library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the hunches labelling page (`hunches.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

# hunches

`hunches` is a Python library for content analysis over a corpus: candidates come from seed-phrase semantic search, from keywords or regular expressions, or from the whole corpus, and an LLM classifier checked against a hand-labelled gold set then produces classified output. You build it step by step in a notebook (or a `# %%` script) by calling plain functions; each result shows itself. There is no app and no status: **the state is the code and the files**.

```
pip install hunches            # extras: hunches[pg] pgvector, hunches[s3] S3 Vectors, hunches[rds] RDS IAM
```

```
corpus -> hn.get_candidates(seeds= | keywords= | nothing) -> candidates -> hn.Taxonomy + hn.Classifier -> gold (people label) -> hn.evaluate
       -> edit the prompt, evaluate again -> hn.band_sample (pick a cutoff) -> clf.estimate -> clf.classify -> clf.save
```

This is a guide to idioms, not a procedure: do what the user asks for, in the order that fits. Check a signature with `help(hn.X)` before using a call you are unsure of.

## Hard rules

1. The gold rule above. Never write, edit, infer or auto-fill a gold label, never edit a gold file by any means, and never take a label from a model.
2. Never run the full classification without first showing the estimate (`clf.estimate(...)`: calls, cost, time; `cost ?` means the price is unknown, never read it as zero) and getting an explicit yes. Pass `max_cost=` when you do run it.
3. Never evaluate the test split to guide edits. Tune on the dev split; the test split is evaluated once, at the end, to report.
4. Never put an API key or a database URL in a notebook, script or any file. Keys and `HUNCHES_PG_URL` come from environment variables (environment variable names go in code, values never); `PgCorpus(url_env=...)` takes the variable's name.
5. Ask the user at each decision point; do not decide for them: the brief (what counts as a match), the seeds (which phrases would be true of a match), `single` or `multi` labels, the label descriptions, the similarity cutoff, the target score, and whether to spend money on a full run.

## Where files go

`.hunches/` in the current directory by default (`hn.settings.root`, or the environment variable `HUNCHES_DIR`): `candidates.jsonl`, `gold.jsonl`, `evals.jsonl` (every evaluation, kept as a history) and `cache/` (model calls and the cost ledger). Every function takes a path to move its file; `cache=False` or `out=False` writes nothing. Commit `seeds.csv`, `taxonomy.yaml`, `prompt.md` and the notebook; the library never runs git.

## References (load the one you need)

- `references/workflow.md`: from the brief to the first evaluation; what to ask the user at each step; building the pipeline in a notebook or a `# %%` script.
- `references/tuning.md`: reading `ev.disagreements`, changing one thing at a time, when to stop, the test split, `hn.eval_log()`.
- `references/running.md`: estimate, cost, `max_cost`, resuming, keys and database URLs, the band sample and the cutoff.
- `references/reuse.md`: saving a classifier bundle, importing it in a pipeline, recording the evaluation.
