# Research: End-to-end reference examples

Decision, rationale, alternatives. Facts were checked on 2026-10-27, in this repository's sandbox
where possible; anything only a secondary source says is marked so.

## R1. Which classification model

- **Decision**: `anthropic:claude-haiku-5-5`, with the lock file's `genai-prices` bumped
  (`uv lock --upgrade-package genai-prices`) so the library can price it. **This is a choice for
  Chris to confirm** (spec: "chosen at planning"); the alternative below needs no bump.
- **Evidence**: the locked `genai-prices` 0.1.9 raises "Unable to find model" for
  `claude-haiku-5-5`, so a `max_cost` run would refuse (correct, by Principle VI). A newer release
  prices it at $0.0002 for 1,000 input and 200 output tokens, which is $0.10 per million input and
  $0.50 per million output. Secondary sources
  ([eesel](https://www.eesel.ai/blog/claude-haiku-5-5-pricing),
  [DEV Community](https://dev.to/hassann/claude-haiku-55-pricing-53cb)) give the same rates and the
  October 7, 2026 launch and say the rate rises above 100k-token prompts, which the examples never
  reach; none of them is Anthropic's pricing page, so the first real run should be compared with the
  provider's billing page. `pydantic-ai-slim` 2.53 builds an `AnthropicModel` for the name.
- **Cost estimate**: about 60 items at roughly 600 input and 120 output tokens each is 36k input and
  7k output, about $0.007 on Haiku 5.5 (about $0.07 on Haiku 4.5). Well under SC-007's one dollar.
  A secondary source says the newer tokenizer yields about 30% more tokens; it does not change the
  order of magnitude. The real figure goes in the walkthrough README after the first human run.
- **Alternatives**: `claude-haiku-4-5` (priced in the locked version, $1/$5 per million, older
  model); OpenAI small models (the project supports them, but one provider keeps the example
  simple).
- **Not verified here**: this session has no API key, so no real classification, accuracy or price
  figure has been observed. The first run is a human step.

## R2. Corpus topic, labels and prompt

- **Decision**: workplace posts, as in the existing sample, so its prose carries over. Mode
  `single`, labels `layoff` and `burnout` plus the built-in `off_topic`. Sixty items: about 20 each,
  with deliberate hard cases (rumoured redundancies, tiredness not caused by work, a post that
  mentions both). The corpus must also contain items with a literal `%`, `_` and backslash so the
  wildcard-escape checks (US2 scenario 3) have something to find. Prompt: the sample's one-sentence
  prompt, plus the rumour rule the walkthrough's "tune on dev" step teaches.
- **Gate**: Chris approves the topic, labels, prompt and corpus **before** labelling (FR-019); a
  later change makes labelled rows stale and the offline test fails.
- **Gold split**: about 40 labelled rows, 30 dev and 10 test, drawn with `Gold.draw(..., seed=...)`
  so the draw is repeatable.

## R3. Hand-built vectors

- **Decision**: 2-D unit vectors taken only from Pythagorean pairs, for example (1,0), (0.96,0.28),
  (0.8,0.6), (0.6,0.8), (0.28,0.96), (0,1). Seeds are the axes (1,0) and (0,1), so the cosine to a
  seed is a coordinate and every expected similarity is an exact decimal written by hand. The
  stand-in embedder is a table lookup from seed phrase to vector (`seeds.json`).
- **Rationale**: `Embedder` subclass with `TestEmbeddingModel` already works this way in the
  existing sample and in `tests/test_table.py`; no key and no randomness (FR-008).
- **Alternative**: random or real embeddings. Rejected: adds a key and non-determinism and tests none
  of the library's logic.

## R4. Containers

- **Decision**: images `postgres:16` (plain), `pgvector/pgvector:pg16`, `floci/floci:<pinned tag>`
  (`latest` was 2.3.0 when verified; pin the tag, record it in the example README). Start with
  `podman run -d --rm --name hunches-e2e-<example>-<pid> --label hunches-e2e=<example>
  -p 127.0.0.1::<port>` and read the host port back with `podman port`.
- **Evidence**: in this sandbox a published random port works (`5432/tcp -> 127.0.0.1:39909`), so
  host networking, which does not work through `podman machine` on macOS, is not needed.
  Floci serves S3 Vectors on port 4566 with any credentials ([i-programmer](https://www.i-programmer.info/news/90-tools/19067-floci-a-high-performance-local-aws-emulator-guide.html));
  boto3 honours `AWS_ENDPOINT_URL`, verified earlier this session. Search results for the Floci
  image name disagreed (`floci/floci` vs `hectorvent/floci`); the pulled image is
  `docker.io/floci/floci:latest`.
- **Cleanup**: stale containers with the example's label are removed at start; removal runs in
  `finally`, `atexit` and a SIGTERM handler (SIGINT already raises `KeyboardInterrupt`). A SIGKILL
  leaves a container, which the next run's label sweep removes.
- **Readiness**: Postgres by a `psycopg.connect` retry loop (60 s); Floci by a boto3 `list_vector_buckets`
  retry loop. On timeout print `podman logs --tail 20`.
- **Alternatives**: `--network host` (breaks on macOS machines); `podman-compose` or quadlets (a new
  tool for no gain); Python container libraries (new dependency).

## R5. How examples run and report

- **Decision**: each example is `python -m e2e.<name>.run`; it prints human-readable progress, then
  a last line `RESULT: pass|fail|skipped - <reason or summary>` and exits 0 for pass and skipped,
  1 for fail (contract: [contracts/example-run.md](contracts/example-run.md)). `run_all.py` runs
  them one at a time, reads each last line, and for the notebook uses `nbclient`.
- **Sequential** by design; the spec's "two examples at once" edge case is met by unique container
  names and free ports plus the atomic cache write. `cost.json` in the cache directory is a
  read-modify-write that the library already documents as thread-safe only, so concurrent runs can
  lose a cost line (it feeds estimates, not results). Recorded as a known limit.
- **Cross-example consistency (SC-002)**: candidates are compared with `expected.json` in every
  example. Evaluation scores come from the shared cache so they are equal by construction when the
  gold file and classifier are the same; `run_all` still compares the printed scores and fails if
  they differ, and each example checks the score against the target (a lower bound, not an exact
  value, because model output is not pinned).
- **Notebook skipped vs failed**: a missing key raises `RuntimeError("SKIPPED: ...")` in a cell;
  `run_all` reports `skipped` for that and `fail` for any other exception.

## R6. Parquet through pandas

- **Decision**: `pyarrow` is not a project dependency (`tests/test_table.py` already `importorskip`s
  it, and it is absent from the environment). The table example is run with
  `uv run --with pyarrow python -m e2e.table.run`, and `run_all` uses the same command, so that form
  is checked. Run without it the example reports the form as skipped (spec edge case).
- **Alternative**: add `pyarrow` to the dev group. Rejected: another dependency to make one check
  pass; the constitution already points ephemeral needs at `uv run --with`.

## R7. Size-limit, pagination and index checks

- **Size limit (US2.5)**: `PgCorpus(max_result_mb=...)` is a field; the example sets a small
  value and runs `ANALYZE` first so the planner statistics exist, then expects the refusal that
  names the limit, then a `limit=` and a keyword filter get past it.
- **S3 pagination (US3.1)**: the library lists 1,000 vectors per page and the corpus has 60, so a
  second index in the same bucket is loaded with 1,050 generated filler vectors (500 per
  `put_vectors` call) for this one check. The filler is generated in the script and never
  committed; the corpus stays the single dataset for everything else.
- **pgvector index mode (US2.4)**: with 60 rows an HNSW index is effectively exact, so index mode
  must return the same ids as exact mode; if a run shows otherwise, the example raises
  `hnsw.ef_search`. Verified at implementation against the container.

## R8. Gold file

- **Decision**: `e2e/common/gold.jsonl` is produced once by a person: `Gold.draw` writes pending
  rows (no labels), `hn.label(gold, taxonomy)` is used in a browser, the file is committed as
  written, and `GOLD.md` records who, when and the corpus/taxonomy/prompt commit. Examples copy the
  file with `shutil.copyfile` into their temporary folder, compare bytes, and show `GOLD.md`.
- **Offline test**: while the file is absent the gold checks are skipped with a reason that says the
  maintainer has not labelled yet, so the rest of the drift test runs; once it exists every row is
  checked against the corpus (same id and text) and the taxonomy.
- **Alternatives**: an agent-written file (refused: Principle I); `Gold.import_rows` at run time
  (rewrites `labelled_by` and `labelled_at`, which spec FR-015 forbids).

## R9. Moving the sample

- `examples/sample/corpus.jsonl` is also the corpus of `tests/test_e2e.py`, so it moves to
  `tests/fixtures/sample_corpus.jsonl` (eight hand-built items stay exactly as they are); the
  notebook moves to `e2e/walkthrough/` rebuilt on the common data; the script twin, its drift test
  and `examples/` go. `pyproject.toml`'s `examples/**` lint exemption becomes `e2e/**`.
- References to update: `README.md`, `AGENTS.md` (human-checks list and layout), `tests/test_docs.py`,
  `tests/test_e2e.py`. The skill references do not name the folder (checked by search).
