# Quickstart: check the overhauled labelling page

## 1. Automated

```bash
uv run pytest tests/test_gold.py tests/test_label_server.py tests/test_label_page.py tests/test_evaluation.py tests/test_gold_rule.py tests/test_skills.py tests/test_docs.py -n0
```

## 2. By hand (a person, in a real browser; agents report this and stop)

Make a tiny gold file of a few pending rows by hand (a fixture, not labels), then run `gl.label(gold, taxonomy)`.

1. Window at 1280px: text on the left, labels, note, Back and Skip on the right. Shrink below 1024px: one column, text first, no sideways scrolling. Do it in light and dark.
2. `single` mode: press `1`. The row saves, the next row shows, the status line names the saved row. Press `←`: the row comes back with its label ticked; press `2`: it saves again and moves on.
3. Press `N`, type `two policies in one sentence` (digits and arrows type, nothing is labelled), press `Esc`, then `1`: the row saves with the note. Go back with `←`: the note is there. Open the gold file: the row has `note`.
4. Press `S`: the row is skipped and nothing is written. Press `Ctrl+Enter` in the note after going back to a labelled row: it saves the edited note.
5. `multi` mode: `2` and `3` toggle, nothing is saved; `Enter` (or **Save and next**) saves both labels.
6. Label the last row: the "All rows are labelled" state shows; **Done** ends the session.
7. Tab through the page: every control is reachable, the focus ring is visible.

## 3. Developer check (done in T002, reported, not a repository test)

Screenshots with the preinstalled Chromium at 1280px and 390px, light and dark, and a key-only session against the real server. Output goes to the scratchpad.
