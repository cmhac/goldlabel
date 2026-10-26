"""Fixtures written by the pre-006 code (see tests/fixtures/pre006/README.md).

The expected values in expected.json were recorded from that code on purpose; later 006 tasks
assert that the new code reproduces them.
"""

import json
import shutil
from pathlib import Path

import pytest

from hunches import candidates, classifier
from hunches.classifier import Classifier
from hunches.cost import breakdown, cache_get, cache_key
from hunches.gold import Gold
from hunches.search import LocalCorpus, search_vectors
from hunches.settings import settings
from hunches.taxonomy import Taxonomy

FIXTURES = Path(__file__).parent / "fixtures" / "pre006"


@pytest.fixture
def expected():
    return json.loads((FIXTURES / "expected.json").read_text())


@pytest.fixture
def project(tmp_path, monkeypatch):
    shutil.copytree(FIXTURES, tmp_path / ".hunches")
    monkeypatch.chdir(tmp_path)
    settings.root = tmp_path / ".hunches"
    return tmp_path


def read_jsonl(project, name):
    path = project / ".hunches" / name
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def test_files_are_well_formed(project):
    taxonomy = Taxonomy.read(project / ".hunches" / "taxonomy.yaml")
    assert taxonomy.mode == "multi"
    assert [label.name for label in taxonomy.labels] == ["alpha", "beta"]
    assert candidates.read_seeds(".hunches/seeds.csv") == ["alpha seed"]
    assert (project / ".hunches" / "prompt.md").read_text() == "Classify the item.\n"
    meta = json.loads((project / ".hunches" / "candidates.meta.json").read_text())
    assert meta == {
        "seeds_digest": candidates.seeds_digest(["alpha seed"]),
        "written_at": meta["written_at"],
        "floor": 0.6,
        "embedding_model": "fake-embed",
    }
    assert [
        c["id"]
        for c in candidates.Candidates.read(
            project / ".hunches" / "candidates.jsonl"
        ).rows
    ] == ["a1", "a2"]
    gold = Gold(project / ".hunches" / "gold.jsonl").all.rows
    assert [(g.id, g.split, g.labels) for g in gold] == [
        ("a1", "dev", ["alpha"]),
        ("b1", "dev", ["beta"]),
        ("a2", "test", ["alpha"]),
        ("c1", "test", []),  # no labels yet (pre-006 wrote [] for pending)
    ]
    results = read_jsonl(project, "results.jsonl")
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
    # the pre-006 .hunches/cost.json is not read; the ledger now lives in the cache directory
    assert breakdown(None) == {}
    emb_entry, cls_entry = (
        cache_get(None, emb["cache_key"]),
        cache_get(None, cls["cache_key"]),
    )
    assert emb_entry is not None and cls_entry is not None
    assert emb_entry["output"] == emb["vector"]
    assert cls_entry["output"] == {
        "labels": cls["labels"],
        "reasoning": cls["reasoning"],
    }


def test_expected_matches_current_code(project, expected):
    cls = expected["classification"]
    taxonomy = Taxonomy.read(project / ".hunches" / "taxonomy.yaml")
    system = classifier.system_prompt(cls["prompt"], taxonomy)
    assert system == cls["system_prompt"]
    assert cache_key(cls["model"], system, cls["text"]) == cls["cache_key"]
    assert Classifier(cls["model"], taxonomy, cls["prompt"]).digest == cls["run_digest"]
    assert read_jsonl(project, "results.jsonl")[0]["run"] == cls["run_digest"]
    emb = expected["seed_embedding"]
    assert cache_key(emb["model"], "embed_query", emb["seed"]) == emb["cache_key"]


def test_local_search_matches_recorded(project, expected):
    want = expected["search"]
    corpus = LocalCorpus(project / ".hunches" / "corpus")
    hits, capped = search_vectors(
        corpus, want["query"], want["floor"], embedding_model="fake-embed"
    )
    assert [list(h) for h in hits] == want["hits"]
    assert capped is want["capped"]
    assert [h[0] for h in hits] == ["a1", "a2"]
