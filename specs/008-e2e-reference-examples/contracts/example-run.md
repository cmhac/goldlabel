# Contract: running an example

The interface of this feature is a command line, not a Python API. Nothing is added to
`hunches.__all__`.

## Commands

Run from the repository root after `uv sync --all-extras`:

| Example | Command | Needs |
|---|---|---|
| table | `uv run --with pyarrow python -m e2e.table.run` | Python; a key for the first classification |
| postgres | `uv run python -m e2e.postgres.run` | `podman`; a key for the first classification |
| pgvector | `uv run python -m e2e.pgvector.run` | `podman`; a key for the first classification |
| s3 | `uv run python -m e2e.s3.run` | `podman`; a key for the first classification |
| walkthrough | open `e2e/walkthrough/walkthrough.ipynb`; `run_all` runs it headlessly | a key for the first run |
| all | `uv run --with pyarrow python -m e2e.run_all` | everything above |

The key is `ANTHROPIC_API_KEY` in the environment. Nothing reads a `.env` file.

## Output and exit status

- Progress is plain text on stdout.
- The **last line** is `RESULT: pass`, `RESULT: fail - <check name>: expected <a>, got <b>`, or
  `RESULT: skipped - <reason>`.
- Exit status `0` for pass and skipped, `1` for fail (a failed check, a refused call that should
  not have been refused, an unexpected exception).
- A missing `podman`, a busy port, a failed image pull and a readiness timeout are **fail** with a
  message naming the cause (and the container's last 20 log lines for a timeout). A missing key
  with nothing cached is **skipped** after the candidate checks have passed.
- `run_all` prints one line per example (`<name>: <RESULT line>`), then `all: pass|fail|skipped`,
  and exits `1` if any example failed. It also fails if two examples printed different evaluation
  scores. Each example prints `score=<value>` before its RESULT line for this.

## Guarantees

- No tracked or unignored file in the repository changes (working files go to a temporary folder;
  the cache is the ignored `e2e/.cache/`).
- No container from the run remains, whether it passed, failed or was interrupted.
- The gold file is copied byte for byte and its provenance (`GOLD.md`) is printed.
- The estimate (items, cached, live calls, price) is printed before the first live model call, and
  every classification runs with a `max_cost`; an unknown price refuses the run.
- The test split is evaluated only by the walkthrough, once, at the end.
