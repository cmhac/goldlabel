# pre006 fixtures

A tiny project written by the pre-006 code (TUI-era `goldlabel`), using stubbed models only
(a `FunctionModel` classifier, a fake embedder returning `[1, 0, 0]`). 006 tasks assert the new
code reproduces `expected.json` and reads these files (spec FR-4, SC-4). The values here were
recorded from the old code on purpose; do not regenerate them from new code.

Generated at commit `345c4ff63d7e23bc56e690dc8c21b0bd2878fd3a`.

## Files

- `cache/<key>.json`: one entry from `classifier.classify` (multi mode, two labels, one-line prompt, one text) and one from `candidates.embed_seeds`; `cost.json` as `cost.record` / `record_timing` wrote it (unknown prices are `null`).
- `seeds.csv`, `taxonomy.yaml`, `prompt.md`: written by `files.write_text` / `write_taxonomy`.
- `candidates.jsonl`, `candidates.meta.json`: written by `candidates.build_candidates` against `corpus/`.
- `gold.jsonl`: `files.write_gold`; two dev rows, two test rows, one of them with `labels: []` (the old format's pending-looking row).
- `results.jsonl`: one row with `run`, one without (a row from before 004).
- `corpus.jsonl`: 4 items with a 3-dimensional `embedding` column (model `fake-embed`). The pre-006 code wrote this as a `corpus/` folder; it was converted to one table file when that corpus kind was removed (007), with the same ids, texts and numbers. Every other file here is unchanged pre-006 output.
- `expected.json`: the exact `system_prompt`, `cache_key`, `run_digest`, the seed-embedding cache key and vector, and one local search (query `[1, 0.2, 0]`, floor 0.60) with ids and similarities.
- No `config.toml` (it held a temp path); `tests/test_pre006_fixtures.py` writes one.

## Baseline (before task 02)

- `find src/goldlabel -name '*.py' | xargs wc -l | tail -1`: **11588 total**
- Test files at this point (tests/): test_app.py test_assistant_context.py test_assistant_thinking.py test_brief.py test_browse_screen.py test_candidates.py test_chat.py test_classifier.py test_cost.py test_e2e.py test_files.py test_final_screen.py test_gold_orphan_screen.py test_gold_orphans.py test_gold_screen.py test_history.py test_history_screens.py test_isolation.py test_keys.py test_metrics.py test_model_picker.py test_models.py test_new_project.py test_paths.py test_pg_integration.py test_pre006_fixtures.py test_progress.py test_project_settings.py test_projects.py test_rail.py test_redo_plan.py test_run_screen.py test_search.py test_search_pg_check.py test_search_pg_connect.py test_search_pg_exact.py test_search_pg_guards.py test_search_pg_index.py test_search_pg_probes.py test_search_screen.py test_sizes.py test_stale_ui.py test_status.py test_system.py test_system_screen.py test_taxonomy_screen.py test_theme.py test_threshold_screen.py test_tune_screen.py test_versions.py 

## Generator (one-off, not committed as code; only works on the pre-006 code)

It still writes the old `corpus/` folder; `corpus.jsonl` was converted from that output.

Run from the repo root: `uv run python gen_pre006.py tests/fixtures/pre006`

```python
"""One-off: write tests/fixtures/pre006/ with the pre-006 code. Run: uv run python gen_pre006.py <out_dir>"""

import asyncio, json, os, shutil, sys, tempfile
from pathlib import Path

import numpy as np
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import RequestUsage

out = Path(sys.argv[1]).resolve()
work = Path(tempfile.mkdtemp())
os.chdir(work)

from goldlabel import candidates, classifier, cost, files
from goldlabel.search import search

files.ensure_root()
files.write_config(
    files.Config(
        embedding_model="fake-embed",
        assistant_model="test",
        classifier_model="fake-classifier",
        corpus_dir=str(work / "corpus"),
    )
)
taxonomy = files.Taxonomy(
    mode="multi",
    labels=[
        files.Label(name="alpha", description="about alpha"),
        files.Label(name="beta", description="about beta"),
    ],
)
files.write_taxonomy(taxonomy)
prompt = "Classify the item."
files.write_text("prompt.md", prompt + "\n")
files.write_text("seeds.csv", "seed\nalpha seed\n")


def respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    tool = info.output_tools[0]
    return ModelResponse(
        parts=[
            ToolCallPart(
                tool.name, {"reasoning": "It mentions alpha.", "labels": ["alpha"]}
            )
        ],
        usage=RequestUsage(input_tokens=10, output_tokens=5),
    )


model = FunctionModel(respond, model_name="fake-classifier")
TEXT = "alpha is the first letter"
pred = asyncio.run(classifier.classify(TEXT, prompt, taxonomy, model))


class Emb(Embedder):
    def __init__(self):
        super().__init__(TestEmbeddingModel("fake-embed"))

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [[1.0, 0.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="fake-embed",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


vec = asyncio.run(candidates.embed_seeds(["alpha seed"], Emb()))[0]

corpus = work / "corpus"
corpus.mkdir()
items = [
    ("a1", "alpha one", [1, 0, 0]),
    ("a2", "alpha two", [0.8, 0.6, 0]),
    ("b1", "beta one", [0, 1, 0]),
    ("c1", "gamma one", [0.3, 0.1, 0.9]),
]
(corpus / "items.jsonl").write_text(
    "".join(json.dumps({"id": i, "text": t}) + "\n" for i, t, _ in items)
)
(corpus / "meta.json").write_text(json.dumps({"embedding_model": "fake-embed"}))
np.save(corpus / "vectors.npy", np.array([v for *_, v in items], dtype=np.float32))
asyncio.run(candidates.build_candidates(Emb()))
query = [1.0, 0.2, 0.0]
hits, capped = search(query, 0.60)

files.write_gold(
    [
        files.GoldRow(id="a1", text="alpha one", labels=["alpha"], split="dev"),
        files.GoldRow(id="b1", text="beta one", labels=["beta"], split="dev"),
        files.GoldRow(id="a2", text="alpha two", labels=["alpha"], split="test"),
        files.GoldRow(id="c1", text="gamma one", labels=[], split="test"),
    ]
)
run = files.run_digest(prompt + "\n", taxonomy, "fake-classifier")
files.write_jsonl(
    "results.jsonl",
    [
        {
            "id": "a1",
            "text": "alpha one",
            "labels": ["alpha"],
            "max_similarity": 1.0,
            "run": run,
        },
        {"id": "a2", "text": "alpha two", "labels": ["alpha"], "max_similarity": 0.9},
    ],
)
expected = {
    "classification": {
        "model": "fake-classifier",
        "text": TEXT,
        "prompt": prompt + "\n",
        "system_prompt": classifier.system_prompt(prompt + "\n", taxonomy),
        "cache_key": cost.cache_key(
            "fake-classifier", classifier.system_prompt(prompt + "\n", taxonomy), TEXT
        ),
        "run_digest": run,
        "labels": pred.labels,
        "reasoning": pred.reasoning,
    },
    "seed_embedding": {
        "model": "fake-embed",
        "seed": "alpha seed",
        "cache_key": cost.cache_key("fake-embed", "embed_query", "alpha seed"),
        "vector": vec,
    },
    "search": {
        "query": query,
        "floor": 0.60,
        "hits": [[i, t, s] for i, t, s in hits],
        "capped": capped,
    },
}
if out.exists():
    shutil.rmtree(out)
shutil.copytree(work / ".goldlabel", out)
shutil.copytree(corpus, out / "corpus")
(out / "config.toml").unlink()  # holds a temp path; tests write their own
(out / "expected.json").write_text(json.dumps(expected, indent=2) + "\n")
print(sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()))
```
