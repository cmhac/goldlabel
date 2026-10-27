"""SC-1: the README chain end to end, with no real network.

The corpus is the tiny hand-built one in `tests/fixtures/sample_corpus.jsonl`, the embedder and the classifier model
are fakes, and the gold labels come from a SIMULATED HUMAN: a background thread that labels over the
labelling server's HTTP API, the way a browser tab would. This tests the pipeline; it is a test
fixture, not an agent writing gold labels, and nothing in the library offers a way to do the same.
"""

import dataclasses
import http.client
import json
import shutil
import threading
from pathlib import Path
from urllib.parse import urlparse

import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

import hunches as hn
from hunches import _label
from hunches.classifier import CostLimit

SAMPLE = Path(__file__).parent / "fixtures" / "sample_corpus.jsonl"

# What the people labelling decided, written by hand for the five items above the 0.60 floor.
HUMAN = {
    "layoff-1": ["layoff"],
    "layoff-2": ["layoff"],
    "layoff-3": ["layoff"],
    "burnout-1": ["burnout"],
    "burnout-2": ["burnout"],
}


class HandEmbedder(Embedder):
    """Every seed is the vector [1, 0], the direction the sample corpus's layoff items point in."""

    def __init__(self):
        super().__init__(TestEmbeddingModel("hand-built-2d"))
        self.calls = 0

    async def embed_query(self, query, *, settings=None):
        self.calls += 1
        return EmbeddingResult(
            [[1.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="hand-built-2d",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


class FakeModel:
    """A FunctionModel that labels by keyword and counts its calls (one call = one live item)."""

    def __init__(self):
        self.calls = 0
        self.model = FunctionModel(self._answer, model_name="fake-classifier")

    def _answer(self, messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        self.calls += 1
        text = str(messages).lower()
        if (
            "laid off" in text
            or "reorg" in text
            or ("redundanc" in text and "rumours count" in text)
        ):
            labels = ["layoff"]
        elif "exhausted" in text or "weekends" in text:
            labels = ["burnout"]
        else:
            labels = ["off_topic"]
        part = ToolCallPart(
            info.output_tools[0].name, {"reasoning": "keywords", "labels": labels}
        )
        return ModelResponse(parts=[part])


def simulated_human(url: str) -> threading.Thread:
    """Label every pending row over HTTP with HUMAN's answers, then press Done."""
    u = urlparse(url)
    assert u.hostname and u.port
    host, port = u.hostname, u.port
    token = u.query.removeprefix("token=")

    def call(method, path, body=None):
        conn = http.client.HTTPConnection(host, port, timeout=5)
        headers = {"X-Hunches-Token": token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        conn.request(method, path, json.dumps(body) if body else None, headers)
        r = conn.getresponse()
        data = json.loads(r.read().decode())
        conn.close()
        assert r.status == 200, data
        return data

    def run():
        state = call("GET", "/api/state")
        while state["item"] is not None:
            state = call(
                "POST",
                "/api/label",
                {"id": state["item"]["id"], "labels": HUMAN[state["item"]["id"]]},
            )
        call("POST", "/api/done")

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_readme_chain_end_to_end(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    corpus_file = tmp_path / "corpus.jsonl"
    shutil.copy(SAMPLE, corpus_file)
    humans = []
    monkeypatch.setattr(
        _label.webbrowser, "open", lambda url: humans.append(simulated_human(url))
    )

    # 1. search: embeds the seeds (one live call per seed), calls no classifier model
    fake = FakeModel()
    embedder = HandEmbedder()
    candidates = hn.get_candidates(
        hn.Table(
            corpus_file,
            id_column="id",
            vector_column="embedding",
            embedding_model="hand-built-2d",
        ),
        seeds=["I lost my job"],
        embedder=embedder,
    )
    assert embedder.calls == 1
    assert fake.calls == 0
    assert [r["id"] for r in candidates.rows] == list(HUMAN)  # 0.95 ... 0.66, by hand
    assert Path(".hunches/candidates.jsonl").exists()

    # 2. taxonomy and classifier
    taxonomy = hn.Taxonomy(
        mode="single",
        labels={
            "layoff": "The author lost, or fears losing, their job.",
            "burnout": "The author is worn out by work.",
        },
    )
    clf = hn.Classifier(fake.model, taxonomy, prompt="Label the post.")

    # 3. gold: draw pending rows, a person labels them in the page
    gold = hn.Gold()
    gold.draw(candidates, n=3, split="dev", seed=4)
    assert all(r.labels is None for r in gold.pending.rows)
    dev_ids = {r.id for r in gold.pending.rows}
    assert "layoff-3" in dev_ids  # the item the first prompt gets wrong (see FakeModel)
    hn.label(gold, taxonomy)  # blocks until the simulated human presses Done
    humans.pop().join(timeout=10)
    assert len(gold.dev.rows) == 3 and not gold.pending.rows
    assert {r.labelled_by for r in gold.dev.rows} == {"hunches-ui"}
    assert fake.calls == 0  # labelling never calls a model

    # 4. first evaluate: one live call per dev item; layoff-3 is wrong, so 2 of 3
    ev1 = hn.evaluate(clf, gold.dev, target=0.9)
    assert fake.calls == 3
    assert ev1.score() == pytest.approx(2 / 3)
    assert [d["id"] for d in ev1.disagreements] == ["layoff-3"]

    # 5. identical re-evaluate: all cached, zero calls
    hn.evaluate(clf, gold.dev)
    assert fake.calls == 3

    # 6. a changed prompt: one call per item again, and it now agrees with the humans
    clf2 = clf.with_prompt("Label the post. Rumours count as layoffs.")
    ev2 = hn.evaluate(clf2, gold.dev, target=0.9)
    assert fake.calls == 6
    assert ev2.score() == pytest.approx(1.0)
    assert ev2.digest != ev1.digest

    # 7. the test split is drawn, labelled and evaluated once
    gold.draw(candidates, n=1, split="test", seed=0)
    hn.label(gold, taxonomy)
    humans.pop().join(timeout=10)
    final = hn.evaluate(clf2, gold.test)
    assert fake.calls == 7
    assert final.score() == pytest.approx(1.0)

    # 8. the band sample classifies the one candidate nobody has seen yet, live
    report = hn.band_sample(clf2, candidates, per_band=30, seed=0)
    assert fake.calls == 8
    assert sum(r["n"] for r in report.rows) == 5

    # 9. estimate calls no model; max_cost refuses an unpriced live run; a cached run needs no price
    new = ["A new post one", "A new post two"]
    est = clf2.estimate(new)
    assert (est.n, est.cached, est.live, est.dollars) == (2, 0, 2, None)
    with pytest.raises(CostLimit):
        clf2.classify(new, out="refused.jsonl", max_cost=0.50)
    assert fake.calls == 8
    assert not Path("refused.jsonl").exists()
    above = candidates.above(0.70)
    assert clf2.estimate(above).live == 0
    results = clf2.classify(above, out="results.jsonl", max_cost=0.50)
    assert fake.calls == 8
    assert results.cached == 3 and results.live == 0
    assert [r["labels"] for r in results.rows] == [["layoff"]] * 3
    assert len(Path("results.jsonl").read_text().splitlines()) == 3

    # 10. save a bundle; a pipeline script loads it and classifies new items to `out`
    clf2.save("classifiers/layoffs", evaluation=final)

    def pipeline(items, out):
        loaded = hn.Classifier.load("classifiers/layoffs")
        # a bundle stores the model as a string; swap in the stub instead of a real provider
        loaded = dataclasses.replace(loaded, model=fake.model)
        return loaded.classify(items, out=out)

    piped = pipeline(["I got laid off today", "Soup recipe"], out="piped.jsonl")
    assert fake.calls == 10
    assert piped.labels == [["layoff"], ["off_topic"]]
    lines = [json.loads(x) for x in Path("piped.jsonl").read_text().splitlines()]
    # lines are appended as items finish, so the file's order is not the input's
    assert {x["text"]: x["labels"] for x in lines} == {
        "I got laid off today": ["layoff"],
        "Soup recipe": ["off_topic"],
    }
    assert {x["run"] for x in lines} == {clf2.digest}

    # 11. the evaluation log: one line per evaluate call, with the prompt of each
    log = [json.loads(x) for x in Path(".hunches/evals.jsonl").read_text().splitlines()]
    assert [(x["split"], x["n"]) for x in log] == [
        ("dev", 3),
        ("dev", 3),
        ("dev", 3),
        ("test", 1),
    ]
    assert [x["live_calls"] for x in log] == [3, 0, 3, 1]
    assert log[0]["prompt"] == "Label the post."
    assert log[2]["prompt"] == "Label the post. Rumours count as layoffs."
    assert "test split evaluated 1 times (1 distinct prompts)" in repr(hn.eval_log())
