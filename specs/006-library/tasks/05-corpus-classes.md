# 05 — Corpus classes and vector search without `Config`

Spec: "Corpus", FR-1, FR-5; 005 and its deltas for all pgvector behaviour.

**Do** in `search.py`:
- Three frozen dataclasses, no base class: `LocalCorpus(dir)`; `S3Corpus(bucket, index, region=None)`; `PgCorpus(table, id_column="id", text_column="text", vector_column="embedding", text_table=None, text_id_column=None, url_env="HUNCHES_PG_URL", search="exact", statement_timeout_s=..., auth="url", aws_region=None, aws_profile=None, max_result_mb=512)` with the same defaults and validation as the `pg_*` fields in `files.Config`/`PG_DEFAULTS` today.
- Replace `search(query_vector, floor)` (reads `Config`) with `search_vectors(corpus, vector, floor, *, embedding_model)` dispatching with a plain `if`/`match` on the class; it returns what it returns today (`(hits, capped)`). `embedding_model` is used only for the local corpus's `meta.json` mismatch check. `search_pg_exact`, `_search_pg_index`, `check_store`, `pg_connect`, `pg_message`, the probes, `Stop`/`SearchCancelled` take the `PgCorpus` instead of `Config`.
- pgvector URL: environment variable named by `url_env` **only**. Delete the keyring path, `pg_url_id`, `pg_url_name` and every use of `keys` and `system` in `search.py`; error messages name the environment variable. `max_result_mb` replaces `System.pg_max_result_mb`. `check_store` becomes `PgCorpus.check(seeds=None)`; the spec says `corpus.check()` for all three but only pgvector has a check today: implement it for `PgCorpus` only and correct the spec wording in this commit.
- Delete `keys.py` and `tests/test_keys.py` if nothing else imports them after this; otherwise leave for task 11.
- Port every `tests/test_search_pg_*.py`, `tests/test_search.py`, `tests/test_pg_integration.py` to build corpus objects instead of `Config` + system files; assertions stay the same.

**Tests (red first)**: all ported tests pass with identical expectations; the local corpus gives the same ids and similarities as `expected.json` from task 01 (FR-5); defaults and validation of `PgCorpus` match the old `PG_DEFAULTS`; a `PgCorpus` with no URL in its `url_env` variable raises a message naming the variable and never mentioning a keyring; `S3Corpus` with a stubbed boto3 behaves as before including the `topK` cap and `capped`; the URL, password and token never appear in any exception text (existing scrubber tests, ported).

**Not in this task**: `hunches.search()` (the seeds → `Candidates` function; task 06), embedding.
