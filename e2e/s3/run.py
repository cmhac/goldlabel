"""S3 Vectors on a local emulator (Floci): the whole corpus, keywords and seed search.

Run from the repository root: `uv run python -m e2e.s3.run` (needs podman).
Floci is a stand-in: nothing here says how real AWS orders results, checks permissions or throttles.
"""

import os
import tempfile
from pathlib import Path

import boto3

import hunches as hn
from e2e.common.support import (
    StandIn,
    check,
    classify_and_evaluate,
    container,
    corpus_rows,
    expected,
    found,
    hits,
    run,
    seeds,
)

IMAGE = "docker.io/floci/floci:2.3.0"  # podman needs the full registry name
BUCKET = "hunches-e2e"
PAGE = 1000  # the library lists this many vectors per request
PAD = PAGE + 50


def ready(port: int) -> None:
    client_for(port).list_vector_buckets()


def client_for(port: int):
    return boto3.client(
        "s3vectors",
        endpoint_url=f"http://127.0.0.1:{port}",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )


def put(client, index: str, vectors: list[dict]) -> None:
    client.create_index(
        vectorBucketName=BUCKET,
        indexName=index,
        dataType="float32",
        dimension=2,
        distanceMetric="cosine",
    )
    for start in range(0, len(vectors), 500):  # put_vectors takes at most 500
        client.put_vectors(
            vectorBucketName=BUCKET,
            indexName=index,
            vectors=vectors[start : start + 500],
        )


def by_rank(rows: list[list]) -> list[list]:
    # the service lists vectors in its own order, so ties are compared by id, not by position
    return sorted(rows, key=lambda h: (-h[1], -h[2], h[0]))


def main() -> str | None:
    want = expected()
    with container("s3", IMAGE, 4566, ready=ready) as port:
        # the emulator's address and throwaway credentials live in this process's environment only
        os.environ["AWS_ENDPOINT_URL"] = f"http://127.0.0.1:{port}"
        os.environ["AWS_ACCESS_KEY_ID"] = os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
        os.environ["AWS_DEFAULT_REGION"] = "us-east-1"
        client = client_for(port)
        client.create_vector_bucket(vectorBucketName=BUCKET)
        # each vector: the key is the item id, the text rides along as metadata["text"]
        put(
            client,
            "corpus",
            [
                {
                    "key": r["id"],
                    "data": {"float32": r["embedding"]},
                    "metadata": {"text": r["text"]},
                }
                for r in corpus_rows()
            ],
        )
        # a second index with more vectors than one page of the listing, for the paging check
        put(
            client,
            "pad",
            [
                {
                    "key": f"f{i:04d}",
                    "data": {"float32": [1.0, 0.0]},
                    "metadata": {"text": f"filler {i}"},
                }
                for i in range(PAD)
            ],
        )
        with tempfile.TemporaryDirectory() as folder:
            tmp = Path(folder)
            hn.settings.root = tmp
            corpus = hn.S3Corpus(BUCKET, "corpus")

            got = hn.get_candidates(corpus, out=False)
            ids = [r["id"] for r in got.rows]
            check("whole corpus, every item once", sorted(ids), sorted(want["whole"]))
            for key, entry in want["keywords"].items():
                got = hn.get_candidates(
                    corpus, keywords=entry["terms"], regex=entry["regex"], out=False
                )
                check(f"keywords {key}", by_rank(hits(got)), by_rank(entry["hits"]))

            got = hn.get_candidates(
                corpus,
                seeds=list(seeds()),
                embedder=StandIn(),
                floor=want["seeds"]["floor"],
                out=False,
                cache=False,
            )
            check("seed search", found(got), want["seeds"]["hits"])

            got = hn.get_candidates(hn.S3Corpus(BUCKET, "pad"), out=False)
            padded = [r["id"] for r in got.rows]
            check(
                f"paging: all {PAD} vectors of a {PAD}-vector index", len(padded), PAD
            )
            check("paging: each once", len(set(padded)), PAD)

            candidates = hn.get_candidates(corpus, out=False)
            return classify_and_evaluate(candidates, tmp)


if __name__ == "__main__":
    run(main)
