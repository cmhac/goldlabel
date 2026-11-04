# Tasks: Overhaul the labelling page

**Input**: [spec.md](spec.md), [plan.md](plan.md), [quickstart.md](quickstart.md). One commit per task: `013/TNN: ...`. T000 is the specs commit.

## Phase 1: Notes in the file and the server (User Story 4)

- [X] T001 [US4] Write the failing tests: `tests/test_gold.py` (a row with `note` round-trips; no `note` key when unset; the pre-006 fixtures load; `import_rows` keeps a `note` key; `to_polars()` has a `note` column), `tests/test_label_server.py` (label with a note stores it trimmed and the state item carries `note`; whitespace clears it; no `note` key keeps it; `note: 5` returns 400 and leaves the file unchanged; `labelled_by` is still `goldlabel-ui`), `tests/test_evaluation.py` (a guard test, green from the start: a gold row with a `note` gives the model the same prompt text as one without), and update the exact gold column list in `tests/test_notebook.py` (line 388) to include `"note"`. Watch the new tests, except the guard, fail for the right reason. Then add `GoldRow.note` and `dump`, `Handle.label(..., note=...)`, the `note` validation in `do_POST` and `"note"` in `_state()` item. Run `tests/test_gold.py tests/test_label_server.py tests/test_evaluation.py tests/test_notebook.py tests/test_gold_rule.py -n0`: green.

## Phase 2: The page (User Stories 1, 2, 3 and 5)

- [X] T002 [US1] [US2] [US3] [US5] Update `tests/test_label_page.py` first (red): the served `app.js`/`index.html` contain the two-column `lg:` layout, a `role="status"` element, a labelled `<textarea>` for the note, `aria-pressed` options in a `fieldset`, key handling for `n`, `s`, `Escape`, Ctrl/Meta+Enter and `repeat`, a `note` in the label request, and the five existing routes only (what only a browser can show, such as auto-advance, a held-down key and typing in the note, is covered by the developer check below and reported as such); keep the no-external-URL, no-theme-toggle, no-prediction and token tests. Then rewrite `src/goldlabel/web/index.html` and `app.js` as in plan.md, download the Tailwind v4.3.3 standalone CLI to the scratchpad and rebuild `app.css` as `web/README.md` says. Run `tests/test_label_page.py tests/test_label_server.py tests/test_e2e.py -n0`: green. Then the developer check in plan.md (screenshots at 1280 and 390 px, light and dark, and the key-only session) and fix what it shows.

## Phase 3: Text and close

- [X] T003 Update the text: README "The labelling page" (layout, auto-advance, the keys, the note, where it is stored), `src/goldlabel/skills/goldlabel-tune/SKILL.md` (one sentence: rows may carry a person's `note`, read it when reading disagreements, never write one), and `grep -rn "Enter to move on\|number keys" README.md src/goldlabel/skills .kiro docs` for other old key text. Run `tests/test_skills.py tests/test_docs.py tests/test_gold_rule.py -n0`: green.
- [X] T004 Run `uv run ruff check`, `uv run ruff format --check`, `uv run ty check`, `uv run pytest`; run `/ponytail-review` on the diff and `/ponytail-debt`; set `spec.md` Status, update the AGENTS.md "Current state" paragraph (013 implemented; human checks: the page in a real browser at both widths, now including keyboard use and notes). Fix findings.

## Dependencies

T001 -> T002 -> T003 -> T004. No parallel work: T002 reads T001's state field, T003 describes T002's keys.
