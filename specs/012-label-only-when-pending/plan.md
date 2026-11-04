# Implementation Plan: Open the labelling page only when rows are pending, and always wait for it

**Branch**: `claude/sharp-galileo-vi4k0k` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

In `src/goldlabel/_label.py`, `label()` counts the pending rows in its scope before starting anything. If there are none and `force_open_ui` is not true it prints one line and returns the labelled rows; otherwise it runs exactly as today. The `block` parameter is deleted (the blocking path becomes the only path). Three tests that used `block=False` and the README sentence about it are updated.

## Technical Context

**Language/Version**: Python 3.12. **Dependencies**: none new. **Testing**: pytest (`tests/test_label_page.py`, `tests/test_gold_rule.py`, `tests/test_e2e.py`). **Project Type**: library. **Scope**: one function, three tests, README/skills text.

## Constitution Check

- **I Gold Rule**: the skip path writes nothing; no way to set a label is added; `serve`, `Gold` and the page are unchanged. Pass.
- **II Ponytail** (skill applied): no helper, no new class; the count is one expression over rows `label()` already reads; the one new keyword is the one the user asked for. Pass.
- **IV Test-first**: new tests fail first. Expected values are written by hand. No real browser or port in the skip tests: `webbrowser.open` and `serve` are monkeypatched to fail if called. Pass.
- **VII Notebooks**: result objects and the sync form unchanged. Pass.

## Design

```python
def label(gold, taxonomy, *, split=None, force_open_ui=False, open_browser=True, port=None):
    if split is not None and split not in SPLITS:   # same error serve() raises, before the count
        raise GoldError(...)
    scope = [r for r in gold._read() if split in (None, r.split)]
    if not force_open_ui and all(r.labels for r in scope):
        print(...)            # "all N rows are labelled" or "no rows to label; draw some first"
        return GoldSet(rows with labels, split or "all", gold.path)
    ...                       # today's body, with the block branch removed
```

- "Pending" is `not r.labels`, the library's existing definition (`Gold.pending`, `Handle._after`).
- The orphan notice stays and is printed in both paths (a labelled row with a label no longer in the taxonomy is something to review).
- `if not block: return handle` and the `block` parameter and docstring text are removed. `serve()` is untouched and still used by tests that need a handle.
- The skip message is one line and does not repeat the gold rule (the rule is printed when the page opens).

## Tests

- New (written first, red): all rows labelled -> no `serve` call, no browser call, one printed line, returns the labelled rows; a pending row -> server runs (existing behaviour); dev labelled + test pending -> `split=None` serves, `split="dev"` skips; empty scope -> "nothing to label" message and an empty set; `force_open_ui=True` with all labelled -> server starts; `block=` -> `TypeError`; bad split -> `GoldError` as before.
- Changed (3): the tests that used `block=False` to get a handle now make `webbrowser.open` a fake that presses Done (`POST /api/done`) from the URL it is given, so `label()` runs to completion without a thread: handle test -> asserts the page answered and returned rows; orphan test -> the printed notice; the gold-rule test -> `SHORT in output`.

## Project Structure

```text
specs/012-label-only-when-pending/{spec.md,plan.md,quickstart.md,tasks.md}
src/goldlabel/_label.py          # label()
tests/test_label_page.py  tests/test_gold_rule.py   # new and changed tests
README.md  src/goldlabel/skills/goldlabel-tune/SKILL.md  references  .kiro/steering/goldlabel.md   # text if they name block or the page opening
```

## Complexity Tracking

No violations.
