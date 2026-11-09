# Feature Specification: README explains the skills and the labelling page

**Feature Branch**: `claude/bold-ritchie-n31ibp`
**Created**: 2026-11-09
**Status**: Approved (simple docs change; the user asked for the whole process unattended)
**Input**: GitHub issue [#28](https://github.com/cmhac/goldlabel/issues/28)

## Why

A tester worked from the README and did not know the skills exist as a guided workflow. The README's install block also says `ub add`, which is not a command.

## User Story 1 - A reader learns what the skills are and where to start (P1)

**Scenarios**
1. Given the README, a reader finds that `goldlabel install <agent>` copies the skills into the agent's skills folder (Claude Code `.claude/skills`, Codex and Copilot `.agents/skills`, Kiro `.kiro/skills`; `--global` for the home directory).
2. The README says `/goldlabel` is where to start: it checks what the user already has and names the next stage skill.
3. The README says the skills are optional: the library is plain functions and the example workflow works without an agent.
4. The README describes a session: the agent asks, shows, waits for the user's yes at each of the six stages, writes only goldlabel calls in one notebook, and never writes a gold label; people label in the page.

## User Story 2 - A reader learns the labelling page and how to start it (P1)

The labelling step of the workflow points to the page, and the page section says how to start it (`goldlabel label`, or `gl.label`), as it already does for review and revision. The feature 015 page has landed, so the issue's condition is met.

## User Story 3 - The install block is correct (P1)

`ub add` becomes `uv add` in all five lines.

## Requirements

- FR-001: the README changes only in the places above; no code, skill or gold-rule text changes.
- FR-002: every command and path the README states matches `src/goldlabel/cli.py` and `goldlabel install --help`.
- FR-003: `tests/test_docs.py` still passes (it requires `goldlabel label` in the README).

## Deliberately skipped

- A README test: the user chose that the README has no tests (AGENTS.md); checked by reading against `cli.py`.
- Screenshots of the page and an agent transcript: not verifiable here; the human checks in AGENTS.md cover the page.
- Reflowing the existing README typos (`teh`, `LLMs classifiers`): outside the issue.
