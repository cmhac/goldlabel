# Implementation Plan: Ordered stage skills and minimal agent code

**Branch**: `claude/sharp-galileo-vi4k0k` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/011-ordered-minimal-skills/spec.md`. Closes [issue #16](https://github.com/cmhac/goldlabel/issues/16).

## Summary

Text and tests only. Rewrite the overview skill and the six stage skills into one fixed shape (entry check, numbered procedure, exit check, closing "Next"), state the minimal-code, in-code and notebook-first rules in the overview and in each stage, remove the side-file and fallback guidance, and add one drift test that enforces the shape, the chain, and the code rule. No library change, no new skill, no new dependency.

## Technical Context

**Language/Version**: Markdown skills; Python 3.12 tests.
**Primary Dependencies**: none new (`pytest`, `ast`, `re`, `yaml` already used by `tests/test_skills.py`).
**Storage**: N/A.
**Testing**: pytest. New `tests/test_skill_stages.py`; two existing tests change.
**Project Type**: library with shipped agent skills.
**Constraints**: the gold rule stays verbatim at the top of every skill and in every description (`tests/test_skills.py`); the wheel ships `src/goldlabel/skills/`; the README instruction block equals `docs/agent-instructions.md`.
**Scale/Scope**: 7 skill files, 4 reference files, README, 2 instruction files, the walkthrough text.

## Constitution Check

*GATE: passed before design and re-checked after.*

- **I Gold Rule**: untouched. The rule text, descriptions and verbatim tests stay; only text after the rule changes. Pass.
- **II Ponytail**: the `ponytail` skill was applied to this plan. Smallest change: one test file, no helper module, no parser library, no new skill, no stage runner (spec "Deliberately skipped"). Research, data-model and contracts are skipped: nothing to research, no data, no interface. Pass.
- **III Spec Kit**: spec -> plan -> tasks; `/ponytail-review` before implement. Pass.
- **IV Test-first**: the drift test is written first and fails on today's skills. Expected values are written by hand in the test (the six stage names, the four headings). Pass.
- **V Code is the pipeline**: no stored status; the entry check reads the notebook and files. Pass.
- **VI Honest costs / VII notebooks**: unchanged. Pass.

## Design decisions

1. **One shape, fixed headings.** After the verbatim gold rule, each stage skill is: a title line `Stage N of 6: <name>`, `## Entry check`, `## Procedure` (numbered, one action per step, each "ask" step says what to ask), `## Exit check`, `## Next`. The optional parts of a stage (corpus `where=`, band sample, saving a classifier, folding the test split) are numbered steps marked `(optional)`; none is a skill.
2. **Entry check names the previous stage.** Every stage after the first says: "If any of this is missing, say which stage is unfinished (`goldlabel-<previous>`), offer to run it, and continue only if the user tells you to skip it." The first stage's entry check is the user's brief.
3. **Closing "Next" in a fixed form** (defined once in the overview, repeated in each stage): `**Next: \`goldlabel-<next>\`.** Tell the user: what is done, what it produced, what they approved, and that the next stage is \`goldlabel-<next>\`; offer to start it.` The last stage says `**Sequence complete.**` and names the optional follow-ups (save and reuse the classifier, report).
4. **Repeat rule.** Each stage ends its procedure with one line on what must be re-run after it is repeated (for example changing a label means re-running `goldlabel-tune` and `goldlabel-run`).
5. **Minimal code, enforced by a deny-list, not a parser.** A stage skill's python block fails the test if it contains a def, class, lambda, if, for, while, with, try, assert, comprehension, or a call to `open`, `Path`, `os`, `json`, `load_dotenv` or any attribute starting with `write`; a block whose first line is `# user-directed` is exempt (the connect-skill reshaping example and the single database fetch step). `shortcut: a deny-list misses a creative construct; tighten it when a notebook shows one.`
6. **Everything in code.** Taxonomy, prompt and seeds are variables in cells; the taxonomy skill's "approved" is a cell plus the user's yes; the search-terms skill's `seeds.csv` write and the tune skill's `open("prompt.md")` are removed. `references/reuse.md` keeps describing the bundle `clf.save` writes.
7. **Notebook by default**; "When you cannot edit notebooks" is removed from `references/workflow.md`; the walkthrough keeps its notebook and script pair (the existing test requires them equal).
8. **Re-run guards (FR-009)**: one sentence in the overview and in `goldlabel-tune`: no guards; say which cells are run-once.
9. **Issue #16 wording**: the overview states that recommending the next step is a hard requirement of the workflow.

## Project Structure

### Documentation (this feature)

```text
specs/011-ordered-minimal-skills/
├── spec.md
├── plan.md
├── quickstart.md
└── tasks.md
```

### Source Code

```text
src/goldlabel/skills/goldlabel/SKILL.md            # procedure, hard rules, closing form, minimal code, notebook default
src/goldlabel/skills/goldlabel/references/*.md      # workflow (drop fallback), tuning, running, reuse
src/goldlabel/skills/goldlabel-{connect,search-terms,taxonomy,candidates,tune,run}/SKILL.md
docs/agent-instructions.md  README.md  .kiro/steering/goldlabel.md   # order + minimal-code sentences
tests/test_skill_stages.py                           # new
tests/test_skills.py  tests/test_docs.py             # taxonomy example test; README block equality
```

**Structure Decision**: edit in place; one new test file.

## Complexity Tracking

No violations.
