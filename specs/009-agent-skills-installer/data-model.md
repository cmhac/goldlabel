# Data model: 009

No database. Four small shapes.

## Harness target (a literal dict in `cli.py`)

| Field | Meaning |
|---|---|
| name | `claude`, `codex`, `copilot`, `kiro` |
| project folder | skills folder under the current directory (research R1) |
| user folder | skills folder under the home directory |
| steering | Kiro only: the folder for `goldlabel.md` (project `.kiro/steering`, user `~/.kiro/steering`) |

`codex` and `copilot` resolve to the same folder; targets are deduplicated by resolved path.

## Install result (printed, never stored)

One line per (folder, skill): `written`, `up to date`, `would write` (`--dry-run`), or `differs`
(refused without `--force`), then the agent's next step. Nothing is recorded on disk.

## Gold row (changed field only)

`split`: `"test"` -> `"dev"` for labelled test rows by `Gold.fold_test()`. `id`, `text`, `labels`,
`labelled_by`, `labelled_at` are untouched; a test compares the rows before and after.

## Eval log fold record

A line in `evals.jsonl`: `{"event": "test_folded", "time": ISO-8601 UTC, "rows": n}`. Evaluation
lines have no `event` key. `EvalLog.rows` keeps only evaluation lines; `EvalLog.folds` holds the
events. Rule: the fold needs at least one test-split evaluation line after the latest fold line, and
no pending test row.
