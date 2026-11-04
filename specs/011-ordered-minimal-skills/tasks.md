# Tasks: Ordered stage skills and minimal agent code

**Input**: [spec.md](spec.md), [plan.md](plan.md). One commit per task: `011/TNN: ...`. Closes issue #16. Run after 012 is done.

## Phase 1: Tests first (User Story 3, P2, but written first)

- [ ] T001 [US3] Write `tests/test_skill_stages.py`, failing on today's skills: the six stage skills in the fixed order (names written by hand in the test); each has `Stage N of 6`, `## Entry check`, `## Procedure` with at least three numbered steps, `## Exit check`, `## Next` in that order; each `## Next` names the next skill in backticks and says "Tell the user"; the last says "Sequence complete"; stages 2-6 name the previous skill in their entry check; python blocks outside `# user-directed` blocks contain none of the deny-listed constructs (plan decision 5); no stage skill, overview or `workflow/tuning/running` reference mentions `taxonomy.yaml`, `prompt.md`, `seeds.csv` or `taxonomy-notes`; `workflow.md` has no "cannot edit notebooks"; the overview contains the ordered list, "notebook", "write only goldlabel calls" and no "guide to idioms"; docs block (`docs/agent-instructions.md`) states the order and the rule. Run: fails.

## Phase 2: User Stories 1 and 2 (P1)

- [ ] T002 [US1] [US2] Rewrite `src/goldlabel/skills/goldlabel/SKILL.md` (gold rule untouched at the top): the six stages as an ordered procedure, begin at the first, optional steps named, the fixed closing form, the entry-check refusal rule, repeat rule, minimal-code rule, in-code rule, notebook default, run-once cells (FR-009), "where files go" without the side files, commit the notebook. Edit `references/workflow.md` (remove the "idioms" framing, the seeds/taxonomy/prompt file guidance and the notebook fallback), `tuning.md` (the `prompt.md` line), keep `running.md` and `reuse.md` consistent.
- [ ] T003 [US1] [US2] Rewrite `goldlabel-connect`, `goldlabel-search-terms`, `goldlabel-taxonomy` into the fixed shape: Stage N of 6, entry check, numbered procedure (optional steps marked), exit check, `## Next`; no side files; seeds as a list in a cell; taxonomy as a `gl.Taxonomy(...)` cell the user approves; notes stay in the conversation; the reshaping and database fetch examples start with `# user-directed` and say they need the user's yes; replace comprehension examples with `gl`/`pl` calls. Keep every existing test-targeted block (`write_ndjson`, `is_in`) working.
- [ ] T004 [US1] [US2] Rewrite `goldlabel-candidates`, `goldlabel-tune`, `goldlabel-run` the same way: prompt as a string in a cell edited in place, no `open("prompt.md")`, no `assert` snippet (say instead: do not use items quoted in the prompt as gold; check by eye), no guards and name the run-once cells, `goldlabel-run` ends "Sequence complete" and names the optional follow-ups; tune keeps the explicit-yes fold text unchanged. Run `tests/test_skill_stages.py tests/test_skills.py -n0`.

## Phase 3: User Story 3 and the surrounding text

- [ ] T005 [US3] Update `tests/test_skills.py` (the taxonomy example test now asserts the block builds a `Taxonomy` with labels `scam`, `satire`, writing no file) and `README.md`, `docs/agent-instructions.md` (README block stays equal), `.kiro/steering/goldlabel.md`: order, "recommend the next step", minimal-code rule, taxonomy/prompt/seeds in code; README examples read seeds and the prompt from variables, not files. Run the whole suite.

## Phase 4: Close

- [ ] T006 Run ruff, ty and the whole suite; `/ponytail-review` on the diff and `/ponytail-debt`; update AGENTS.md "Current state" (011 implemented, the human trial SC-004 still to do) and `spec.md` Status; confirm `uv build` wheel still has the skills.

## Dependencies

T001 -> T002 -> T003 -> T004 -> T005 -> T006. T003 and T004 touch different files but share the closing form, so run in order.
