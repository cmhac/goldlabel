# Implementation Plan: Rename the library to goldlabel

> **Revision 2026-10-30 (user direction).** Nobody has used the library, so the final change keeps no
> compatibility code and no migration note, and the old name appears only under `specs/`. Anything
> below about recognising the legacy page stamp or old log lines, a README migration note, or an
> allowlist of legacy files describes the first plan and was **not** kept; `spec.md`, `data-model.md`,
> `contracts/rename-map.md` and `quickstart.md` are current.

**Branch**: `claude/admiring-hypatia-vc2jgs` | **Date**: 2026-10-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/008-rename-goldlabel/spec.md`

## Summary

Rename `hunches` to `goldlabel` everywhere the product shows or loads its name: package, install
name, docs alias `gl`, environment variables, default directory, labelling page and its
stamp, agent plugin and skill, CI, docs. Approach: gate on the user's approval of a name-only
constitution/rule amendment; write the failing tests (leftover-name, legacy stamp, old log line);
`git mv` three paths; one scripted replacement over tracked files with `specs/` history excluded;
add the one real piece of logic, mapping the legacy `hunches-ui` stamp onto the new one when
counting; regenerate `uv.lock`; verify with the four checks, the wheel and a clean install. No
shims, no aliases, no new dependency. Facts and decisions are in [research.md](research.md); the
before/after surface is [contracts/rename-map.md](contracts/rename-map.md).

## Technical Context

**Language/Version**: Python 3.12+ (`pyproject.toml`)

**Primary Dependencies**: none added or removed.

**Storage**: files only. The gold, cache, ledger, candidates and evaluation files are untouched in
format; only the default directory name and one stamp value change.

**Testing**: `pytest` (`asyncio_mode = "auto"`, xdist), the existing drift tests, plus one
repository-walk test. No real service is called.

**Target Platform**: any machine running Python 3.12 (notebooks and scripts), plus the four agent
hosts that load the plugin.

**Project Type**: library (`src/goldlabel`) shipped also as an agent plugin (`skills/goldlabel`).

**Performance Goals**: none.

**Constraints**: the gold rule's text changes by the name only; nothing is rewritten in a user's
gold file; importing the package still does no I/O; `specs/001`-`007` untouched.

**Scale/Scope**: about 154 renamed paths (about 120 are history under `specs/` and stay) and about
190 files touched by content, almost all by mechanical replacement.

## Constitution Check

*Gate: must pass before research; re-checked after design (below).* The Ponytail skill was invoked
(`ponytail`) before drafting the spec and again before this plan; its ladder was applied (does it
need to exist, already in the code base, standard library, installed dependency, minimum code), and
`/ponytail-review` will be run on spec, plan and tasks before `/speckit-implement`.

| Principle | Check | Result |
|---|---|---|
| I. Gold rule | The rule's text changes by the name only (FR-010, SC-003); nothing adds a way to set a label; `labelled_by` stamps are read, never rewritten; legacy labels keep their provenance (FR-006). The constitution says the rule MUST NOT be reworded and that amendments need `/speckit-constitution` with the user's approval, so a name-only PATCH amendment is **a precondition, not a task an agent decides** (FR-011). Task 1 stops and asks; nothing else that touches those two files runs before approval. | Pass, gated |
| II. Ponytail | One scripted replacement and one small helper; no alias package, fallback read, migration command, compat flag or registry (all listed under spec "Deliberately skipped"); no new dependency. | Pass |
| III. Spec Kit | Spec, plan and (next) tasks under `specs/008-rename-goldlabel/`; the CLI-generated files (`.specify/templates`, `.specify/scripts`, `.claude/skills/speckit-*`) are not edited. History specs 001-007 are not rewritten. `/ponytail-review` before and after implementation. | Pass |
| IV. Test-first | Red tests first (leftover-name, legacy stamp, old log line, rule text pinned inline); expectations written by hand, not derived from the code; the existing tests change by the mechanical replacement. No real service. | Pass |
| V. No hidden state | `.hunches/` and `HUNCHES_*` are no longer read, and nothing reads them as a fallback; files go where the argument, then `GOLDLABEL_DIR`, then `.goldlabel/` say. | Pass |
| VI. Honest costs and logs | Untouched; `evals.jsonl` stays append-only and old lines still load. | Pass |
| VII. Notebook library | `import goldlabel` still does no I/O and imports none of the forbidden modules (`test_public_api.py`, renamed); `__init__` exports exactly the same names. | Pass |
| Packaging constraint | Skill, `docs/agent-instructions.md`, Kiro steering and manifests are renamed together and stay drift-tested. The dev skills are not added to the plugin. | Pass |
| Podman | No container commands added. | Pass |

Re-check after design: no violation found. The only item that cannot be satisfied by the agent
alone is the amendment approval; it is recorded as the first task's stop condition, not as a
complexity exception.

## Project Structure

### Documentation (this feature)

```text
specs/008-rename-goldlabel/
├── spec.md
├── plan.md              # This file
├── research.md          # Facts checked and decisions
├── data-model.md        # The provenance-stamp table
├── quickstart.md        # Verification steps
├── contracts/
│   └── rename-map.md    # Old/new value for every name surface
├── checklists/
│   └── requirements.md
└── tasks.md             # Next: /speckit-tasks
```

### Source Code (repository root)

```text
src/hunches/ -> src/goldlabel/    # git mv; contents replaced; gold_rule.md via the amendment
skills/hunches/ -> skills/goldlabel/
.kiro/steering/hunches.md -> .kiro/steering/goldlabel.md
pyproject.toml, uv.lock, .gitignore, .github/workflows/ci.yml
.claude-plugin/{plugin,marketplace}.json, plugin.json
README.md (+ migration note), AGENTS.md (CLAUDE.md is its symlink), docs/agent-instructions.md
examples/sample/{walkthrough.py,walkthrough.ipynb,README.md}
tests/**                          # imports, aliases, expectations; new tests/test_no_old_name.py
.specify/memory/constitution.md   # only through /speckit-constitution
```

**Structure Decision**: no new files in `src/`. The one new behaviour is a small helper in
`src/goldlabel/gold.py` that maps the stamp `hunches-ui` to `goldlabel-ui` for counting, used by
`GoldSet._summary` and by the provenance count in `evaluation.py`, so the legacy value appears in
exactly one place in the package. One new test file; all other test changes are replacements.

## Order of work (becomes `tasks.md`)

1. **Amendment gate (human)**: show the user the name-only diff to Principle I, the packaging
   line and the title; run `/speckit-constitution` only after approval (PATCH, 1.1.0 to 1.1.1);
   record the approval. Stop here if it is not given.
2. **Red**: add `tests/test_no_old_name.py`, the legacy-stamp case, the old-log-line case and the
   pinned-rule-text case; run them and show them failing for the right reason.
3. **Rename**: `git mv` the three paths; run the scripted replacement (order and exclusions in
   research R6); apply the amendment's `gold_rule.md` text; add the stamp helper; add the README
   migration note; `uv lock`; `ruff check --fix` and `ruff format`; review the diff for alias
   false positives and for any line that still says "pip install hunches".
4. **Verify and report**: the quickstart steps, `/ponytail-review` on the diff, `/ponytail-debt`,
   and the human-only list (plugin reinstall and gold-rule refusal trial per agent, README install
   commands marked unverified, labelling page in a browser, repository rename and ordering with
   the merge).

One commit per task, `008/TNN: ...`, on the assigned branch; no pull request unless asked.

## Complexity Tracking

No violations to justify. The legacy-stamp helper is not a compatibility layer for the name; it
protects the provenance of labels people already made (R2).
