# Contract: the text the tests hold

Anchors the new tests look for (spelled by hand in `tests/test_skill_stages.py`, not derived from the skills).

**Overview (`goldlabel/SKILL.md`)**
- Contains a progress-check heading ("Step 0", `## Check progress first`) that appears before the first mention of `goldlabel-connect` as a thing to start.
- Names evidence for each of: `gl.Table`/`gl.PgCorpus`/`gl.S3Corpus`, `seeds`/`keywords`, `gl.Taxonomy`, `gl.get_candidates`, `gl.Classifier`/`clf.evaluate`, `clf.classify`; and `gold*.json`, `evals.jsonl`.
- States that the user's confirmation decides a skip, and that the check changes and runs nothing.
- Names `goldlabel label`, `gl.label`, `force_open_ui=True`, `STALE`, and the sentence that every revision goes through the page.
- Has the stage guide for all six stages in order.

**`goldlabel-tune/SKILL.md`**: mentions the page's evaluation view and `STALE` between the evaluate step and the one-change step; still has Entry check, Procedure, Exit check, Next in order.

**Everywhere** (overview, six stages, references): no instruction to change a gold label other than through the page; the rule's own line "Never edit a gold file by any means" is the one allowed mention.

**Instruction copies**: one bullet beginning "Start with `goldlabel`" appears identically in `POINTERS`, `.kiro/steering/goldlabel.md` (via `steering_text()`) and `docs/agent-instructions.md`.
