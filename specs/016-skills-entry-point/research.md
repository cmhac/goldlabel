# Research: `/goldlabel` as a complete entry point

## R1. Where does the progress check live?
**Decision**: Step 0 in the overview skill, as agent guidance; no library code.
**Rationale**: the agent already reads files with its own tools; a `goldlabel status` command or helper would be stored/derived state the constitution (Principle V) avoids and code nobody asked for (Ponytail). The overview is the one skill every user is told to call.
**Alternatives**: a `goldlabel status` CLI (rejected: new command, needs constitution change, parses notebooks); a seventh "resume" skill (rejected: breaks the six-stage test and adds a second entry point, which is the tester's confusion); a check inside each stage's entry check (kept as is: entry checks stay, they are the backstop).

## R2. What counts as evidence for a stage?
**Decision**: one line per stage, from goldlabel calls and the storage folder only:

| Stage | Evidence |
|---|---|
| 1 connect | a corpus object (`gl.Table`, `gl.PgCorpus`, `gl.S3Corpus`) |
| 2 search-terms | `seeds` and/or `keywords` variables (or a decision to take the whole corpus, stated by the user) |
| 3 taxonomy | a `gl.Taxonomy(...)` |
| 4 candidates | a `gl.get_candidates(...)` call, `candidates.jsonl` |
| 5 tune | `gl.Classifier`, `gl.Gold`, `draw_sample`, `gl.label`, `clf.evaluate`; `gold*.json`, `evals.jsonl`; a test sample evaluated |
| 6 run | `clf.estimate`, `clf.classify`, a saved classifier |

**Rationale**: matches the stage skills' own entry and exit checks and the code rule (a notebook holds goldlabel calls only), so evidence is checkable without running anything. Stage 2 can leave no call when the user chose the whole corpus; the check must ask rather than infer.
**Alternatives**: running the notebook to see what executes (rejected: side effects, cost, keys); reading outputs only (rejected: not present in a clean `.ipynb`; the notebook in the repo is saved without outputs).

## R3. Evidence is not consent
**Decision**: report, mark unsure, wait for the user's yes before skipping; the stage's own entry check still applies.
**Rationale**: the spec's story 1 and the existing rule "continue only if the user tells you to skip". A stale gold file from another corpus would otherwise skip tuning.

## R4. What the check may read (privacy and the gold rule)
**Decision**: the notebook or script, and the storage folder's file names, dates and the aggregate fields the skills already name (sample name, row counts, evaluation count). Never gold text or labels in bulk, never a key, URL or `.env`.
**Rationale**: gold rows can hold the user's data; the rule says agents do not write labels, and reading them in bulk adds nothing to knowing which stage is done.

## R5. How the page is taught
**Decision**: one section in the overview listing the page's jobs as shipped by 015 (datasets, samples, rows, jump to id, label pending, row editor, evaluations with disagreements, STALE), the two start forms, and the rule "every revision goes through the page". `goldlabel-tune` keeps its step 3 text and gets the evaluation view at step 5.
**Rationale**: the user asked for exactly this; 015's `goldlabel-tune` already has the revise pointer in step 3, so the change is to make it complete and reachable from the overview.
**Alternatives**: a new reference file `references/labelling.md` (rejected for now: the section is short; a reference is a later split if the overview passes about 140 lines).

## R6. Keeping the three instruction copies equal
**Decision**: add the one new bullet to `POINTERS`, the Kiro steering file and `docs/agent-instructions.md` in the same wording; `test_cli.py` already forces steering == `steering_text()`; add one assertion that the new bullet appears verbatim in `docs/agent-instructions.md` and in `POINTERS`.
**Rationale**: `docs/agent-instructions.md` is hand-copied and its first bullet already differs from `POINTERS` (it adds where to read the skills), so a whole-block equality test would fail for a reason that is not drift; a per-bullet check is the smallest test that catches the drift this feature cares about.

## R7. Naming the gold file
**Decision**: say `gold.json` / `gold-<name>.json`, as shipped; the issue's `gold.jsonl` is out of date (015).

## R8. Wording the gold rule
**Decision**: untouched. New text uses "revise in the page" and never the words "edit" or "fix" as an agent action; the test checks no skill or reference tells the agent to edit a gold file (the rule's own "Never edit a gold file by any means" line is the allowed exception and is matched exactly).

## Deliberately skipped
Same as the spec's list; additionally a `references/labelling.md` and a machine-readable progress report format.
