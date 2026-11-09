# Tasks: `/goldlabel` as a complete entry point

**Input**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/skill-text.md](contracts/skill-text.md), [quickstart.md](quickstart.md).

**Commits**: one commit per task, named `016/TNN: ...`, on `claude/tender-heisenberg-vfoip3`. No PR unless asked.

**Tests**: red/green (constitution Principle IV). Each task that changes skill or instruction text first adds its failing assertions to `tests/test_skill_stages.py` (or the file named), runs them, sees them fail for the right reason, then writes the text and sees them pass. Expected strings are written by hand in the test, never read back from the skills. Nothing calls a model, service or browser.

**Green at every commit**: `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest` (pre-commit enforces it). The gold rule paragraph (`src/goldlabel/gold_rule.md`) is never edited or reworded; `tests/test_gold_rule.py`, `tests/test_skills.py` and `tests/test_docs.py` would fail and print the text to paste. Never edit a gold file by any means.

**Ponytail**: `/ponytail-review` of spec, plan and tasks runs before T001 (not waived); `/ponytail-review` and `/ponytail-debt` on the diff in T013. Added skill text is lean: plain sentences, no repetition of the stage skills' detail, overview at most 150 lines.

**All of T003, T005, T007 edit `src/goldlabel/skills/goldlabel/SKILL.md`: they run in order, never in parallel.**

## Phase 1: Setup

- [ ] T001 Baseline: on the branch, run `scripts/dev-setup.sh`, then `uv run ruff check`, `uv run ruff format --check`, `uv run ty check` and `uv run pytest`, and record the pass counts in a one-line note at the end of this file. Read `src/goldlabel/skills/goldlabel/SKILL.md`, `src/goldlabel/skills/goldlabel-tune/SKILL.md` steps 3 to 6, `tests/test_skill_stages.py` and the `POINTERS` text in `src/goldlabel/cli.py`. Any red test at baseline is reported to the user and not fixed here.

## Phase 2: Foundational

No shared prerequisite: every story edits existing files and its own tests. (Nothing to build first.)

## Phase 3: User Story 1 - Resume at the next unfinished stage (P1) 🎯 MVP

**Goal**: `/goldlabel` checks what the user already has and offers the next stage instead of stage 1.
**Independent test**: the new tests pass; the quickstart read-through gives the right resume stage for the three fixtures.

- [ ] T002 [US1] Red: in `tests/test_skill_stages.py` add `test_the_overview_checks_progress_before_the_procedure`, asserting on `OVERVIEW.read_text()` (hand-written strings): the heading `## Check progress first` exists and comes before `## The procedure`; it names each stage's evidence: `gl.Table`, `gl.PgCorpus`, `gl.S3Corpus`, `seeds`, `keywords`, `gl.Taxonomy`, `gl.get_candidates`, `candidates.jsonl`, `gl.Classifier`, `gl.Gold`, `clf.evaluate`, `evals.jsonl`, `clf.estimate`, `clf.classify`, and `gold*.json`; it contains the phrases `unsure`, `the user's yes` and `Sequence complete`; it says it reads and changes nothing (`changes and runs nothing`); it forbids bulk reading (`never print gold text or labels`) and keys (`never read a key, a database URL or a .env`); it says to start at `goldlabel-connect` only when nothing is done. Run it, see it fail (the heading is missing).
- [ ] T003 [US1] Green: in `src/goldlabel/skills/goldlabel/SKILL.md` add `## Check progress first` before `## The procedure`, and change "Start at the first" in the procedure to "Start at the stage the progress check names (the first, when nothing is done)". Content per [contracts/skill-text.md](contracts/skill-text.md) and [research.md](research.md) R2 to R4: (1) say `/goldlabel` is where to start whenever the user does not know which skill to call; (2) read the user's notebook or script and the file names, dates and aggregate fields (sample name, row counts, evaluation count) in the storage folder; (3) the evidence table, one row per stage, exactly as in R2, with the note that stage 2 may leave no call when the user chose the whole corpus, so ask; (4) report per stage as done (name the evidence), unsure (say why) or not started, plus one proposed resume stage; (5) evidence is not consent: skip only on the user's yes, and the stage's own entry check still applies; "start over" or a named stage is followed; (6) changes and runs nothing, never print gold text or labels in bulk, never read a key, a database URL or a `.env`; (7) stage 6 evidence means say **Sequence complete** and offer what is optional (reuse, a second corpus, review in the page); (8) several `gold-<name>.json` files: ask which dataset; a notebook with something other than goldlabel calls: report it and offer to clean it up, never delete unasked. Use `gold.json`, not `gold.jsonl`. Run the new test green, then the whole suite.

## Phase 4: User Story 2 - The overview alone guides every stage (P1)

**Goal**: an agent with only the overview can lead the user through the six stages in plain words.
**Independent test**: the new tests pass; the six-row reviewer checklist (SC-001) is complete.

- [ ] T004 [US2] Red: in `tests/test_skill_stages.py` add `test_the_overview_guides_each_stage_in_plain_words`: a `## The stages in plain words` section exists; for each of the six stage names in order it contains a block with the labels `Purpose:`, `Ask:`, `Show:` and `Approval:` (parse by splitting the section on the stage names, in the order of `STAGES`); a `## How to talk the user through a step` section exists with the words `what the step is for`, `show`, `decision`, `wait` and `what comes next`; and `len(OVERVIEW.read_text().splitlines()) <= 150`. See it fail.
- [ ] T005 [US2] Green: in `src/goldlabel/skills/goldlabel/SKILL.md` add the two sections after `## The procedure`. Each stage block is four short lines, from the stage skills' own entry questions and exit checks (read each `SKILL.md` for the true wording; do not invent decisions): `Purpose:` one plain sentence, `Ask:` the user's decisions, `Show:` what to put in front of them, `Approval:` what they must say before moving on. Talk-through rules: say what the step is for; show the result; ask the decision that is theirs; wait; say what comes next; plain words, one stage at a time, no jargon left unexplained. Keep the existing hard rules, code rule and references untouched. Count lines; trim wording if over 150. Green, then the whole suite.

## Phase 5: User Story 3 - The agent teaches the labelling page and sends every revision through it (P1)

**Goal**: the overview names what the page does, how to start it, and that it is the only route for revisions.
**Independent test**: the new tests pass; the refusal trial (human check) points to the page.

- [ ] T006 [US3] Red: in `tests/test_skill_stages.py` add (a) `test_the_overview_teaches_the_labelling_page`: a `## The labelling and review page` section names `goldlabel label`, `gl.label`, `force_open_ui=True`, `STALE`, `jump to a row by id`, `label the pending rows`, `revise a label or a note`, `disagreements`, `never shows a model's prediction`, `joins`, and the sentence `every revision of a gold label or note goes through the page`; (b) `test_no_guidance_offers_a_gold_edit`: for every file in `[OVERVIEW, *stage SKILL.md, *REFS.glob("*.md"), docs/agent-instructions.md, .kiro/steering/goldlabel.md]`, remove the gold rule paragraph (read `src/goldlabel/gold_rule.md` and drop that text) and assert none of these hand-written phrases remains: `edit gold.json`, `edit the gold file`, `open gold.json`, `change the gold file`, `update the gold file`, `gold.jsonl` (comment: `# shortcut: a phrase list misses a new wording; extend it when a trial shows one`). Run; (a) fails, (b) should already pass; if (b) fails on existing text, report the line to the user and fix that wording only if it offers an edit.
- [ ] T007 [US3] Green: in `src/goldlabel/skills/goldlabel/SKILL.md` add `## The labelling and review page` after the stage guide. Content, from feature 015 as shipped (check `goldlabel label --help` and `src/goldlabel/_label.py` routes before writing; do not describe anything the page lacks): the page's jobs (datasets, samples and rows; jump to a row by id; label the pending rows; revise a label or a note; each evaluation's disagreements; the STALE flag for an evaluation made before a revision); start it with `goldlabel label [NAME]` in a terminal (the user runs it; say so if you cannot open a browser, never claim you did) or `gl.label(sample, taxonomy)` in the notebook (`force_open_ui=True` walks every row of a sample for a review), which joins a page that is already running; the page never shows a model's prediction while a person labels; **every revision of a gold label or note goes through the page**; after a revision, evaluations made earlier are STALE, so evaluate again (a new line in `evals.jsonl`; the old one is never rewritten); the user insisting on "just fix them" gets the gold rule's refusal, the page, and other help. Add one Python block only if it is goldlabel calls (`gl.label(dev, taxonomy)`), which the code-rule test checks. Green, then the whole suite and the 150-line check.

## Phase 6: User Story 4 - `goldlabel-tune` reads disagreements from the page (P2)

**Goal**: the tuning loop offers the page's evaluation view and handles STALE evaluations.
**Independent test**: the new tests pass; every existing tune test still passes.

- [ ] T008 [US4] Red: in `tests/test_skill_stages.py` add `test_tune_offers_the_page_when_reading_disagreements`: take `section(body("goldlabel-tune"), "## Procedure")`, find the step that starts `4. Evaluate on dev and read the disagreements` through step 6, and assert it names `goldlabel label`, `STALE` and `evaluate again`; assert it still names `ev.disagreements_to_polars()`; assert the held-out step still says (hand-written) `never read its disagreements to write the prompt`. See it fail on the first assertion.
- [ ] T009 [US4] Green: in `src/goldlabel/skills/goldlabel-tune/SKILL.md` (steps 4 to 6 only) offer the page's evaluation view beside `ev.disagreements_to_polars()`: the user can open `goldlabel label` and read the evaluation's disagreements with each row's labels and note, and the person who labelled the rows decides whether a label or the prompt is wrong; if they revise a row, say the earlier evaluation is STALE and evaluate the dev sample again, comparing which rows flipped as the step already does; keep step 8 (held-out test sample) as it is. If `references/tuning.md` describes reading disagreements without the page, add the same one-line pointer there. Do not change the stage's four parts, order, entry check or Next line. Green, then the whole suite.

## Phase 7: User Story 5 - The three instruction copies agree (P2)

**Goal**: agents that never load skills get the same start-here and revise-in-the-page text.
**Independent test**: the new test passes; `tests/test_cli.py` still ties the Kiro file to `steering_text()`.

- [ ] T010 [US5] Red: in `tests/test_skill_stages.py` replace the last test's scope by adding `test_the_start_here_bullet_is_the_same_in_every_copy`: a hand-written constant `START_BULLET` (the new bullet, written out in the test: "- Start with `goldlabel`: it checks the user's notebook and `.goldlabel/` folder for the stages already done and offers the next one, so call it first whenever you do not know which skill comes next; never skip a stage on that evidence alone, only on the user's yes.") must appear in `docs/agent-instructions.md`, in `.kiro/steering/goldlabel.md` and in `goldlabel.cli.POINTERS`. Also assert the existing bullet `To review or revise gold labels` is present in all three. See it fail.
- [ ] T011 [US5] Green: add `START_BULLET` as the first bullet of the list in `POINTERS` (`src/goldlabel/cli.py`), `.kiro/steering/goldlabel.md` and `docs/agent-instructions.md`, with identical wording, directly after the "When working with the `goldlabel` library" line (before "Use the goldlabel agent skills"). Run `tests/test_cli.py` (steering == `steering_text()`), `tests/test_docs.py` and `tests/test_skills.py`, then the whole suite.

## Phase 8: Polish and cross-cutting

- [ ] T012 [P] Update `AGENTS.md` (and keep `CLAUDE.md` a symlink): add a "**016 is implemented**" paragraph to "Current state" (closes issue #27; the overview checks progress first, guides each stage, teaches the labelling page; `goldlabel-tune` offers the page's evaluation view; the instruction text has a start-here bullet; text and tests only), and add to "What a human still has to do": the agent trial (a notebook done through stage 3, call `/goldlabel`, expect `goldlabel-tune`; Claude Code and one other agent), the gold-rule refusal trial with the updated skills (three phrasings), and comparing the agent's description of the page with the real page. Do not reword the gold rule. `tests/test_docs.py` stays green.
- [ ] T013 Quickstart read-through and review: write the three fixtures from [quickstart.md](quickstart.md) in the scratchpad (not the repo) and follow the overview's progress check on each by hand, recording the resume stage (expect `goldlabel-connect`, `goldlabel-tune`, sequence complete) in a note at the end of this file; run `uv build` and check the wheel holds `goldlabel/skills/*` and `goldlabel/gold_rule.md`; run `/ponytail-review` on the diff and `/ponytail-debt`, fix what they find (skill text only), and list the shortcuts (the phrase list in T006). Final run of the four checks. Report to the user what was not verified: the agent trial and the refusal trial.

## Dependencies and order

- T001 first; then US1 (T002, T003) → US2 (T004, T005) → US3 (T006, T007), all in the overview file, in order.
- US4 (T008, T009) edits `goldlabel-tune` and may run in parallel with US1 to US3 after T001, but its tests live in the same test file, so keep commits in task order to avoid conflicts.
- US5 (T010, T011) is independent of the others; T011 before T012.
- T012 and T013 last. MVP: T001 to T003 (the progress check alone fixes the tester's failure).

## Parallel example

After T001: one worker on T008 to T009 (`goldlabel-tune`), one on T010 to T011 (instruction copies), while the overview tasks T002 to T007 run in order.
