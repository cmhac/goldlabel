# Specification Quality Checklist: Open the labelling page only when rows are pending

**Created**: 2026-11-04 | **Feature**: [spec.md](../spec.md)

## Content Quality
- [x] Focused on user value
- [x] Mandatory sections completed
- [x] No implementation details beyond the named public call

## Requirement Completeness
- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Acceptance scenarios and edge cases defined
- [x] Scope bounded ("Deliberately skipped")
- [x] Assumptions identified (option name `review`, `block=False` return)

## Notes
- Gold rule untouched: the skip path writes nothing.
