# Quickstart: validating 015

Automated checks run with `uv run pytest`; section 3 needs a person.

## 1. Setup

```bash
scripts/dev-setup.sh
uv run ruff check && uv run ruff format --check && uv run ty check && uv run pytest
```

## 2. Automated (tests build gold files by hand and drive the server over loopback HTTP)

| Scenario | Spec |
|---|---|
| `Gold` reads and writes the JSON document; `_write` keeps the taxonomy; a 014 `.jsonl` file is not a dataset | FR-026 |
| A revision adds one `revisions` entry with the previous labels, note and `labelled_by`; a first label, and an unchanged save, add none; two revisions give two entries | FR-016, FR-017, Story 5 |
| Datasets and samples list with counts; a bad file lists as an error and the others still list | FR-009 |
| Open a row by id; unknown id 404; revise through `/api/label` | FR-010, FR-013 |
| Passes: pending rows only, `force` every row, Back, Skip, counts for the pass; two passes at once | FR-012 |
| Lock written after bind; stale lock (dead pid, closed port, garbage) replaced; live lock makes `gl.label` print the URL, create a pass and return when pending is 0 or Done is posted | FR-005 to FR-007, Story 2 |
| `gl.label` writes the taxonomy; a different one replaces it; rows untouched | FR-008 |
| Host check; non-GET without `X-Goldlabel` is 403; no token in the page | FR-027 |
| `clf.evaluate` logs disagreements; the evaluation view joins text, marks revised and missing rows; STALE after a later revision only, not after a first label or another sample | FR-019 to FR-021 |
| `goldlabel label` start, join, unknown name, empty folder, port in use, `--dir` | FR-001 to FR-004 |
| Served page and CSS carry the `lg:` scroll classes and `tabindex` | FR-023 |
| Gold-rule, skills and docs drift tests pass with the new names | SC-006 |

## 3. By a person

1. `uv run goldlabel label` in a folder with two datasets; open one, jump to a row by id, change its label and note, use the browser Back, jump to another row. Check `gold.json`: the row holds a `revisions` entry with the old values.
2. Run `gl.label(dev, taxonomy)` in a notebook while step 1's page is open: it prints the page URL, waits, returns when you label the last pending row or press **Done**.
3. Run an evaluation, revise a row it got wrong, reload the sample page: the evaluation shows STALE and names the row.
4. At 1280px with a 40-label taxonomy, scroll the label list to the end while the text stays on screen; at 390px the page is one column. Light and dark. Keyboard only. Real browser, not Playwright in the repo.
5. The gold-rule refusal trial with the updated skills.
