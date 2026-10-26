"""Fixtures written by the pre-006 code (see tests/fixtures/pre006/README.md).

The expected values in expected.json were recorded from that code on purpose; later 006 tasks
assert that the new code reproduces them.
"""

import json
import shutil
from pathlib import Path

import pytest
from pydantic_ai.models.function import FunctionModel

from hunches import candidates, classifier, cost, files
from hunches.search import search

FIXTURES = Path(__file__).parent / "fixtures" / "pre006"


@pytest.fixture
def expected():
    return json.loads((FIXTURES / "expected.json").read_text())


@pytest.fixture
def project(tmp_path, monkeypatch):
    shutil.copytree(FIXTURES, tmp_path / ".hunches")
    monkeypatch.chdir(tmp_path)
    corpus = (tmp_path / ".hunches" / "corpus").resolve()
    files.write_config(
        files.Config(
            embedding_model="fake-embed",
            classifier_model="fake-classifier",
            corpus_dir=str(corpus),
        )
    )
    return tmp_path


def test_files_are_well_formed(project):
    taxonomy = files.read_taxonomy()
    assert taxonomy.mode == "multi"
    assert [label.name for label in taxonomy.labels] == ["alpha", "beta"]
    assert candidates.read_seeds() == ["alpha seed"]
    assert files.read_text("prompt.md") == "Classify the item.\n"
    meta = json.loads((project / ".hunches" / "candidates.meta.json").read_text())
    assert meta == {
        "seeds_digest": candidates.seeds_digest(["alpha seed"]),
        "written_at": meta["written_at"],
        "floor": 0.6,
        "embedding_model": "fake-embed",
    }
    assert [c["id"] for c in files.read_jsonl("candidates.jsonl")] == ["a1", "a2"]
    gold = files.read_gold()
    assert [(g.id, g.split, g.labels) for g in gold] == [
        ("a1", "dev", ["alpha"]),
        ("b1", "dev", ["beta"]),
        ("a2", "test", ["alpha"]),
        ("c1", "test", []),  # the pending-looking row: no labels yet
    ]
    results = files.read_jsonl("results.jsonl")
    assert [("run" in r) for r in results] == [True, False]


def test_corpus_is_well_formed(project):
    corpus = project / ".hunches" / "corpus"
    assert json.loads((corpus / "meta.json").read_text()) == {
        "embedding_model": "fake-embed"
    }
    assert len((corpus / "items.jsonl").read_text().splitlines()) == 4
    import numpy as np

    assert np.load(corpus / "vectors.npy").shape == (4, 3)


def test_cache_and_cost_are_well_formed(project, expected):
    cls, emb = expected["classification"], expected["seed_embedding"]
    names = sorted(p.stem for p in (project / ".hunches" / "cache").glob("*.json"))
    assert names == sorted([cls["cache_key"], emb["cache_key"]])
    spent = cost.breakdown()
    assert set(spent) == {"fake-classifier", "fake-embed"}
    assert spent["fake-classifier"]["calls"] == 1
    assert spent["fake-embed"]["calls"] == 1
    emb_entry, cls_entry = (
        cost.cache_get(emb["cache_key"]),
        cost.cache_get(cls["cache_key"]),
    )
    assert emb_entry is not None and cls_entry is not None
    assert emb_entry["output"] == emb["vector"]
    assert cls_entry["output"] == {
        "labels": cls["labels"],
        "reasoning": cls["reasoning"],
    }


def test_expected_matches_current_code(project, expected):
    cls = expected["classification"]
    taxonomy = files.read_taxonomy()
    system = classifier.system_prompt(cls["prompt"], taxonomy)
    assert system == cls["system_prompt"]
    assert cost.cache_key(cls["model"], system, cls["text"]) == cls["cache_key"]
    assert files.run_digest(cls["prompt"], taxonomy, cls["model"]) == cls["run_digest"]
    assert files.read_jsonl("results.jsonl")[0]["run"] == cls["run_digest"]
    emb = expected["seed_embedding"]
    assert cost.cache_key(emb["model"], "embed_query", emb["seed"]) == emb["cache_key"]


async def test_old_cache_entry_is_a_hit(project, expected):
    cls = expected["classification"]

    def never(messages, info):
        raise AssertionError("a cache hit must not call the model")

    prediction = await classifier.classify(
        cls["text"],
        cls["prompt"],
        files.read_taxonomy(),
        FunctionModel(never, model_name=cls["model"]),
    )
    assert prediction.cached is True
    assert prediction.labels == cls["labels"]
    assert prediction.reasoning == cls["reasoning"]


def test_local_search_matches_recorded(project, expected):
    want = expected["search"]
    hits, capped = search(want["query"], want["floor"])
    assert [list(h) for h in hits] == want["hits"]
    assert capped is want["capped"]
    assert [h[0] for h in hits] == ["a1", "a2"]
