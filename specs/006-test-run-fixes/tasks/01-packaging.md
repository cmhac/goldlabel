# 01 — Packaging: backends in the base install, `local` stays an extra

Spec: item 2, Q2.

**Do**
- `pyproject.toml`: add `boto3` and `psycopg[binary]` to `dependencies`; delete the `s3`, `pg`, `rds` extras and keep `local`; rewrite the comment above `dependencies`. Look at how the dev group handles `boto3`/`psycopg` today and remove duplicates. `uv lock`, commit `uv.lock`.
- Verify and report: `sentence-transformers` is gated by `python_version < '3.14'` in `pydantic-ai-slim`'s metadata (`Provides-Extra: sentence-transformers`); a lock/sync on Python 3.12 installs it; `requires-python` stays `>=3.12`. Measure and report the fresh `uv sync` time and the installed size of `.venv` before and after (PyTorch and, on Linux, its CUDA wheels may add gigabytes). If the growth is above about 2 GB, **stop and tell Chris with the numbers** before committing, since CI time, cache size and `uv tool install hunches` all grow; do not add index overrides or CPU-only wheels on your own.
- `search.py`: the four `except ImportError … raise ImportError("… pip install hunches[…]")` blocks (around lines 73, 141, 183, 533) go. Keep the imports lazy inside the functions (startup stays fast and the fake `psycopg`/`boto3` in tests still work) but as plain imports.
- Docs that name extras: `README.md` (Install lines 10–14, the RDS/Aurora paragraph around line 127: "install `hunches[rds]`" becomes "set `pg_auth = "rds_iam"`…"), `AGENTS.md` (Stack: drop "optional extras …"; Commands: `uv sync --all-extras` → `uv sync --extra local`), `.github/workflows/ci.yml` and `publish.yml` (`uv sync --all-extras` → `uv sync --extra local`, including the optional pgvector job). README says `hunches[local]` is large (about 5.5 GB measured) and unavailable on Python 3.14. (Measured: folding it in was 240 MB to 5.7 GB, so Chris kept it an extra.) Leave `specs/005-pgvector` as written (history).

**Tests (red first)**
- New `tests/test_packaging.py`: parse `pyproject.toml` with `tomllib`; assert no `optional-dependencies`, `boto3` and `psycopg[binary]` appear in `dependencies`, and the `pydantic-ai-slim` entry includes `sentence-transformers`.
- Delete the two tests that assert the old ImportError text (`tests/test_search_pg_connect.py` around lines 116 and 247) and the S3 one in `tests/test_search.py` if present; say which you removed.
- `uv run python -c "import boto3, psycopg"` after a plain `uv sync` (no extras) succeeds. Report the output.

**Not in this task**: any behaviour change.
