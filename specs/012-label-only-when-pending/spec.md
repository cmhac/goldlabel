# Feature Specification: Open the labelling page only when rows are pending, and always wait for it

**Feature Branch**: `claude/sharp-galileo-vi4k0k` (the assigned branch; the spec directory name is independent of it)

**Created**: 2026-11-04

**Status**: Implemented (human checks listed in AGENTS.md)

**Input**: User description: "Drawing a gold dataset should only run the data entry server if there are actually more rows to label. If all rows have been labeled, it should just print a statement that all rows are labeled and skip data entry, unless an explicit option is passed." Follow-up from the user: drop the `block` parameter so `gl.label` only ever blocks until **Done**.

## Where things are today

- The labelling server is started by `gl.label(gold, taxonomy)` (`src/goldlabel/_label.py`), not by `gold.draw`, which only writes pending rows. This spec changes `gl.label`; `draw` is untouched.
- `gl.label` always starts the server, prints the link, opens the browser and waits for **Done**, even when every row in scope already has labels. The page then shows its finished state. Notebooks written by agents rerun the labelling cell (for example after a test split is drawn: `gl.label(gold, taxonomy)` printed "100 labelled, 0 pending" and still opened a page in the examples the user supplied), so a user can be sent to a browser tab with nothing to do.
- The page already lets a person go back and relabel; that stays reachable.
- `serve()` (the lower-level call) already resumes at the first unlabelled row; it is not changed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Re-running the labelling cell does nothing when there is nothing to label (Priority: P1)

A user (or an agent working with them) runs `gl.label(gold, taxonomy)`, or re-runs the notebook from the top. Every row in scope is already labelled. No server starts, no browser opens, nothing blocks. One line says that all rows are labelled (how many, and which split), and the call returns the labelled rows, the same kind of result it returns after **Done**.

**Why this priority**: it is the whole request, and it makes the labelling cell safe to re-run, which removes one reason agents wrap it in guards.

**Independent Test**: build a gold file by hand with every row labelled, call `gl.label`, and check that no port was opened, no browser launch was attempted, a statement was printed, and the returned rows equal the labelled rows. Then add one pending row and check the server starts as before.

**Acceptance Scenarios**:

1. **Given** every row in the chosen split is labelled, **When** `gl.label` is called, **Then** it prints that all rows are labelled with the count and split, starts no server, opens no browser, and returns the labelled rows.
2. **Given** at least one row in scope is pending, **When** `gl.label` is called, **Then** it behaves exactly as today.
3. **Given** dev rows are all labelled and test rows are pending, **When** `gl.label(gold, taxonomy)` is called with no split, **Then** it starts the server (something is pending in scope); **When** called with `split="dev"`, **Then** it skips.
4. **Given** the gold file has no rows in the chosen split, **When** `gl.label` is called, **Then** it prints that there is nothing to label and to draw rows first, starts no server, and returns an empty set.
5. **Given** a split other than `dev`, `test` or none, **When** `gl.label` is called, **Then** it is refused as today.

---

### User Story 2 - I can still open the page on purpose to review or relabel (Priority: P1)

A user wants to go back over rows that are already labelled (to fix a label, or to look at what they decided). They pass one explicit option and the page opens as it does today, at the first row.

**Why this priority**: without it, skipping would remove a capability the page has today.

**Independent Test**: with all rows labelled, call `gl.label` with the option and check the server starts and the page can relabel a row.

**Acceptance Scenarios**:

1. **Given** every row is labelled, **When** the user passes the explicit option, **Then** the server starts and the link is printed, as today.
2. **Given** the option is passed and rows are pending, **Then** nothing differs from today.

---

### Edge Cases

- Labels whose names are no longer in the taxonomy (orphans) still produce today's notice, in the skip case too, because they are rows the user may want to review.
- Nothing about who may write a label changes: only the labelling server and `Gold.import_rows` write labels, and the skip path writes nothing.
- A second process holding the labelling lock: in the skip case no lock is taken, so there is nothing to wait for.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `gl.label` MUST count the pending rows in the chosen scope (`split`, or both) before starting anything.
- **FR-002**: When that count is zero and the explicit option is not given, `gl.label` MUST NOT start the server, open a browser or take the labelling lock, MUST print one statement that every row in scope is labelled (or that there are no rows to label), and MUST return the labelled rows of the scope as it does after **Done**.
- **FR-003**: When the count is above zero, `gl.label` MUST behave as today, including its output and its return value.
- **FR-004**: `gl.label` MUST accept one explicit keyword option, `force_open_ui`, that starts the page even when nothing is pending, defaulting to off.
- **FR-004a**: `gl.label` MUST NOT have a `block` parameter: it always waits until **Done** (or returns at once in the skip case) and always returns the labelled rows of the scope. A caller passing `block=` gets Python's normal unexpected-keyword error.
- **FR-005**: An invalid `split` MUST still raise the same error as today, before the count is made.
- **FR-006**: The README, the docstring, the agent skills that mention `gl.label` (`goldlabel-tune`, the `goldlabel` references and the walkthrough text), including removing the README sentence that describes `block=False` and its handle, and the Kiro steering file MUST describe the new behaviour and the option, and the existing drift tests MUST pass.
- **FR-007**: The gold rule text, `Gold`, `serve` (still available as `goldlabel._label.serve`, not exported, returning a handle) and the page MUST NOT change.

### Key Entities

- **Scope**: the rows in the chosen split (or all rows); **pending** means a row with no labels.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: With every row labelled, `gl.label` returns in under one second, opens 0 ports and 0 browser windows, and prints exactly one statement.
- **SC-002**: With one pending row, behaviour is unchanged, and the existing label-server tests pass unchanged except the three that used `block=False` (`test_label_page.py` twice, `test_gold_rule.py` once), which are updated as part of this change (confirmed by the user) to reach the server another way because the parameter is gone.
- **SC-003**: Calling `gl.label` a second time, with nothing drawn since the first call returned, never opens the labelling page.
- **SC-004**: Ruff, ty and pytest pass; the gold rule drift tests pass unchanged.

## Deliberately skipped

- Changing `gold.draw` (it does not start a server).
- A prompt asking the user whether to review; the option is explicit and off by default.
- Any change to the page, the token, the port or the labelling lock.
- A separate "review" function or mode on the page.
- A non-blocking mode for `gl.label`, removed at the user's request; code that needs a handle uses `goldlabel._label.serve`, which is not part of the public API.
- Making `draw` or evaluation safe to re-run (decided in spec 011: agents write no guard).

## Assumptions

- The option is called `force_open_ui` (`gl.label(gold, taxonomy, force_open_ui=True)`), the name the user chose.
- "Rows in scope" follows the existing `split` argument; no new scoping is added.
- Removing `block` is a breaking change to a public function. Confirmed by the user: the library is early and unstable, so there is no deprecation period and no warning release.
