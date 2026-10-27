"""Run every example and the walkthrough notebook; one summary line each.

Run from the repository root: `uv run --with pyarrow python -m e2e.run_all`

An example passes, fails or is skipped (no key, no gold file, a library not installed); skipped is
not a failure. Exit status 1 if any example fails or two examples report different scores.
"""

import re
import subprocess
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbclient.exceptions import CellExecutionError

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ["table", "postgres", "pgvector", "s3"]
NOTEBOOK = ROOT / "e2e" / "walkthrough" / "walkthrough.ipynb"


def parse(output: str) -> tuple[str, str, float | None]:
    """(status, text, score) from an example's output; its last RESULT: line decides."""
    lines = [x for x in output.splitlines() if x.startswith("RESULT: ")]
    score = re.findall(r"^score=([0-9.]+)$", output, flags=re.MULTILINE)
    if not lines:
        return "fail", "no RESULT line (the run was cut short)", None
    status, _, text = lines[-1].removeprefix("RESULT: ").partition(" - ")
    return status, text, float(score[-1]) if score else None


def overall(results: dict[str, tuple[str, str, float | None]]) -> str:
    statuses = {status for status, _, _ in results.values()}
    scores = {score for _, _, score in results.values() if score is not None}
    if "fail" in statuses or len(scores) > 1:
        return "fail"
    return "skipped" if "skipped" in statuses else "pass"


def run_notebook() -> tuple[str, str, float | None]:
    nb = nbformat.read(NOTEBOOK, as_version=4)
    client = NotebookClient(
        nb,
        timeout=900,
        kernel_name="python3",
        resources={"metadata": {"path": str(NOTEBOOK.parent)}},
    )
    try:
        client.execute()  # the notebook on disk keeps no outputs
    except CellExecutionError as e:
        last = str(e).strip().splitlines()[-1]
        # a cell raises RuntimeError("SKIPPED: ...") for a missing key or gold file
        if "SKIPPED:" in last:
            return "skipped", last.split("SKIPPED:", 1)[1].strip(), None
        return "fail", last, None
    return "pass", "", None


def main() -> int:
    results = {}
    for name in EXAMPLES:
        done = subprocess.run(
            [sys.executable, "-m", f"e2e.{name}.run"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        results[name] = parse(done.stdout)
        if results[name][0] == "fail":
            print(
                f"--- {name}: last output\n" + "\n".join(done.stdout.splitlines()[-15:])
            )
            print(done.stderr[-1500:], end="")
    results["walkthrough"] = run_notebook()
    for name, (status, text, _) in results.items():
        print(f"{name}: RESULT: {status}" + (f" - {text}" if text else ""))
    scores = {score for _, _, score in results.values() if score is not None}
    if len(scores) > 1:
        print(f"the examples reported different scores: {sorted(scores)}")
    verdict = overall(results)
    print(f"all: {verdict}")
    return 1 if verdict == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
