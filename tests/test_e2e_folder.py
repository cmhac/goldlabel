"""Offline checks on `e2e/`: the opt-in end-to-end examples are never run here.

Everything below reads files only. Expected values are re-derived with plain string counting and
arithmetic, not with the library under test.
"""

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

import hunches as hn
from e2e.common import support
from hunches.classifier import CostLimit
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


# --- e2e/common/support.py ------------------------------------------------------------------------

ROOT = COMMON.parent.parent


def run_example(body: str) -> subprocess.CompletedProcess:
    code = (
        "from e2e.common.support import Failed, check, run\n"
        f"def main():\n    {body}\nrun(main)\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
    )


def test_result_line_and_exit_status_for_pass_skipped_and_fail():
    done = run_example("check('one', 1, 1)")
    assert done.returncode == 0
    assert done.stdout.splitlines()[-1] == "RESULT: pass"

    done = run_example("return 'no key'")
    assert done.returncode == 0
    assert done.stdout.splitlines()[-1] == "RESULT: skipped - no key"

    done = run_example("check('sum', 1 + 1, 3)")
    assert done.returncode == 1
    assert done.stdout.splitlines()[-1] == "RESULT: fail - sum: expected 3, got 2"

    done = run_example("raise KeyError('boom')")
    assert done.returncode == 1
    assert done.stdout.splitlines()[-1] == "RESULT: fail - KeyError: 'boom'"


def test_stand_in_embedder_returns_the_seed_vector_and_rejects_unknown_phrases():
    import asyncio

    embedder = support.StandIn()
    result = asyncio.run(embedder.embed_query("I just lost my job"))
    assert result.embeddings == [[1.0, 0.0]]
    with pytest.raises(KeyError, match="no such phrase"):
        asyncio.run(embedder.embed_query("no such phrase"))


def test_a_missing_podman_fails_naming_podman_and_never_docker(monkeypatch):
    monkeypatch.setenv("PATH", "")
    with (
        pytest.raises(support.Failed) as caught,
        support.container("x", "postgres:16", 5432),
    ):
        pass
    assert "podman is required" in str(caught.value)
    assert "docker" not in str(caught.value).lower()


ROWS = [{"id": "a", "text": "laid off today"}, {"id": "b", "text": "nice weather"}]


def test_no_key_and_nothing_cached_skips_after_the_estimate(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.delenv(support.KEY, raising=False)
    got = support.classify_and_evaluate(
        hn.Candidates(ROWS, source="all"), tmp_path, cache=tmp_path / "c"
    )
    assert got is not None and support.KEY in got and "2 items" in got
    assert "Estimate: 2 items, 0 cached, 2 live calls" in capsys.readouterr().out


def test_an_unknown_price_costs_one_probe_call_and_then_refuses(tmp_path, monkeypatch):
    calls = []

    def answer(messages, info: AgentInfo) -> ModelResponse:
        calls.append(1)
        args = {"reasoning": "x", "labels": ["off_topic"]}
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, args)])

    monkeypatch.setattr(support, "MODEL", FunctionModel(answer, model_name="unpriced"))
    with pytest.raises(CostLimit, match="unknown"):
        support.classify_and_evaluate(
            hn.Candidates(ROWS, source="all"), tmp_path, cache=tmp_path / "c"
        )
    assert len(calls) == 1
