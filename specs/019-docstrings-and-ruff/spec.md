# Feature Specification: Docstrings that explain every public function, enforced by ruff

**Feature Branch**: `claude/stoic-bardeen-rgigyw`
**Created**: 2026-11-10
**Status**: Draft
**Input**: GitHub issue [#31](https://github.com/cmhac/goldlabel/issues/31) ("Need clarity on the with_prompt function"), plus: "the docstrings will explain to any user who is not using an AI agent what each function does", and "enforce strict docstring requirements with ruff".

## Why

A user hovering over `Classifier.with_prompt` in their editor sees only `def with_prompt(text: str) -> Classifier`. It has no docstring, so they cannot tell whether it replaces the instructions, appends to them, or changes the classifier in place. The code answers it (`replace(self, prompt=text)`: it **replaces the instructions text and returns a new `Classifier`**; the label list, the one-label/every-label rule, the `off_topic` rule and the reasoning instruction are always added after it by `system_prompt`), but nothing the user can read says so.

`with_prompt` is not the only case. Measured on 2026-11-10 against the code on this branch (installed `ruff 0.17.3`, `ruff check --select D`, Google convention): **31 of 68** public callables exported through `goldlabel.__all__` have no docstring (`Classifier.with_prompt`, `with_taxonomy`, `Gold.label`, `Gold.pending`, `Gold.all`, `Candidates.above`, `bands`, `top_seeds`, `write`, `Evaluation.score`, `passed`, `write`, `Sample.rows`, `counts`, `path`, all `to_polars`/`to_pandas`, and more), and ruff reports 119 docstring findings in `src/` (35 undocumented public methods, 11 undocumented public functions, 9 modules, 5 classes, 5 `__init__`s, plus 19 docstrings whose summary line is not followed by a blank line). The agent skills explain the library to agents; nothing explains it to a person reading their editor's hover text, `help()` or a notebook's `?`.

## User Story 1 - A person hovering over `with_prompt` learns what it does (P1)

A journalist or analyst writing a notebook by hand (no agent) hovers over or runs `help(clf.with_prompt)` and reads, in plain words, that it replaces the instructions, what is still added automatically, that the original classifier is untouched, and what that does to the cache and to cost.

**Why this priority**: it is the issue. It is the smallest slice that fixes the reported problem.

**Independent Test**: read `Classifier.with_prompt.__doc__`; it states "replaces", not "appends"; names what the library always adds after the text; says a new `Classifier` is returned and the original is unchanged; and says a changed prompt means the next `classify`/`evaluate` calls the model again for each item.

**Acceptance Scenarios**:

1. **Given** a `Classifier` built with prompt A, **When** the user reads the docstring and then runs `clf.with_prompt("B")`, **Then** the new classifier's prompt is exactly `"B"`, `clf.prompt` is still `"A"`, and the docstring said so.
2. **Given** the docstring, **When** a reader who has never seen the skills reads it, **Then** they can say what text the model finally receives (their text, then the labels, the mode rule, the `off_topic` rule and the reasoning instruction) without opening the source.

---

## User Story 2 - Every public function says what it does, in the same shape (P1)

Every public name in `goldlabel.__all__` and every public method and property on those classes has a docstring a non-agent user can act on: what it does in one line, what each argument means (including units and allowed values), what it returns, what it raises, and what it does beyond returning (writes a file and where, makes live model calls, spends money, opens a page, reads the network or a database). Names that look alike say how they differ (`with_prompt` vs `with_taxonomy`; `Gold.label` vs `Gold.pending` vs `Gold.all`; `Evaluation.score` vs `passed`; `write` on `Candidates`, `Evaluation` and `Taxonomy`).

**Why this priority**: the issue asks for "any other unclear functions"; the 31 undocumented ones are the known set, and the already-documented ones have to be audited for the same gaps (a one-line summary that omits replace-versus-append, mutate-versus-copy, or "costs money").

**Independent Test**: walk the list of public callables (the 68 above, recounted at implementation time); each has a docstring with a summary line and the parts that apply (arguments, returns, raises, side effects), and each of the lookalike pairs above says how it differs from the other.

**Acceptance Scenarios**:

1. **Given** any public function or method, **When** the user calls `help()` on it, **Then** they see a summary, its arguments, its return value, any exception it raises on purpose, and any file, network or cost effect.
2. **Given** a function that returns a new object rather than changing its own (`with_prompt`, `with_taxonomy`, `Sample` arithmetic with `+`), **When** the docstring is read, **Then** it says the original is unchanged.
3. **Given** a function that spends money or changes a file on disk, **When** the docstring is read, **Then** it says so and names the control (`max_cost`, `estimate`) or the file name.
4. **Given** the gold rule, **When** any docstring in `gold.py` or `_label.py` is edited, **Then** it does not describe a way for code to set a label (Principle I); `gold_rule.md` and its drift tests are untouched.

---

## User Story 3 - Ruff fails a commit that adds an undocumented or malformed public docstring (P1)

`pyproject.toml` turns on ruff's strict docstring rules so a new public function without a docstring, or one that leaves out an argument, a return or a raised exception, fails `ruff check` locally (pre-commit) and in CI, the same way every other lint does.

**Why this priority**: without enforcement the docstrings rot back to the current state. The user asked for it explicitly.

**Independent Test**: add a public function with no docstring, one with a missing argument description, and one that raises without saying so; `uv run ruff check` fails on each; remove them and it passes.

**Acceptance Scenarios**:

1. **Given** the change is complete, **When** `uv run ruff check` runs on a clean checkout, **Then** it reports no docstring findings and the existing pre-commit and CI steps run it with no new step.
2. **Given** a new public method with no docstring, **When** ruff runs, **Then** it fails on that method.
3. **Given** a public function whose docstring lists some but not all of its arguments, **When** ruff runs, **Then** it fails.
4. **Given** tests, examples and specs, **When** ruff runs, **Then** they are not asked for docstrings.

---

### Edge Cases

- Private names (leading underscore) and private modules (`_label.py`, `_html.py`, `_frame.py`, `_sync.py`, `_gold_rule.py`) do not need public-style docstrings; ruff already skips them for the `D` rules, but the `DOC` rules (see Assumptions) also inspect private helpers: 119 findings today, most in private code.
- Dunder methods (`__repr__`, `_repr_html_`, `__add__`): `D105` flags 16 of them. `__repr__` and `_repr_html_` are not worth a docstring each; `__add__` on `Sample` is a public way to combine samples and does need one.
- Dataclass and pydantic fields have no docstring of their own; the class docstring must document them (an "Attributes" section).
- `Evaluation.passed`, `Predictions.errors`, `Sample.path` are properties: ruff and editors show the property's docstring, not a signature.
- The gold rule text is copied verbatim into skills and docs and checked by `tests/test_gold_rule.py`; docstrings must not reword it, only link to `goldlabel.GOLD_RULE_SHORT`.
- A docstring change must not change behaviour: the 119 findings include 19 auto-fixable layout ones; those fixes must not touch code.
- Docstring examples must be runnable-looking but are not executed (no doctest run: the library calls models and writes files).

## Requirements

### Functional Requirements

- **FR-001**: `Classifier.with_prompt` MUST have a docstring that says it replaces (does not append to) the instruction text; says what the library always adds after it (label list with descriptions, the one-label or every-label rule, the `off_topic` rule, the reasoning instruction); says it returns a new `Classifier` and leaves the original unchanged; and says a changed prompt means results are not reused from the cache. It MUST be correct against `system_prompt()` in `classifier.py`.
- **FR-002**: Every public callable (each name in `goldlabel.__all__`, and each public method and property of the exported classes) MUST have a docstring starting with a one-line summary, then a blank line, then the parts that apply: arguments with meaning and allowed values, return value, exceptions raised on purpose, and effects beyond the return value (files written and where, live model calls and cost, network or database reads, a page opened).
- **FR-003**: Every public module and public class MUST have a docstring; a class docstring MUST describe its public fields and how a user normally gets one (which function returns it).
- **FR-004**: Functions that return a changed copy MUST say the original is unchanged; functions that write a file MUST name the file or folder (`gl.settings.root` rules) and whether an existing file is overwritten.
- **FR-005**: The already-documented public callables MUST be audited against FR-002; any gap found (a one-line docstring that hides a side effect, a cost, or a replace/append/copy behaviour) is filled in the same change. The audit's result (callables checked, gaps found) is recorded in the feature's tasks file.
- **FR-006**: Docstrings MUST be plain language for a reader who has not read the skills or the spec: no spec numbers (no "014", no "Implemented in task 07"), no agent jargon, terms of the domain (gold set, sample, seed) explained once where first used or pointed to the class that explains them.
- **FR-007**: `pyproject.toml` MUST enable ruff's docstring rules for `src/` so that a missing docstring on a public module, class, function, method or property, a missing blank line after the summary, a missing documented argument, a missing documented return, and a missing documented raised exception each fail `ruff check`. Exact rule codes and the docstring convention are chosen in the plan, checked against the installed ruff (`ruff rule <code>`), not from memory.
- **FR-008**: Tests, `examples/` and `specs/` MUST be exempt from the docstring rules (existing `per-file-ignores` style).
- **FR-009**: The enforcement MUST run through the existing `ruff check` command, so pre-commit and CI need no new step, and `uv run ruff check`, `ruff format --check`, `ty check` and `uv run pytest` MUST pass.
- **FR-010**: The change MUST NOT alter runtime behaviour or any public name or signature, and MUST NOT touch `gold_rule.md`, `_gold_rule.py` or any way of setting a gold label.
- **FR-011**: `AGENTS.md` (and so `CLAUDE.md`) MUST say, in one or two lines under Conventions, that public docstrings are written for a person with no agent, name the ruff rule set that enforces them, and what a docstring must contain.

### Key Entities

- **Public callable**: a function, method or property reachable from `goldlabel.__all__` without an underscore: what the user sees in their editor.
- **Docstring parts**: summary, arguments, returns, raises, effects; the unit ruff checks and the unit the audit records.

## Success Criteria

### Measurable Outcomes

- **SC-001**: 0 of the public callables exported through `goldlabel.__all__` lack a docstring (31 of 68 today).
- **SC-002**: `uv run ruff check` reports 0 docstring findings on `src/` (119 today under the Google convention, `D` rules), and fails on each of the three test cases in User Story 3.
- **SC-003**: Reading only `help(Classifier.with_prompt)`, a person who has not seen the issue answers correctly: does it replace or append (replace); is the original changed (no); what else does the model receive (labels, mode rule, `off_topic`, reasoning); do old cached results apply (no).
- **SC-004**: Each of the lookalike pairs in User Story 2 has docstrings that, read side by side, state the difference in one sentence each; checked by reading, recorded in the tasks file.
- **SC-005**: The full test suite passes unchanged apart from any test that read a docstring; no test, signature or public name changes.

## Assumptions

- "Public" means what the library exports: names in `goldlabel.__all__` and the public members of those classes. Private modules and underscore names are out of scope for the written-for-a-person standard (they keep the comments they have).
- The audit's baseline (68 callables, 31 undocumented, 119 findings) was measured with `ruff 0.17.3` and the Google convention on this branch; the plan re-measures with the version `uv.lock` pins.
- Google-style sections (`Args:`, `Returns:`, `Raises:`) are the house style because they read well in an editor hover and in `help()`; NumPy style is the alternative and is not chosen unless the plan finds a reason. The plan confirms this against ruff's docs and the installed version.
- The `Returns` and `Raises` checks (`DOC201`, `DOC501`) are *preview* rules in ruff 0.17.3 and fire on private helpers too (119 findings today, mostly private). Whether to use them (with `explicit-preview-rules` and per-file exemptions for private modules) or to settle for the stable `D` rules including `D417` (every argument documented) is a plan decision, taken with the finding counts in front of it; the spec's requirement (FR-007) is that missing returns and raises fail ruff if ruff can do that without a flood of false positives on private code.
- Prose cannot be linted: ruff proves a docstring exists and has the parts, not that it is clear. Clarity is checked by the reading tests in SC-003 and SC-004.
- The README and the agent skills are not rewritten; they already explain the workflow. A docstring may link to a skill name where that helps, never replace a docstring with one.

## Deliberately skipped

- A docs site (Sphinx, MkDocs, mkdocstrings): docstrings are the documentation, read in the editor and `help()`; a site is a separate feature.
- A doctest run or a docstring-example test: the functions call models, write files and open a page.
- A test that checks docstring prose (for example that `with_prompt`'s mentions "replaces"): reviewed by reading, recorded in the tasks file; one bad edit costs a reader a hover, not data.
- Docstrings for private helpers, tests, examples and specs.
- Renaming functions or changing behaviour to make them clearer; the issue asks to explain, not to redesign (for example, adding a `with_prompt(append=...)` option).
- Rewriting the README or the skills.
