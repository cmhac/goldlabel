# Implementation Plan: Docstrings that explain every public function, enforced by ruff

**Branch**: `claude/stoic-bardeen-rgigyw` | **Date**: 2026-11-10 | **Spec**: [spec.md](spec.md)

**Input**: `specs/019-docstrings-and-ruff/spec.md`; decisions and measurements in [research.md](research.md)

## Summary

Write a Google-style docstring on every public callable of `goldlabel` (31 of 68 have none; `with_prompt` first, the issue), audit the 37 that have one, and turn on ruff's `D` rules (Google convention) plus the preview `DOC201`/`DOC501` rules in `pyproject.toml` so the existing `ruff check` fails on regressions. One small test closes the one gap ruff leaves (a public function with arguments and no `Args:` section). No runtime code changes.

## Technical Context

**Language/Version**: Python 3.12+ (unchanged)
**Primary Dependencies**: none added; ruff 0.17.3 already pinned in `uv.lock`
**Storage**: N/A
**Testing**: pytest; one new file `tests/test_docstrings.py`, plus a red/green check of the ruff rules with a scratch file outside the repo
**Target Platform**: unchanged (library, editor hover, `help()`, notebook `?`)
**Project Type**: library
**Performance Goals**: N/A
**Constraints**: no behaviour, signature or public name changes (FR-010); gold rule text and every way to set a label untouched; ruff, ty, pytest pass before every commit
**Scale/Scope**: 68 public callables, 119 `D` findings and 121 `DOC` findings to clear (research R1), 11 source modules

## Constitution Check

| Principle | Status |
| --- | --- |
| I Gold rule | Docstrings in `gold.py` and `_label.py` only describe the existing behaviour; none adds, softens or rewords the rule (it is quoted through `GOLD_RULE_SHORT`, never copied). `gold_rule.md`, `_gold_rule.py`, their drift tests untouched. Pass. |
| II Ponytail | No new dependency, option or module. One 20-line test, justified by the measured gap (research R3). Skips listed in the spec. Pass. |
| III Spec Kit | spec -> plan -> tasks; `/ponytail-review` before implementing (waived only by the user). Pass. |
| IV Test-first, no real services | The Args test is written first and fails on the 37-or-so offenders, then passes; the ruff rules are shown red then green. No service called. Pass. |
| V Code is the pipeline | No state added. Pass. |
| VI Honest costs | Docstrings must state cost and logging effects accurately (`evaluate` always appends to `evals.jsonl`; unknown price is `?`, `max_cost` refuses). Checked in the audit. Pass. |
| VII Library for notebooks | The goal of the feature: what `help()` shows in a notebook. Pass. |

No violations; nothing in Complexity Tracking.

## Design

1. **Config** (`pyproject.toml`, `[tool.ruff.lint]`): `select = ["D", "DOC201", "DOC501"]`, `preview = true`, `explicit-preview-rules = true`, `ignore = ["D105", "D107"]`, `[tool.ruff.lint.pydocstyle] convention = "google"`. `per-file-ignores`: `tests/**`, `examples/**`, `scripts/**`, `specs/**` ignore `D` and `DOC`; `src/goldlabel/_*.py` ignore `D` and `DOC`. The existing `ty`, pytest and pre-commit entries are unchanged: `ruff check` already runs in both pre-commit and CI.
2. **Docstring standard** (what the audit checks; recorded as the first lines of `tests/test_docstrings.py`' module docstring, not a new doc): summary line in the imperative or noun phrase, blank line, then `Args:` (meaning, allowed values, units), `Returns:`, `Raises:` (only the exceptions raised on purpose), and a short `Note:`/paragraph for effects: files written and where, live model calls and cost, network or database reads, a page opened, "returns a new X; the original is unchanged". Plain words; no spec numbers, no agent jargon (FR-006).
3. **Order of work**: public classes users meet first (`Classifier`, `Gold`/`Sample`, `Candidates`, `Evaluation`), then corpora (`Table`, `S3Corpus`, `PgCorpus`), then the rest, finishing with the module docstrings. The `with_prompt` docstring is written and checked against `system_prompt()` first (FR-001, research R6).
4. **Test** (`tests/test_docstrings.py`): iterate `goldlabel.__all__`; for each class, its public methods and properties (via `vars`, as the measurement did), assert a docstring and, when there are parameters beyond `self`/`cls`, an `Args:` heading. Failure message names `Class.method`.
5. **Agent rule** (FR-011): two lines in `AGENTS.md` Conventions; `CLAUDE.md` is the symlink.

Project structure: only `pyproject.toml`, `AGENTS.md`, `tests/test_docstrings.py`, the eleven `src/goldlabel/*.py` modules and this spec folder change.

## Risks

- A preview rule can change on a ruff upgrade; `uv.lock` pins it, and an upgrade is a deliberate commit that re-runs `ruff check`.
- `ruff format` reflows docstring code blocks in Markdown and Python; run it after editing.
- Docstring text is checked by reading only (spec "Deliberately skipped"); the audit table in `tasks.md` T03 is that record.
- The 19 auto-fixable layout findings (`D209`) change only whitespace inside docstrings.

## Deliberately skipped

Everything in the spec's list, plus: a custom lint script for docstring prose; `ignore-one-line-docstrings = true` (research R2: would let a public one-liner with a return value pass); a `data-model.md` and `contracts/` (no data, no new interface: the public API does not change).
