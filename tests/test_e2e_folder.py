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


# --- e2e/run_all.py ---------------------------------------------------------------------------------

from e2e import run_all


def test_run_all_reads_the_last_result_line_and_the_score():
    out = "ok  a\nscore=0.8000\nelapsed 1s\nRESULT: skipped - no key\n"
    assert run_all.parse(out) == ("skipped", "no key", 0.8)
    assert run_all.parse("RESULT: pass\n") == ("pass", "", None)
    assert run_all.parse("RESULT: fail - x: expected 1, got 2")[0] == "fail"
    assert run_all.parse("ok  a\n")[0] == "fail"  # killed before its RESULT line


def test_run_all_verdict_fails_on_a_failure_or_on_different_scores():
    ok = ("pass", "", 0.8)
    assert run_all.overall({"a": ok, "b": ok}) == "pass"
    assert run_all.overall({"a": ok, "b": ("skipped", "no key", None)}) == "skipped"
    assert run_all.overall({"a": ok, "b": ("fail", "x", None)}) == "fail"
    assert run_all.overall({"a": ok, "b": ("pass", "", 0.7)}) == "fail"


# --- the folder is complete, linked and offline-safe ------------------------------------------------

import tomllib

from test_docs import public_names_used

E2E = ROOT / "e2e"
EXAMPLES = ["table", "postgres", "pgvector", "s3"]
RUNNING_DOCKER = re.compile(
    r"\bdocker\s+(run|pull|build|compose|exec|ps|rm|stop|start|images)\b"
    r"|docker-compose|docker\.sock|docker daemon",
    re.IGNORECASE,
)


def test_each_path_has_exactly_one_folder_with_its_parts():
    folders = {p.name for p in E2E.iterdir() if p.is_dir()}
    assert folders - {"__pycache__", ".cache"} == {*EXAMPLES, "walkthrough", "common"}
    for name in EXAMPLES:
        assert (E2E / name / "run.py").is_file(), name
        assert "run(main)" in (E2E / name / "run.py").read_text(), name
    assert (E2E / "walkthrough" / "walkthrough.ipynb").is_file()
    assert (E2E / "run_all.py").is_file() and (E2E / "README.md").is_file()


def test_every_readme_links_its_folders_and_states_command_needs_and_cost():
    for name in [*EXAMPLES, "walkthrough"]:
        text = (E2E / name / "README.md").read_text()
        for heading in ("## Needs", "## Run", "## Cost"):
            assert heading in text, f"{name}: {heading}"
        if name != "walkthrough":
            assert f"python -m e2e.{name}.run" in text, name
        for readme in ("README.md", "e2e/README.md"):
            path = ROOT / readme
            link = f"e2e/{name}/" if readme == "README.md" else f"{name}/"
            assert link in path.read_text(), f"{readme} does not link {name}"


def test_examples_use_only_public_library_names():
    for path in E2E.rglob("*.py"):
        for name in public_names_used(path.read_text()):
            assert name in hn.__all__, f"{path.relative_to(ROOT)} uses hn.{name}"


def test_nothing_under_e2e_or_in_the_new_docs_runs_docker():
    paths = [
        *E2E.rglob("*.py"),
        *E2E.rglob("*.md"),
        E2E / "walkthrough" / "walkthrough.ipynb",
    ]
    for path in [*paths, ROOT / "README.md"]:
        assert not RUNNING_DOCKER.search(path.read_text()), path.relative_to(ROOT)


def test_the_default_test_run_never_collects_e2e_and_the_cache_is_ignored():
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert config["tool"]["pytest"]["ini_options"]["testpaths"] == ["tests"]
    assert "e2e/.cache/" in (ROOT / ".gitignore").read_text().splitlines()


def test_gold_provenance_is_committed_with_the_gold_file():
    if (COMMON / "gold.jsonl").exists():
        assert (COMMON / "GOLD.md").is_file(), "gold.jsonl needs GOLD.md beside it"


# --- support.container against a stand-in `podman` ----------------------------------------------------

STUB = """#!/bin/sh
echo "$@" >> "$PODMAN_LOG"
case "$1" in
  ps) printf '%s' "$PODMAN_PS" ;;
  port) echo "127.0.0.1:5555" ;;
  logs) echo "last log line" ;;
esac
"""


@pytest.fixture
def fake_podman(tmp_path, monkeypatch):
    stub = tmp_path / "bin" / "podman"
    stub.parent.mkdir()
    stub.write_text(STUB)
    stub.chmod(0o755)
    log = tmp_path / "podman.log"
    monkeypatch.setenv("PATH", f"{stub.parent}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("PODMAN_LOG", str(log))
    monkeypatch.setenv("PODMAN_PS", "")
    return lambda: log.read_text().splitlines() if log.exists() else []


def test_the_container_is_published_on_a_random_local_port_and_removed_after_a_failure(
    fake_podman,
):
    name = f"hunches-e2e-x-{os.getpid()}"
    with (
        pytest.raises(RuntimeError, match="boom"),
        support.container("x", "img", 5432, {"A": "b"}) as port,
    ):
        assert port == 5555
        raise RuntimeError("boom")
    calls = fake_podman()
    run = next(c for c in calls if c.startswith("run "))
    assert f"--name {name}" in run and "-p 127.0.0.1::5432" in run and "-e A=b" in run
    assert calls[-1] == f"rm -f {name}"


def test_a_container_left_by_a_dead_run_is_swept_but_a_live_run_is_respected(
    fake_podman, monkeypatch
):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    monkeypatch.setenv("PODMAN_PS", f"hunches-e2e-x-{dead.pid}\n")
    with support.container("x", "img", 5432):
        pass
    assert f"rm -f hunches-e2e-x-{dead.pid}" in fake_podman()

    monkeypatch.setenv("PODMAN_PS", f"hunches-e2e-x-{os.getpid()}\n")
    before = len(fake_podman())
    with (
        pytest.raises(support.Failed, match="another run of x is in progress"),
        support.container("x", "img", 5432),
    ):
        pass
    assert not any(c.startswith("run ") for c in fake_podman()[before:])


def test_a_service_that_never_answers_fails_with_the_log_and_is_removed(
    fake_podman, monkeypatch
):
    monkeypatch.setattr(support, "READY_SECONDS", 0.2)
    with (
        pytest.raises(support.Failed, match="last log line"),
        support.container("x", "img", 5432, ready=lambda port: False),
    ):
        pass
    assert fake_podman()[-1] == f"rm -f hunches-e2e-x-{os.getpid()}"
