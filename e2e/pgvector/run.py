"""Postgres with pgvector: seed-phrase search in exact and in index (HNSW) mode.

Run from the repository root: `uv run python -m e2e.pgvector.run` (needs podman).
"""

import os
import tempfile
from pathlib import Path

import psycopg

import hunches as hn
from e2e.common.support import (
    StandIn,
    check,
    classify_and_evaluate,
    container,
    corpus_rows,
    expected,
    found,
    run,
    seeds,
)

IMAGE = "docker.io/pgvector/pgvector:pg16"  # podman needs the full registry name
URL = "postgresql://postgres:e2e@127.0.0.1:{port}/postgres"


def ready(port: int) -> None:
    psycopg.connect(URL.format(port=port), connect_timeout=2).close()


def load(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION vector")
        conn.execute(
            "CREATE TABLE corpus (id text PRIMARY KEY, text text NOT NULL, "
            "embedding vector(2) NOT NULL)"
        )
        for r in corpus_rows():
            conn.execute(
                "INSERT INTO corpus VALUES (%s, %s, %s::vector)",
                (r["id"], r["text"], str(r["embedding"])),
            )
        conn.execute("ANALYZE corpus")


def main() -> str | None:
    want = expected()
    with container(
        "pgvector", IMAGE, 5432, {"POSTGRES_PASSWORD": "e2e"}, ready
    ) as port:
        url = URL.format(port=port)
        os.environ["HUNCHES_PG_URL"] = url  # this process's environment only
        load(url)
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            hn.settings.root = tmp
            phrases = list(seeds())
            floor = want["seeds"]["floor"]

            # exact: the database ranks every row by cosine similarity, no index involved
            exact = hn.PgCorpus(table="corpus", search="exact")
            got = hn.get_candidates(
                exact,
                seeds=phrases,
                embedder=StandIn(),
                floor=floor,
                out=False,
                cache=False,
            )
            check("seed search, exact", found(got), want["seeds"]["hits"])
            check("bands, exact", got.bands(), want["seeds"]["band_counts"])

            # index: an HNSW index answers; approximate in general, and for 60 rows the same ids
            with psycopg.connect(url, autocommit=True) as conn:
                conn.execute(
                    "CREATE INDEX ON corpus USING hnsw (embedding vector_cosine_ops)"
                )
            indexed = hn.PgCorpus(table="corpus", search="index")
            got = hn.get_candidates(
                indexed,
                seeds=phrases,
                embedder=StandIn(),
                floor=floor,
                out=False,
                cache=False,
            )
            check("seed search, index", found(got), want["seeds"]["hits"])

            # the vectors are not needed to read the text: the whole corpus, as in the other examples
            got = hn.get_candidates(exact, out=False)
            check("whole corpus", [r["id"] for r in got.rows], want["whole"])
            return classify_and_evaluate(got, tmp)


if __name__ == "__main__":
    run(main)
