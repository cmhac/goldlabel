# Specification Quality Checklist: Samples: rerun-safe, seedless gold draws, and named gold datasets

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
- Decisions from the user (2026-11-04): the page shows only the rows pending in the pass; `Gold(candidates, sample_size=50)`; `draw_sample(split, n=None)` with `draw_dev`/`draw_test`; draws top a split up to its size in an id-fixed order, no seeds, no guards (option 3); draws return a `Sample` that `gl.label` and `clf.evaluate` take; evaluation is a classifier method (`clf.evaluate`/`clf.aevaluate`), `gl.evaluate` removed.
- Judgement calls for the user to overturn: candidates optional on `Gold`; `Gold(candidates=None, *, name=None, path=None, sample_size=50)` breaks positional `Gold(path)`; no `draw` alias; `gold.dev`/`gold.test` become live Samples including pending rows; evaluating a test Sample with pending rows is refused; the name salts the draw order.
- `/ponytail-review` of spec, plan and tasks is still required before `/speckit-implement`.
