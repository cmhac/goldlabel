# Specification Quality Checklist: A simpler gold API: candidates and sample size on `Gold`, a required split, named datasets

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-11-04
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs) beyond the library's own public names, which are the user-facing interface
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders (as far as a Python-library spec allows)
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded ("Deliberately skipped")
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Ponytail skill applied before drafting; the spec carries a "Deliberately skipped" list.
- Decisions from the user (2026-11-04): required `split` on `gl.label`; the page shows only the rows pending in the pass; `Gold` takes the candidates and a `sample_size` (default 50, per split); `draw` becomes `draw_sample(split, n=None, seed=None)` with `draw_dev`/`draw_test` shortcuts; `n` overrides the size for one call.
- Judgement calls made as defaults, for the user to overturn: candidates optional on `Gold` (needed only to draw); `Gold(candidates=None, *, name=None, path=None, sample_size=50)` breaks positional `Gold(path)`; no `draw` alias; a name is only a file name; per-dataset log counts reuse the gold path already on each log line.
- `/ponytail-review` of spec, plan and tasks is still required before `/speckit-implement`.
