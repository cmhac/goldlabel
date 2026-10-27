"""Offline checks on `e2e/`: the opt-in end-to-end examples are never run here.

Everything below reads files only. Expected values are re-derived with plain string counting and
arithmetic, not with the library under test.
"""

import json
import math
import re
from pathlib import Path

import pytest

from hunches.taxonomy import Taxonomy

COMMON = Path(__file__).parent.parent / "e2e" / "common"
# Exact decimal unit-vector coordinates (3-4-5 and 7-24-25 triples), research R3.
ALLOWED = {0.0, 1.0, -1.0, 0.28, 0.96, 0.352, 0.936, 0.6, 0.8, -0.6, -0.8}


def corpus():
    lines = (COMMON / "corpus.jsonl").read_text().splitlines()
    return [json.loads(line) for line in lines]


def expected():
    return json.loads((COMMON / "expected.json").read_text())


def seeds():
    return json.loads((COMMON / "seeds.json").read_text())


def test_corpus_has_sixty_distinct_non_empty_items():
    rows = corpus()
    assert len(rows) == 60
    assert len({r["id"] for r in rows}) == 60
    assert all(isinstance(r["text"], str) and r["text"].strip() for r in rows)


def test_embeddings_are_exact_unit_vectors_from_the_written_table():
    for r in corpus():
        x, y = r["embedding"]
        assert {x, y} <= ALLOWED, r["id"]
        assert math.isclose(x * x + y * y, 1.0, abs_tol=1e-9), r["id"]
    for phrase, (x, y) in seeds().items():
        assert math.isclose(x * x + y * y, 1.0, abs_tol=1e-9), phrase


def test_the_wildcard_characters_are_in_the_corpus():
    texts = [r["text"] for r in corpus()]
    for ch in ("%", "_", "\\"):
        assert sum(ch in t for t in texts) >= 2, ch


def test_taxonomy_and_prompt_load():
    taxonomy = Taxonomy.read(COMMON / "taxonomy.yaml")
    assert taxonomy.names == ["layoff", "burnout", "off_topic"]
    assert taxonomy.mode == "single"
    assert (COMMON / "prompt.md").read_text().strip()


def test_expected_whole_is_the_corpus_in_order():
    assert expected()["whole"] == [r["id"] for r in corpus()]


def hits_by_hand(terms, regex):
    out = []
    for index, r in enumerate(corpus()):
        counts = []
        for term in terms:
            if regex:
                counts.append(len(re.findall(term, r["text"])))
            else:
                counts.append(r["text"].lower().count(term.lower()))
        n = sum(c > 0 for c in counts)
        if n:
            out.append((-n, -sum(counts), index, r["id"]))
    return [[i, -n, -m] for n, m, _, i in sorted(out)]


def test_expected_keyword_hits_match_plain_counting():
    for name, entry in expected()["keywords"].items():
        want = hits_by_hand(entry["terms"], entry["regex"])
        assert entry["hits"] == want, name
        assert entry["limit5"] == want[:5], name
        assert want, name  # a search with no hits would test nothing


def test_expected_seed_hits_match_dot_products():
    spec = expected()["seeds"]
    found = []
    for r in corpus():
        best = None
        for phrase, s in seeds().items():
            sim = round(r["embedding"][0] * s[0] + r["embedding"][1] * s[1], 4)
            if sim >= spec["floor"] and (best is None or sim > best[0]):
                best = (sim, phrase)
        if best:
            found.append([r["id"], best[0], best[1]])
    found.sort(key=lambda h: (-h[1], h[0]))
    assert spec["hits"] == found
    assert sum(spec["band_counts"]) == len(found)


def test_gold_rows_match_the_corpus_and_taxonomy():
    path = COMMON / "gold.jsonl"
    if not path.exists():
        pytest.skip("gold labels not made yet: Chris labels them, see e2e/README.md")
    texts = {r["id"]: r["text"] for r in corpus()}
    names = set(Taxonomy.read(COMMON / "taxonomy.yaml").names)
    bad = []
    for line in path.read_text().splitlines():
        row = json.loads(line)
        labels = row["labels"] or []
        stale = row["id"] not in texts or row["text"] != texts[row["id"]]
        unstamped = bool(labels) and row.get("labelled_by") != "hunches-ui"
        if stale or unstamped or not set(labels) <= names:
            bad.append(row["id"])
    assert not bad, f"gold rows that no longer match the corpus or taxonomy: {bad}"
