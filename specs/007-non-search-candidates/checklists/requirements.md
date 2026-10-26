# Specification Quality Checklist: Non-search candidate sources

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-26
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- This is a library, so its public function names (`hn.keywords`, `hn.everything`) are the user
  interface and appear in the spec; they are marked as provisional in Assumptions and confirmed in
  the plan. The mentions of the fake `psycopg` and stubbed S3 client are in Assumptions and
  Success Criteria only as how verification is done, per the constitution's testing rules.
- Both clarification questions resolved 2026-10-26 (ranking: distinct terms then total matches;
  server-side regex: strings in Postgres syntax, compiled patterns refused). The whole-corpus-larger-than-memory question keeps its default
  (use the existing result-size limit and refuse beyond it).
- Open item for the plan, not the spec: whether S3 Vectors can list a whole index with metadata
  (check against current AWS docs before planning that reader).
- Ponytail was applied: the spec carries a "Deliberately skipped" list and asks for no option,
  abstraction or format beyond the two calls and an optional-similarity candidate list.
- 2026-10-26: `LocalCorpus` is removed in favour of `Table` (FR-024). This is a hard break to a
  public name, accepted because the library is unpublished: no shim and no migration note, and the
  docs describe only the table format. The plan must list every file that mentions it (code, tests, example corpus, README, `AGENTS.md`, skill
  references) and convert the sample corpus into a table.
