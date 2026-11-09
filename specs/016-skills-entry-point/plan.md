# Implementation Plan: `/goldlabel` as a complete entry point

**Branch**: `claude/tender-heisenberg-vfoip3` | **Date**: 2026-11-09 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/016-skills-entry-point/spec.md`

## Summary

Text and tests only. No library, CLI, page or file-format change (FR-012).

- **Overview skill** (`src/goldlabel/skills/goldlabel/SKILL.md`) gains, in this order: a **Step 0: check progress** (read-only; evidence table, one row per stage; report, mark unsure, wait for the user's yes; resume at the first stage without evidence); a **stage guide** (one short block per stage: purpose in plain words, the user's decisions, what to show, the approval to wait for); **how to talk the user through a step** (five short rules); and **the labelling and review page** (jobs, `goldlabel label [NAME]`, `gl.label(sample, taxonomy)`, `force_open_ui=True`, joining a running page, STALE, "every revision goes through the page"). The existing procedure, hard rules, code rule and references stay.
- **`goldlabel-tune`**: at step 5 (reading disagreements) offer the page's evaluation view next to `ev.disagreements_to_polars()`; after a revision say the evaluation is STALE and evaluate again; the held-out rule is untouched.
- **Instruction text**: two new bullets (start at `goldlabel`, which checks progress first; the revise-in-the-page bullet already exists) in `POINTERS` in `cli.py`, `.kiro/steering/goldlabel.md` (which a test requires to equal `steering_text()`) and `docs/agent-instructions.md` (hand-copied; no test ties it to `POINTERS` today).
- **Tests**: `tests/test_skill_stages.py` grows (progress check, per-stage evidence, page mention in overview and tune, no gold-edit instruction); one assertion ties the new bullet in `docs/agent-instructions.md` to `POINTERS`.

Choices are in [research.md](research.md), the shape of the added text in [data-model.md](data-model.md) and [contracts/skill-text.md](contracts/skill-text.md), the checks in [quickstart.md](quickstart.md).

## Technical Context

**Language/Version**: Markdown agent text; Python 3.12+ for the tests.

**Primary Dependencies**: none new.

**Storage**: N/A (the skills describe `gold*.json`, `evals.jsonl`, `candidates.jsonl`; nothing is written).

**Testing**: pytest, text checks over the shipped skill files (the existing `test_skill_stages.py` pattern); red first.

**Target Platform**: any agent that loads the skills (Claude Code, Codex, Copilot CLI, Kiro) or reads the instruction block.

**Project Type**: library with shipped agent skills.

**Performance Goals**: none. The overview stays readable in one pass: target at most about 140 lines (61 today).

**Constraints**: gold rule text verbatim and unmoved (its drift tests print the text to paste); every Python block in a skill or reference passes the goldlabel-calls-only test; skills ship in the wheel unchanged in layout (seven folders); no side files.

**Scale/Scope**:

| File | Change |
|---|---|
| `src/goldlabel/skills/goldlabel/SKILL.md` | 61 → about 130 lines |
| `src/goldlabel/skills/goldlabel-tune/SKILL.md` | about +8 lines at steps 3, 5, 6 |
| `src/goldlabel/skills/goldlabel/references/tuning.md` | one or two lines, if it describes reading disagreements without the page |
| `src/goldlabel/cli.py` (`POINTERS`), `.kiro/steering/goldlabel.md`, `docs/agent-instructions.md` | one new bullet each, one wording |
| `tests/test_skill_stages.py` | about +60 lines |
| `AGENTS.md` | "Current state" entry for 016 and the human checks (agent trial, refusal trial) |

## Constitution Check

*GATE: passes before Phase 0; re-checked after Phase 1.*

| Item | Result |
|---|---|
| I. Gold rule | PASS. The rule text is not touched. The text added sends every revision to the page and offers no other route; a test fails on any skill or reference that offers a gold edit. The progress check never prints gold text or labels in bulk (FR-004). |
| II. Ponytail | PASS. The skill was invoked before the spec and this plan. Skipped items are in the spec and in research.md. |
| III. Spec Kit | PASS. spec → plan; tasks and `/ponytail-review` of spec, plan and tasks come before implementing (not waived). |
| IV. Test-first | PASS. Each task starts with the failing text test. No model, service or browser is involved. |
| V. No hidden state | PASS. The progress check is a read of the user's own files by the agent; no status file, no library helper. |
| VI. Honest costs and evaluations | PASS. No evaluation or cost behaviour changes; the held-out rule is restated unchanged; the page offered at the reading step never licenses reading test disagreements to tune. |
| VII. Notebook library | PASS. Nothing in the library changes. |
| Skills constraints (011) | PASS. Order, four parts, the code rule and the closing "Next" lines are unchanged and still tested. |

**Post-design re-check**: unchanged. No complexity to justify.

## Project Structure

### Documentation (this feature)

```text
specs/016-skills-entry-point/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── skill-text.md
├── checklists/requirements.md
└── tasks.md             # /speckit-tasks
```

### Source Code (repository root)

```text
src/goldlabel/
├── cli.py                              # POINTERS: one bullet
└── skills/
    ├── goldlabel/SKILL.md              # progress check, stage guide, talk-through, the page
    ├── goldlabel/references/tuning.md  # only if it contradicts the page
    └── goldlabel-tune/SKILL.md         # steps 3, 5, 6
docs/agent-instructions.md              # one bullet
.kiro/steering/goldlabel.md             # one bullet (== steering_text())
tests/test_skill_stages.py              # the new assertions
AGENTS.md                               # current state, human checks
```

**Structure Decision**: edit the existing files; add no skill folder (a seventh stage or a separate "resume" skill would break `test_there_are_exactly_the_overview_and_six_stages` and the one-entry-point goal).

## Complexity Tracking

No violations.
