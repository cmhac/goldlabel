# Implementation Plan: Overhaul the labelling page

**Branch**: `claude/eloquent-brown-ngl7t1` | **Date**: 2026-11-04 | **Spec**: [spec.md](spec.md)

## Summary

Two small server-side changes carry notes (`GoldRow.note`, an optional `note` on `POST /api/label` and in the state). Everything else is the page: `web/index.html` and `web/app.js` are rewritten for the split layout, auto-advance in `single` mode, the key map and the note field, and `web/app.css` is rebuilt with the Tailwind CLI. README, one skill sentence and the AGENTS.md "Current state" are updated. No new file in `src/`, no new dependency, no new route.

## Technical Context

**Language/Version**: Python 3.12 for the server and tests; vanilla JavaScript and Tailwind v4.3.3 (pre-built CSS) for the page. **Dependencies**: none new. **Testing**: pytest over HTTP and over the served files as text (`tests/test_label_server.py`, `tests/test_label_page.py`, `tests/test_gold.py`, `tests/test_evaluation.py`); no browser in the tests. **Project Type**: library with a local web page. **Scope**: `gold.py` (1 field), `_label.py` (about 10 lines), `web/*`, tests, docs text.

## Constitution Check

- **I Gold Rule**: a note is written only by `Handle.label`, which a person's `POST /api/label` calls, and by `import_rows` as an imported row's own key; no function sets a note or a label for a caller, no model output reaches either. `gold_rule.md`, `GOLD_RULE_*` and the drift tests are untouched. The new tests drive the HTTP API the way the existing simulated human does. Pass.
- **II Ponytail** (skill invoked before the spec and again for this plan): reuses `Handle.label`, `GoldRow`'s `extra`/`dump` pattern, the page's `el()` and `call()` helpers and Tailwind as it is; no new module, helper class, option or dependency; the mock-up's shortcuts dialog, theme toggle and toast timer are cut (spec "Deliberately skipped"). Pass.
- **III Spec Kit**: spec, plan, tasks in `specs/013-labelling-page-overhaul/`; `/ponytail-review` runs on all three before implementing and on the diff after, with `/ponytail-debt`. Pass.
- **IV Test-first**: every server and file-format behaviour gets a failing test first with hand-written expected values; page behaviour that only a browser could run is asserted on the served text and checked ad hoc in a browser by the developer (not a test, not a dependency). The classifier-sees-no-note test counts `FunctionModel` calls and inspects the prompt. Pass.
- **V No hidden state**: the note lives in the gold file next to the label; the page keeps only the draft in memory. Pass.
- **VII Notebooks**: `gl.label` and its signature are unchanged. `GoldSet.to_polars()`/`to_pandas()` gain the column through `model_dump`, together. Pass.

## Design

### Server and file (`gold.py`, `_label.py`)

```python
class GoldRow(BaseModel):
    ...
    note: str | None = None          # a person's comment on the row; written by the labelling page

    def dump(self):                  # existing loop gains "note"
        for key in ("labelled_by", "labelled_at", "note"):
```

`Handle.label(id_, labels, note: str | None = None)`: the stamp already holds `labels`, `labelled_by`, `labelled_at`; `note=None` leaves the row's note alone (an older client), a string is trimmed and stored, `""` after trimming clears it (stored as `None`, which `dump` drops). In `do_POST`, `note = body.get("note")`; if the key is present and not a `str` -> 400 `send {id: str, labels: [str], note?: str}`. `_state()["item"]` gains `"note": row.note`. No sentinel and no new type.

### The page (`web/*`)

- `index.html`: the same shell; `<main>` widens to `max-w-6xl`.
- `app.js` keeps its structure (state, `call`, `render` that rebuilds the DOM, one `keydown` listener) with these changes:
  - `render()` lays out a header, a status line (`role="status"`), and a `lg:grid` of two children: the text card (left) and the panel (right, `lg:sticky lg:top-4`), then the counts. Below `lg` it is one column in the same order.
  - Key presses with `e.repeat` set are ignored (a held-down number key would otherwise label every following row). `choose(name)`: in `single` mode sets `selected = [name]` and calls `save()`; in `multi` mode toggles as today. `save()` posts `{id, labels, note}`; a `busy` flag set around `call` makes a second key press during the request a no-op (the edge case). `call` returns whether it succeeded, so `save` can set the status line (`Saved row <id> as <labels>. Press ← to go back.`) only on success.
  - The note is a `<textarea>` with a `<label>`; its value lives in a module variable `note` (reset when the item changes, restored from `state.item.note`), updated on `input`, so a re-render never loses a draft.
  - Under the note field, one small line says a note is saved with the label and is not kept if the row is skipped (US4 scenario 7).
  - Panel buttons: **← Back**, **Skip S**, and in `multi` mode **Save and next Enter** (disabled with no label chosen). No Save button in `single` mode. A legend line lists the keys.
  - Key handler: when the note has focus, only Esc (blur) and Ctrl/⌘+Enter (save if a label is chosen) act and everything else is left to the browser, so typing and arrows edit text. When it does not: digits (choose), ←, S, N (focus the note, `preventDefault` so no "n" is typed), Enter and → (save in `multi` mode; in `single` mode they save only when the row already has labels, i.e. after going back, so Enter re-confirms it). The existing Ctrl/Meta/Alt guard stays for the non-note case.
  - A hint (`Typing a note: number keys are paused. Esc returns to the labels.`) replaces the idle status line while the note has focus (via `focus`/`blur` listeners that set a flag and re-render only that line).
  - Selected state: heavier border, tinted background, and a "✓" mark that screen readers skip (`aria-hidden`) next to `aria-pressed`; options are `<button aria-pressed>` inside a `fieldset`, as the mock-up, so Tab and Space/Enter work for labels with no number key.
  - Untrusted text only through `textContent` (the existing `el()`).
- `app.css`: rebuilt with the Tailwind standalone CLI v4.3.3 exactly as `web/README.md` describes (download to the scratchpad, not the repo). If the CLI cannot be downloaded the change stops there and says so; no hand-edited CSS.

### Tests (all in the existing files)

- `tests/test_notebook.py` (line 388): the exact gold column list gains `"note"`.
- `test_gold.py`: a row with a `note` round-trips through `_write`/`_read`; a row without one writes no `note` key; the pre-006 fixtures still load; `import_rows` keeps a `note` key as given; `to_polars()` has a `note` column.
- `test_label_server.py`: label with a note stores it trimmed and the state carries it; empty/whitespace clears it; absent keeps it; `note: 5` -> 400 and the file is unchanged; the labelled row still has `labelled_by: "goldlabel-ui"`.
- `test_evaluation.py`: a guard test, green from the start because the classifier already receives only `id` and `text`: a gold row with a `note` yields the same prompt text as without (the `FunctionModel` receives no note). It stays to keep it that way.
- `test_label_page.py`: text assertions on the served files for the contract (the five routes only, no `predict`, the `lg:` two-column classes, a `role="status"` element, a `<textarea>`/`label` for the note, key handling for `n`, `s`, `Escape`, Ctrl/Meta+Enter and `repeat`, `aria-pressed`, no external URL); the existing tests that pin the old page are updated in the same task. The CSS test for `prefers-color-scheme` and the 'no class-based dark' test stay as they are.

### Developer check (not a test)

After the CSS build: run the real server on a tiny hand-built gold file and drive it with the preinstalled Chromium through an ad-hoc Playwright script kept in the scratchpad (never committed, never a dependency): screenshots at 1280 and 390 px in light and dark, and a key-only session (number keys, N, type, Esc, S, ←, Ctrl+Enter, Done). This is reported as a developer check; the human browser look stays in AGENTS.md's list.

## Project Structure

```text
specs/013-labelling-page-overhaul/{spec.md,plan.md,quickstart.md,tasks.md,checklists/requirements.md}
src/goldlabel/gold.py                      # GoldRow.note, dump
src/goldlabel/_label.py                    # label(note), POST /api/label, state
src/goldlabel/web/{index.html,app.js,app.css}   # the page (app.css generated)
src/goldlabel/web/README.md                # only if the build command changes
tests/test_gold.py  test_label_server.py  test_label_page.py  test_evaluation.py
README.md  src/goldlabel/skills/goldlabel-tune/SKILL.md   # page keys and the note
AGENTS.md                                  # Current state, human checks
```

## Complexity Tracking

No violations. No new dependency (Tailwind is a build tool, run from the scratchpad, as `web/README.md` already says).
