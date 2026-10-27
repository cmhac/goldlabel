"""Every way to load local data into hunches, then candidates, classification and evaluation.

Run from the repository root: `uv run --with pyarrow python -m e2e.table.run`
"""

import csv
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

import polars as pl

import hunches as hn
from e2e.common.support import (
    COMMON,
    EMBEDDING_MODEL,
    StandIn,
    check,
    classify_and_evaluate,
    corpus_rows,
    expected,
    found,
    hits,
    run,
    seeds,
)


def main() -> str | None:
    rows, want = corpus_rows(), expected()
    skipped = []
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder)
        hn.settings.root = tmp  # nothing below writes outside the temporary folder

        # 1. One corpus, every supported form. A CSV holds text only (no vectors).
        with open(tmp / "corpus.csv", "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["id", "text"])
            writer.writeheader()
            writer.writerows({"id": r["id"], "text": r["text"]} for r in rows)
        shutil.copyfile(COMMON / "corpus.jsonl", tmp / "corpus.jsonl")
        pl.DataFrame(rows).write_parquet(tmp / "corpus.parquet")
        forms = {
            "csv": tmp / "corpus.csv",
            "jsonl": tmp / "corpus.jsonl",
            "parquet (read by polars)": tmp / "corpus.parquet",
            "polars DataFrame": pl.DataFrame(rows),
            "list of rows": rows,
        }
        try:
            import pandas as pd

            forms["pandas DataFrame"] = pd.read_parquet(tmp / "corpus.parquet")
        except ImportError:
            skipped.append("pandas could not read Parquet (pip install pyarrow)")
        for name, source in forms.items():
            got = hn.get_candidates(hn.Table(source, id_column="id"), out=False)
            check(
                f"whole corpus from {name}", [r["id"] for r in got.rows], want["whole"]
            )
        # Parquet through pandas: hide polars, as in an environment that only has pandas
        with mock.patch.dict(sys.modules, {"polars": None}):
            try:
                table = hn.Table(tmp / "corpus.parquet", id_column="id")
                got = hn.get_candidates(table, out=False)
                check("whole corpus from parquet (read by pandas)", len(got.rows), 60)
            except ImportError:
                skipped.append(
                    "Parquet through pandas needs pyarrow (pip install pyarrow)"
                )

        # 2. Keywords and regular expressions on a file and on a DataFrame: same hits, same order
        for name in ("csv", "polars DataFrame"):
            table = hn.Table(forms[name], id_column="id")
            for key, entry in want["keywords"].items():
                got = hn.get_candidates(
                    table, keywords=entry["terms"], regex=entry["regex"], out=False
                )
                check(f"keywords {key} on {name}", hits(got), entry["hits"])
                got = hn.get_candidates(
                    table,
                    keywords=entry["terms"],
                    regex=entry["regex"],
                    limit=5,
                    out=False,
                )
                check(f"keywords {key} limit 5 on {name}", hits(got), entry["limit5"])

        # 3. Seed phrases need vectors: JSONL, Parquet and a DataFrame carry them, a CSV cannot
        for name in ("jsonl", "parquet (read by polars)", "polars DataFrame"):
            table = hn.Table(
                forms[name],
                id_column="id",
                vector_column="embedding",
                embedding_model=EMBEDDING_MODEL,
            )
            got = hn.get_candidates(
                table,
                seeds=list(seeds()),
                embedder=StandIn(),
                floor=want["seeds"]["floor"],
                out=False,
                cache=False,
            )
            check(f"seed search on {name}", found(got), want["seeds"]["hits"])
            check(f"bands on {name}", got.bands(), want["seeds"]["band_counts"])
        try:
            hn.Table(tmp / "corpus.csv", vector_column="embedding")
        except ValueError as e:
            check("a CSV with a vector column is refused", "CSV" in str(e), True)
        else:
            check("a CSV with a vector column is refused", "no error", "ValueError")

        # 4. The whole corpus, classified, then the dev split scored against the people's labels
        candidates = hn.get_candidates(
            hn.Table(forms["csv"], id_column="id"), out=False
        )
        reason = classify_and_evaluate(candidates, tmp)
        if reason:
            skipped.append(reason)
    return "; ".join(skipped) or None


if __name__ == "__main__":
    run(main)
