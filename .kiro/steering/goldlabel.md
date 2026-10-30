---
inclusion: always
---

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

When working with the `goldlabel` library (content analysis over a corpus: candidates from seed phrases, keywords or the whole corpus, an LLM classifier checked against human-labelled gold data):

- Read `src/goldlabel/skills/goldlabel/SKILL.md` first, then the reference you need: `src/goldlabel/skills/goldlabel/references/workflow.md` (brief, seeds, taxonomy, gold, first evaluation), `src/goldlabel/skills/goldlabel/references/tuning.md` (reading disagreements, tuning on dev, never on test), `src/goldlabel/skills/goldlabel/references/running.md` (estimate, cost, `max_cost`, resuming, keys), `src/goldlabel/skills/goldlabel/references/reuse.md` (saved classifiers). If the skill files are not in the project, read them at https://github.com/cmhac/goldlabel/tree/main/src/goldlabel/skills/goldlabel or print the rule with `import goldlabel; print(goldlabel.GOLD_RULE_FULL)`.
- Never run a full classification without showing `clf.estimate(...)` (calls, cost, time) and getting a yes from the user.
- Never put API keys or database URLs in a notebook, script or file; they come from environment variables.
