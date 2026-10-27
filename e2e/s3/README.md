# S3 Vectors

Reference for a corpus in an Amazon S3 Vectors index, run against a local emulator, no AWS account.

## What it shows

- `hn.S3Corpus(bucket, index)` over an index whose vectors carry the item text as
  `metadata["text"]` and the item id as the key.
- The whole corpus (every item once), keywords and regular expressions, and seed search with
  hand-built vectors (`StandIn` in `../common/support.py`). Results equal the other examples'. The
  service lists vectors in its own order, so keyword ties are compared by id, not by position.
- Paging: a second index of 1,050 generated vectors is read in full, which crosses the library's
  1,000-vector page.
- The whole corpus classified under a cost cap and the dev split scored against the people's labels,
  as in `../table/`.

## Needs

- `podman`, and `uv sync --all-extras` once. The example starts `docker.io/floci/floci:2.3.0` (podman
  needs the full registry name), creates a vector bucket and two indexes, and removes the container
  when it ends, also on failure, Ctrl-C and SIGTERM.
- `ANTHROPIC_API_KEY` in the environment for the first classification; without it every S3 check
  still runs and the last line is `RESULT: skipped - ...`.
- The emulator address and throwaway credentials are set in this process's environment only
  (`AWS_ENDPOINT_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION`).

## Limits

Floci is a stand-in. These checks say nothing about real AWS: IAM permissions, the order of a real
listing, throttling or latency. Check those against a real index before relying on them.

## Run

```bash
uv run python -m e2e.s3.run
```

A pass ends with `RESULT: pass`.

## Cost

About 15 seconds including loading the vectors, plus the container start (the first run also pulls
the image). The classification is cached in `e2e/.cache/`, shared with the other examples.
