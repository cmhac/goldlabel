# Tasks: Open the labelling page only when rows are pending, and always wait for it

**Input**: [spec.md](spec.md), [plan.md](plan.md). One commit per task: `012/TNN: ...`. Do 012 before 011 (the skills text mentions the new behaviour).

## Phase 1: User Stories 1 and 2 (P1), one change

- [ ] T001 [US1] [US2] Write the failing tests in `tests/test_label_page.py` (skip when all labelled: no `serve`, no browser, one line, returns labelled rows; pending row serves; dev labelled/test pending with `split=None` serves and `split="dev"` skips; empty scope message and empty set; `force_open_ui=True` serves; `block=` raises `TypeError`; bad split raises `GoldError`), using a fake `webbrowser.open` that presses Done via `POST /api/done`; change the three tests that used `block=False` (`tests/test_label_page.py` x2, `tests/test_gold_rule.py` x1) to use that fake. Run: the new tests fail.
- [ ] T002 [US1] [US2] Change `label()` in `src/goldlabel/_label.py` as in plan.md: validate `split`, count pending in scope, skip with one printed line and the labelled rows unless `force_open_ui`, delete the `block` parameter and branch, update the docstring. Run `tests/test_label_page.py tests/test_gold_rule.py tests/test_label_server.py tests/test_e2e.py -n0`: green.
- [ ] T003 [US1] [US2] Update the text: README "The labelling page" paragraph (remove the `block=False` sentence, add the skip and `force_open_ui`), any skill or reference or steering line that describes `gl.label` opening the page (`grep -rn "gl.label\|block=" README.md src/goldlabel/skills .kiro`). Run `tests/test_skills.py tests/test_docs.py -n0`: green.

## Phase 2: Close

- [ ] T004 Run ruff, ty and the whole suite; run `/ponytail-review` on the diff; record in `spec.md` Status and the AGENTS.md "Current state" paragraph; list the human check (quickstart step 2) as still to do.

## Dependencies

T001 -> T002 -> T003 -> T004. No parallel work (one function, one README).
