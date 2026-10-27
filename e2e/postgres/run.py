"""Postgres without embeddings: the whole corpus, keywords and server-side filtering, with the text
in one table and in two tables, and the result size limit.

Run from the repository root: `uv run python -m e2e.postgres.run` (needs podman).
"""

import os
import tempfile
from pathlib import Path

import psycopg

import hunches as hn
from e2e.common.support import (
    Failed,
    check,
    classify_and_evaluate,
    container,
    corpus_rows,
    expected,
    hits,
    run,
    say,
)

IMAGE = "docker.io/library/postgres:16"  # podman needs the full registry name
URL = "postgresql://postgres:e2e@127.0.0.1:{port}/postgres"


def ready(port: int) -> None:
    psycopg.connect(URL.format(port=port), connect_timeout=2).close()


def load(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        # one table: id and text together
        conn.execute("CREATE TABLE corpus (id text PRIMARY KEY, text text NOT NULL)")
        # two tables: an item table and a separate table holding the text
        conn.execute("CREATE TABLE items (id text PRIMARY KEY)")
        conn.execute("CREATE TABLE texts (id text PRIMARY KEY, text text NOT NULL)")
        # 20,000 filler rows (about 5 MB as the library sizes a result) for the size limit
        conn.execute("CREATE TABLE big (id text PRIMARY KEY, text text NOT NULL)")
        for r in corpus_rows():
            conn.execute("INSERT INTO corpus VALUES (%s, %s)", (r["id"], r["text"]))
            conn.execute("INSERT INTO items VALUES (%s)", (r["id"],))
            conn.execute("INSERT INTO texts VALUES (%s, %s)", (r["id"], r["text"]))
        conn.execute(
            "INSERT INTO big SELECT 'f' || g, repeat('filler text ', 10) "
            "FROM generate_series(1, 20000) g"
        )
        conn.execute(
            "UPDATE big SET text = 'one needle in the haystack' WHERE id = 'f7'"
        )
        for table in ("corpus", "items", "texts", "big"):
            conn.execute(
                f"ANALYZE {table}"
            )  # the size guard reads the planner statistics


def main() -> str | None:
    want = expected()
    with container(
        "postgres", IMAGE, 5432, {"POSTGRES_PASSWORD": "e2e"}, ready
    ) as port:
        # the URL lives in this process's environment only, never in a file
        os.environ["HUNCHES_PG_URL"] = URL.format(port=port)
        load(os.environ["HUNCHES_PG_URL"])
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            hn.settings.root = tmp
            layouts = {
                "one table": hn.PgCorpus(table="corpus"),
                "two tables": hn.PgCorpus(table="items", text_table="texts"),
            }
            for layout, corpus in layouts.items():
                got = hn.get_candidates(corpus, out=False)
                check(
                    f"whole corpus, {layout}",
                    [r["id"] for r in got.rows],
                    want["whole"],
                )
                for key, entry in want["keywords"].items():
                    # server_side=False reads every row and matches in Python; True lets the
                    # database filter first. Terms with % _ and a backslash are escaped for LIKE.
                    for server_side in (False, True):
                        got = hn.get_candidates(
                            corpus,
                            keywords=entry["terms"],
                            regex=entry["regex"],
                            server_side=server_side,
                            out=False,
                        )
                        check(
                            f"keywords {key}, {layout}, server_side={server_side}",
                            hits(got),
                            entry["hits"],
                        )
                entry = want["keywords"]["laid_off_or_redundancy"]
                got = hn.get_candidates(
                    corpus, keywords=entry["terms"], limit=5, out=False
                )
                check(f"keywords limit 5, {layout}", hits(got), entry["limit5"])

            # The size limit: 1 MB for a 20,000 row table is refused before any row is read.
            big = hn.PgCorpus(table="big", max_result_mb=1)
            try:
                hn.get_candidates(big, out=False)
            except RuntimeError as e:
                check(
                    "the whole big table is refused",
                    "result limit of 1 MB" in str(e),
                    True,
                )
            else:
                raise Failed("the whole big table was not refused")
            got = hn.get_candidates(big, limit=10, out=False)
            check("a limit gets past the size limit", len(got.rows), 10)
            got = hn.get_candidates(
                big, keywords=["needle"], server_side=True, out=False
            )
            check(
                "a server-side keyword filter gets past it",
                [r["id"] for r in got.rows],
                ["f7"],
            )

            say("classify the whole corpus read from Postgres")
            candidates = hn.get_candidates(layouts["one table"], out=False)
            return classify_and_evaluate(candidates, tmp)


if __name__ == "__main__":
    run(main)
