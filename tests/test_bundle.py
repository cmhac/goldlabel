import json
import warnings
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from hunches.classifier import Classifier
from hunches.evaluation import evaluate
from hunches.gold import Gold
from hunches.taxonomy import Label, Taxonomy


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


TAXONOMY = Taxonomy(
    mode="single", labels=[Label(name="a", description="about a"), Label(name="b")]
)


def answering(answers):
    def fn(messages, info: AgentInfo):
        text = next(
            p.content
            for m in reversed(messages)
            for p in reversed(m.parts)
            if isinstance(p, UserPromptPart)
        )
        part = ToolCallPart(
            info.output_tools[0].name, {"reasoning": "why", "labels": answers[text]}
        )
        return ModelResponse(parts=[part])

    return FunctionModel(fn, model_name="m")


def clf(model="m", prompt="Classify it."):
    return Classifier(model, TAXONOMY, prompt, cache=False)


def evaluation(c):
    rows = [
        {"id": "1", "text": "t1", "labels": ["a"], "split": "dev"},
        {"id": "2", "text": "t2", "labels": ["b"], "split": "dev"},
        {"id": "3", "text": "t3", "labels": ["b"], "split": "dev"},
    ]
    path = Path("gold.jsonl")
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    c = replace(c, model=answering({"t1": ["a"], "t2": ["b"], "t3": ["a"]}))
    return evaluate(c, Gold(path).dev, log=False)


def test_save_writes_the_files_with_trailing_newlines(tmp_path):
    clf().save(tmp_path / "deep" / "bundle")
    d = tmp_path / "deep" / "bundle"
    assert sorted(p.name for p in d.iterdir()) == [
        "classifier.yaml",
        "prompt.md",
        "taxonomy.yaml",
    ]
    assert (d / "classifier.yaml").read_text() == "model: m\n"
    assert (d / "prompt.md").read_text() == "Classify it.\n"
    assert (d / "taxonomy.yaml").read_text().endswith("\n")


def test_round_trip_keeps_digest_labels_and_prompt(tmp_path):
    c = clf(prompt="Classify it.\n")
    c.save(tmp_path / "b")
    loaded = Classifier.load(tmp_path / "b")
    assert loaded.digest == c.digest
    assert loaded.model == "m"
    assert loaded.taxonomy.names == ["a", "b", "off_topic"]
    assert loaded.taxonomy.labels[0].description == "about a"
    assert loaded.prompt == "Classify it.\n"
    assert loaded.evaluation is None


def test_a_model_object_is_saved_by_its_name(tmp_path):
    clf(model=answering({})).save(tmp_path / "b")
    assert (tmp_path / "b" / "classifier.yaml").read_text() == "model: m\n"


def test_evaluation_is_written_and_read_back(tmp_path):
    c = clf()
    ev = evaluation(c)
    c.save(tmp_path / "b", evaluation=ev)
    data = json.loads((tmp_path / "b" / "evaluation.json").read_text())
    assert (tmp_path / "b" / "evaluation.json").read_text().endswith("\n")
    assert set(data) == {
        "split", "n", "score", "metric", "metrics", "digest", "date", "sources",
    }  # fmt: skip
    assert (data["split"], data["n"], data["metric"]) == ("dev", 3, "accuracy")
    assert data["score"] == pytest.approx(2 / 3)
    assert data["metrics"]["exact_match"] == pytest.approx(2 / 3)
    assert data["digest"] == c.digest
    assert data["sources"] == {"hunches-ui": 0, "imported": 0, "unstamped": 3}
    assert data["date"].startswith("20")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        loaded = Classifier.load(tmp_path / "b")
    assert loaded.evaluation == data


def test_editing_the_prompt_by_hand_warns_once(tmp_path):
    c = clf()
    c.save(tmp_path / "b", evaluation=evaluation(c))
    (tmp_path / "b" / "prompt.md").write_text("Something else.\n")
    with pytest.warns(UserWarning, match="no longer matches") as caught:
        Classifier.load(tmp_path / "b")
    assert len(caught) == 1


def test_a_missing_evaluation_is_fine(tmp_path):
    clf().save(tmp_path / "b")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert Classifier.load(tmp_path / "b").evaluation is None


def test_unrelated_files_survive_a_second_save(tmp_path):
    d = tmp_path / "b"
    clf().save(d)
    (d / "notes.txt").write_text("keep me\n")
    clf(prompt="New.").save(d)
    assert (d / "notes.txt").read_text() == "keep me\n"
    assert (d / "prompt.md").read_text() == "New.\n"


def test_the_cache_location_is_not_in_the_bundle(tmp_path):
    Classifier("m", TAXONOMY, "p", cache=tmp_path / "c").save(tmp_path / "b")
    assert (tmp_path / "b" / "classifier.yaml").read_text() == "model: m\n"
    assert Classifier.load(tmp_path / "b").cache is None
    assert Classifier.load(tmp_path / "b", cache=False).cache is False
    assert Classifier.load(tmp_path / "b", cache=tmp_path / "x").cache == tmp_path / "x"


def test_a_script_can_load_and_classify_with_no_gold_and_write_out(tmp_path):
    clf().save(tmp_path / "b")
    loaded = Classifier.load(tmp_path / "b", cache=False)
    loaded = replace(loaded, model=answering({"x": ["a"], "y": ["b"]}))
    out = tmp_path / "out.jsonl"
    preds = loaded.classify(
        [{"id": "1", "text": "x"}, {"id": "2", "text": "y"}], out=out, progress=False
    )
    assert preds.labels == [["a"], ["b"]]
    assert sorted(json.loads(x)["id"] for x in out.read_text().splitlines()) == [
        "1",
        "2",
    ]
    assert not Path("gold.jsonl").exists()
