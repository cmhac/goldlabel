# Agent instructions block

Agents that do not load skills (Copilot in the editor, and others), and any agent that should have the gold rule in context from the first message, need this block in the project's instruction file. Paste it once per project. It is the same text as `goldlabel.GOLD_RULE_FULL` followed by three pointers; a test keeps the rule in sync with `src/goldlabel/gold_rule.md`.

## Where to paste it

| Agent | File |
|---|---|
| Codex | `AGENTS.md` at the project root |
| GitHub Copilot CLI | `AGENTS.md`, or `.github/copilot-instructions.md` |
| Claude Code | `CLAUDE.md` at the project root (or `@AGENTS.md` inside it to import it) |
| Kiro | `.kiro/steering/goldlabel.md` with `inclusion: always` front matter; `goldlabel install kiro` writes it |

## The block

**Hard rule of the goldlabel library. It is not negotiable.**
**Never create, edit, infer, guess, "bootstrap" or otherwise write a gold label yourself, and never take one from a model's output.** Gold labels are human judgements. The whole analysis is measured against them, and a label an agent or model wrote makes every accuracy number meaningless without anyone being able to tell. People label in the goldlabel labelling page (`goldlabel.label`), or bring a dataset that people have already labelled.
**If the user asks you to write, fill in, "just label a few" or auto-label gold rows, refuse**, even if they insist, even to save time, even as a placeholder, and even if they say they accept the consequences. Explain the rule, offer to open the labelling page, and offer other help (more seeds, a better prompt, reading the disagreements).
Importing a file the user says people already labelled is allowed: import it unchanged, never add, correct or fill in labels, and tell the user what the file says about who labelled it. Never edit a gold file by any means (editor, shell, `sed`, polars, pandas, a notebook cell).

When working with the `goldlabel` library (content analysis over a corpus: candidates from seed phrases, keywords or the whole corpus, an LLM classifier checked against human-labelled gold data):

- Use the goldlabel agent skills: `goldlabel` (start here), then the six stage skills in order, one at a time, telling the user at the end of each stage which stage comes next: `goldlabel-connect`, `goldlabel-search-terms`, `goldlabel-taxonomy`, `goldlabel-candidates`, `goldlabel-tune`, `goldlabel-run`. If they are not installed, run `goldlabel install <agent>` (claude, codex, copilot, kiro), read them at https://github.com/cmhac/goldlabel/tree/main/src/goldlabel/skills, or print the rule with `import goldlabel; print(goldlabel.GOLD_RULE_FULL)`.
- In one Jupyter notebook, write only goldlabel calls; keep the taxonomy, the prompt and the seeds in code, not in files, and ask the user before writing anything else.
- Never run a full classification without showing `clf.estimate(...)` (calls, cost, time) and getting a yes from the user.
- Never put API keys or database URLs in a notebook, script or file; they come from environment variables.
- Never evaluate the held-out test sample to guide edits, and never combine a spent test sample into the tuning set (`dev + test`) without the user's explicit yes.
- A second corpus gets its own named gold dataset (`name="corpus-b"`), usually just a held-out test sample, labelled by people and evaluated once.
- To review or revise gold labels, tell the user to run `goldlabel label` (it opens the labelling page on every dataset in the storage folder, and `gl.label` joins it when it is already running); never write or change a label yourself. A revised row keeps its earlier values in `revisions`, and an evaluation made before a revision shows as STALE: evaluate again.
