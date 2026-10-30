import json
import re
from datetime import UTC, datetime

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from pytest import approx

from goldlabel import classifier
from goldlabel.candidates import Candidates
from goldlabel.evaluation import (
    BandReport,
    EvalLog,
    Evaluation,
    aevaluate,
    band_sample,
    eval_log,
    evaluate,
)
from goldlabel.gold import Gold
from goldlabel.settings import settings
from goldlabel.taxonomy import Label, Taxonomy


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def taxonomy(mode="single"):
    return Taxonomy(
        mode=mode, labels=[Label(name="a", description="about a"), Label(name="b")]
    )


def answering(answers: dict, name="m", priced=False):
    """FunctionModel that answers by the item text. `calls` collects the texts asked."""
    calls = []

    def fn(messages, info: AgentInfo):
        text = next(
            p.content
            for m in reversed(messages)
            for p in reversed(m.parts)
            if isinstance(p, UserPromptPart)
        )
        calls.append(text)
        labels = answers[text]
        part = ToolCallPart(
            info.output_tools[0].name, {"reasoning": f"why {text}", "labels": labels}
        )
        if not priced:
            return ModelResponse(parts=[part])
        return ModelResponse(
            parts=[part],
            model_name="gpt-4o-mini",
            provider_name="openai",
            usage=RequestUsage(input_tokens=1000, output_tokens=100),
        )

    return FunctionModel(fn, model_name=name), calls


def clf(model, prompt="prompt", mode="single"):
    return classifier.Classifier(model, taxonomy(mode), prompt)


def write_gold(rows, path=None):
    path = path or settings.root / "gold.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return Gold(path)


def g(id, labels, split="dev", **extra):
    return {"id": id, "text": f"t{id}", "labels": labels, "split": split, **extra}


# gold a,a,b,b,off_topic  vs predicted a,b,b,off_topic,off_topic
# exact 3/5, macro 11/18, micro 6/10; disagreements are items 2 and 4
FIVE = [
    g("1", ["a"]),
    g("2", ["a"]),
    g("3", ["b"]),
    g("4", ["b"]),
    g("5", ["off_topic"]),
]
FIVE_ANSWERS = {
    "t1": ["a"],
    "t2": ["b"],
    "t3": ["b"],
    "t4": ["off_topic"],
    "t5": ["off_topic"],
}


def five():
    model, calls = answering(FIVE_ANSWERS)
    return write_gold(FIVE), clf(model), calls


def test_metrics_and_disagreements_match_hand_computed_values():
    gold, c, _ = five()
    ev = evaluate(c, gold.dev)
    assert isinstance(ev, Evaluation)
    assert ev.n == 5 and ev.skipped_pending == 0
    assert ev.score("accuracy") == approx(0.6)
    assert ev.score("macro_f1") == approx(11 / 18)
    assert ev.score("micro_f1") == approx(0.6)
    assert ev.metrics.per_label["a"].recall == approx(0.5)
    assert ev.digest == c.digest
    assert sorted(ev.disagreements, key=lambda d: d["id"]) == [
        {
            "id": "2",
            "text": "t2",
            "gold": ["a"],
            "predicted": ["b"],
            "reasoning": "why t2",
        },
        {
            "id": "4",
            "text": "t4",
            "gold": ["b"],
            "predicted": ["off_topic"],
            "reasoning": "why t4",
        },
    ]


def test_pending_rows_are_skipped_and_counted():
    model, calls = answering({"t1": ["a"]})
    gold = write_gold([g("1", ["a"]), g("2", None), g("3", [])])
    ev = evaluate(clf(model), gold.all)
    assert ev.n == 1 and ev.skipped_pending == 2
    assert calls == ["t1"]
    assert "2 pending rows skipped" in repr(ev)


def test_default_metric_per_mode_and_target_pass_fail():
    gold, c, _ = five()
    ev = evaluate(c, gold.dev, target=0.5)
    assert ev.metric == "accuracy"
    assert "PASS" in repr(ev) and "FAIL" not in repr(ev)
    assert "accuracy 0.6000" in repr(ev)
    ev = evaluate(c, gold.dev, target=0.9)
    assert "FAIL" in repr(ev) and "PASS" not in repr(ev)
    ev = evaluate(c, gold.dev, metric="micro_f1", target=0.6)
    assert ev.metric == "micro_f1" and "PASS" in repr(ev)
    assert "PASS" not in repr(evaluate(c, gold.dev)) and "FAIL" not in repr(
        evaluate(c, gold.dev)
    )


def test_multi_mode_defaults_to_macro_f1():
    model, _ = answering({"t1": ["a"]})
    gold = write_gold([g("1", ["a"])])
    assert evaluate(clf(model, mode="multi"), gold.dev).metric == "macro_f1"


def test_an_item_that_failed_is_a_disagreement_with_no_prediction():
    model, _ = answering({"t1": ["a"], "t2": []})  # an empty list never validates
    gold = write_gold([g("1", ["a"]), g("2", ["b"])])
    ev = evaluate(clf(model), gold.dev)
    assert ev.n == 2 and ev.score("accuracy") == approx(0.5)
    [d] = ev.disagreements
    assert d["id"] == "2" and d["gold"] == ["b"] and d["predicted"] is None
    assert d["reasoning"] is None


def test_second_evaluate_is_all_cache_and_a_new_prompt_is_live_again():
    gold, c, calls = five()
    evaluate(c, gold.dev)
    assert len(calls) == 5
    evaluate(c, gold.dev)
    assert len(calls) == 5  # SC-3: zero live calls
    evaluate(c.with_prompt("another prompt"), gold.dev)
    assert len(calls) == 10  # one live call per item


def test_invalid_gold_labels_raise_with_ids_before_any_call():
    model, calls = answering({})
    gold = write_gold([g("1", ["a"]), g("2", ["zzz"]), g("3", ["a", "b"])])
    with pytest.raises(ValueError, match=r"\['2', '3'\].*orphaned"):
        evaluate(clf(model), gold.dev)
    assert calls == [] and not (settings.root / "evals.jsonl").exists()


def test_rows_without_a_stamp_and_imported_rows_are_accepted_and_counted():
    model, _ = answering({"t1": ["a"], "t2": ["a"], "t3": ["b"], "t4": ["b"]})
    gold = write_gold(
        [
            g("1", ["a"]),
            g("2", ["a"], labelled_by="imported"),
            g("3", ["b"], labelled_by="goldlabel-ui"),
            g("4", ["b"], labelled_by="hand", extra="kept"),
        ]
    )
    ev = evaluate(clf(model), gold.dev)
    assert ev.n == 4 and ev.score("accuracy") == 1
    assert ev.sources == {"goldlabel-ui": 1, "imported": 1, "unstamped": 2}
    assert "goldlabel-ui 1, imported 1, unstamped 2" in repr(ev)


def test_repr_shows_the_per_label_table():
    gold, c, _ = five()
    text = repr(evaluate(c, gold.dev))
    assert "macro_f1 0.6111" in text and "micro_f1 0.6000" in text
    assert re.search(r"\ba\s+1\.00\s+0\.50\s+0\.67\s+2\s+1\b", text)
    assert re.search(r"\bb\s+0\.50\s+0\.50\s+0\.50\s+2\s+2\b", text)
    assert re.search(r"\boff_topic\s+0\.50\s+1\.00\s+0\.67\s+1\s+2\b", text)


def test_write_stores_the_numbers_as_json(tmp_path):
    gold, c, _ = five()
    ev = evaluate(c, gold.dev, target=0.5)
    ev.write(tmp_path / "out" / "ev.json")
    data = json.loads((tmp_path / "out" / "ev.json").read_text())
    assert data["n"] == 5 and data["digest"] == c.digest
    assert data["metric"] == "accuracy" and data["score"] == approx(0.6)
    assert data["metrics"]["macro_f1"] == approx(11 / 18)
    assert data["disagreements"][0]["id"] in ("2", "4")
    datetime.fromisoformat(data["time"])


async def test_aevaluate_matches_evaluate():
    gold, c, _ = five()
    ev = await aevaluate(c, gold.dev)
    assert ev.score("accuracy") == approx(0.6)


# --- the evaluation log --------------------------------------------------------------------------


def log_rows(path=None):
    path = path or settings.root / "evals.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_each_call_appends_one_line_with_every_field():
    gold, c, _ = five()
    before = datetime.now(UTC)
    evaluate(c, gold.dev, target=0.5)
    [row] = log_rows()
    assert set(row) == {
        "time", "split", "n", "gold", "model", "digest", "prompt", "taxonomy", "metric",
        "target", "score", "metrics", "dollars", "live_calls", "cached_calls", "goldlabel",
    }  # fmt: skip
    assert before <= datetime.fromisoformat(row["time"])
    assert (row["split"], row["n"], row["model"]) == ("dev", 5, "m")
    assert row["gold"] == str(gold.path)
    assert row["digest"] == c.digest and row["prompt"] == "prompt"
    assert row["taxonomy"] == {
        "mode": "single",
        "labels": [
            {"name": "a", "description": "about a"},
            {"name": "b", "description": ""},
        ],
    }
    assert (row["metric"], row["target"]) == ("accuracy", 0.5)
    assert row["score"] == approx(0.6)
    assert row["metrics"]["macro_f1"] == approx(11 / 18)
    assert row["metrics"]["per_label"]["a"]["recall"] == approx(0.5)
    assert row["dollars"] is None or row["dollars"] == 0  # unpriced FunctionModel
    assert (row["live_calls"], row["cached_calls"]) == (5, 0)
    assert row["goldlabel"] == "0.1.0"


def test_log_is_append_only_and_records_cached_calls():
    gold, c, _ = five()
    evaluate(c, gold.dev)
    first = (settings.root / "evals.jsonl").read_text()
    evaluate(c, gold.dev)
    text = (settings.root / "evals.jsonl").read_text()
    assert text.startswith(first) and len(log_rows()) == 2
    assert (log_rows()[1]["live_calls"], log_rows()[1]["cached_calls"]) == (0, 5)


def test_log_false_writes_nothing_and_a_path_moves_it(tmp_path):
    gold, c, _ = five()
    evaluate(c, gold.dev, log=False)
    assert not (settings.root / "evals.jsonl").exists()
    evaluate(c, gold.dev, log=tmp_path / "deep" / "dir" / "mine.jsonl")
    assert len(log_rows(tmp_path / "deep" / "dir" / "mine.jsonl")) == 1
    assert not (settings.root / "evals.jsonl").exists()


def test_a_set_spanning_both_splits_is_logged_as_mixed():
    model, _ = answering({"t1": ["a"], "t2": ["b"]})
    gold = write_gold([g("1", ["a"]), g("2", ["b"], split="test")])
    evaluate(clf(model), gold.all)
    assert log_rows()[0]["split"] == "mixed"
    evaluate(clf(model), gold.test)
    assert log_rows()[1]["split"] == "test"


def test_priced_calls_log_dollars():
    model, _ = answering({"t1": ["a"]}, name="gpt-4o-mini", priced=True)
    gold = write_gold([g("1", ["a"])])
    evaluate(clf(model), gold.dev)
    assert log_rows()[0]["dollars"] == approx(
        0.00021
    )  # 1000 in / 100 out of gpt-4o-mini


def test_eval_log_counts_test_evaluations_and_distinct_prompts():
    model, _ = answering({"t1": ["a"], "t2": ["b"]})
    gold = write_gold([g("1", ["a"]), g("2", ["b"], split="test")])
    c = clf(model)
    evaluate(c, gold.dev)
    evaluate(c, gold.test)
    evaluate(c, gold.test)
    evaluate(c.with_prompt("other"), gold.test)
    log = eval_log()
    assert isinstance(log, EvalLog) and len(log.rows) == 4
    text = repr(log)
    assert "test split evaluated 3 times (2 distinct prompts)" in text
    first = log.rows[0]
    assert first["digest"][:8] in text and "1.0000" in text and "dev" in text


def test_fold_events_are_kept_apart_and_reset_the_test_count(tmp_path):
    path = tmp_path / "evals.jsonl"
    ev = {"split": "test", "n": 2, "score": 0.5, "digest": "abcdef012", "model": "m"}
    lines = [
        {**ev, "time": "2026-02-01T00:00:00+00:00"},
        {"event": "test_folded", "time": "2026-02-02T00:00:00+00:00", "rows": 40},
        {**ev, "time": "2026-02-03T00:00:00+00:00"},
    ]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    log = eval_log(path)
    assert [r["time"][:10] for r in log.rows] == ["2026-02-01", "2026-02-03"]
    assert [f["rows"] for f in log.folds] == [40]
    text = repr(log)
    assert "test split evaluated 1 times (1 distinct prompts)" in text
    assert "40 test rows folded into dev" in text
    assert set(log.to_polars().columns) == {
        "time",
        "split",
        "n",
        "score",
        "digest",
        "model",
    }  # no event columns


def test_eval_log_with_a_path_and_when_empty(tmp_path):
    assert eval_log().rows == []
    assert "test split evaluated 0 times (0 distinct prompts)" in repr(
        eval_log(tmp_path / "x.jsonl")
    )


# --- band_sample ---------------------------------------------------------------------------------


def cand(i, sim):
    return {"id": f"c{i}", "text": f"c{i}", "max_similarity": sim, "best_seed": "s"}


def banded():
    # band 0.600-0.625: 4 items; band 0.700-0.725: 2 items; band 0.750+: 3 items; one below the floor
    rows = [cand(i, 0.61) for i in range(4)]
    rows += [cand(i, 0.71) for i in range(4, 6)]
    rows += [cand(i, 0.80) for i in range(6, 9)]
    rows += [cand(9, 0.50)]
    return Candidates(rows)


BAND_ANSWERS = {
    **{f"c{i}": ["off_topic"] for i in (0, 1, 4, 6)},
    **{f"c{i}": ["a"] for i in (2, 3, 5, 7, 8, 9)},
}


def test_band_sample_rates_match_hand_computed_values():
    model, calls = answering(BAND_ANSWERS, name="gpt-4o-mini", priced=True)
    report = band_sample(clf(model), banded(), per_band=30, seed=1)
    assert isinstance(report, BandReport)
    # per_band 30 is larger than every band, so each band is taken whole
    assert report.rows == [
        {"band": "0.600-0.625", "n": 4, "off_topic": 2, "rate": 0.5},
        {"band": "0.700-0.725", "n": 2, "off_topic": 1, "rate": 0.5},
        {"band": "0.750+", "n": 3, "off_topic": 1, "rate": 1 / 3},
    ]
    assert sorted(calls) == sorted(
        f"c{i}" for i in range(9)
    )  # the item below the floor is skipped
    assert report.cost == approx(9 * 0.00021)
    assert not (settings.root / "evals.jsonl").exists()
    assert "0.600-0.625" in repr(report) and "50%" in repr(report)


def test_band_sample_takes_at_most_per_band_and_is_deterministic_for_a_seed():
    model, calls = answering({f"c{i}": ["a"] for i in range(10)})
    rows = [cand(i, 0.61) for i in range(10)]
    c = clf(model)
    one = band_sample(c, Candidates(rows), per_band=3, seed=7)
    assert one.rows == [{"band": "0.600-0.625", "n": 3, "off_topic": 0, "rate": 0.0}]
    first = sorted(set(calls))
    assert len(first) == 3
    calls.clear()
    again = band_sample(
        clf(model, prompt="other"), Candidates(rows), per_band=3, seed=7
    )
    assert again.rows == one.rows and sorted(calls) == first
    calls.clear()
    band_sample(clf(model, prompt="third"), Candidates(rows), per_band=3, seed=8)
    assert sorted(calls) != first


def test_band_sample_off_topic_means_exactly_off_topic():
    model, _ = answering({"c0": ["off_topic"], "c1": ["a", "b"]})
    c = clf(model, mode="multi")
    report = band_sample(c, Candidates([cand(0, 0.61), cand(1, 0.61)]))
    assert report.rows[0]["off_topic"] == 1 and report.rows[0]["rate"] == 0.5


def test_band_sample_refuses_a_list_without_similarity_scores():
    model, calls = answering({})
    other = Candidates([{"id": "a", "text": "t"}], source="all")
    with pytest.raises(ValueError, match="band_sample needs similarity scores.*all"):
        band_sample(clf(model), other)
    assert calls == []
