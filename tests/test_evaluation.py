import hashlib
import json
import re
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage
from pytest import approx

from goldlabel import classifier
from goldlabel._gold_rule import GoldError
from goldlabel.candidates import Candidates
from goldlabel.evaluation import BandReport, Evaluation
from goldlabel.gold import Gold, Sample
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
    path = path or settings.root / "gold.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"taxonomy": None, "rows": rows}))
    return Gold()


def g(id, labels, split="dev", **extra):
    return {"id": id, "text": f"t{id}", "labels": labels, "sample": split, **extra}


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
    ev = c.evaluate(gold["dev"])
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
    ev = clf(model).evaluate(gold["dev"])
    assert ev.n == 1 and ev.skipped_pending == 2
    assert calls == ["t1"]
    assert "2 pending rows skipped" in repr(ev)


def test_default_metric_per_mode_and_target_pass_fail():
    gold, c, _ = five()
    ev = c.evaluate(gold["dev"], target=0.5)
    assert ev.metric == "accuracy"
    assert "PASS" in repr(ev) and "FAIL" not in repr(ev)
    assert "accuracy 0.6000" in repr(ev)
    ev = c.evaluate(gold["dev"], target=0.9)
    assert "FAIL" in repr(ev) and "PASS" not in repr(ev)
    ev = c.evaluate(gold["dev"], metric="micro_f1", target=0.6)
    assert ev.metric == "micro_f1" and "PASS" in repr(ev)
    assert "PASS" not in repr(c.evaluate(gold["dev"])) and "FAIL" not in repr(
        c.evaluate(gold["dev"])
    )


def test_multi_mode_defaults_to_macro_f1():
    model, _ = answering({"t1": ["a"]})
    gold = write_gold([g("1", ["a"])])
    assert clf(model, mode="multi").evaluate(gold["dev"]).metric == "macro_f1"


def test_an_item_that_failed_is_a_disagreement_with_no_prediction():
    model, _ = answering({"t1": ["a"], "t2": []})  # an empty list never validates
    gold = write_gold([g("1", ["a"]), g("2", ["b"])])
    ev = clf(model).evaluate(gold["dev"])
    assert ev.n == 2 and ev.score("accuracy") == approx(0.5)
    [d] = ev.disagreements
    assert d["id"] == "2" and d["gold"] == ["b"] and d["predicted"] is None
    assert d["reasoning"] is None


def test_second_evaluate_is_all_cache_and_a_new_prompt_is_live_again():
    gold, c, calls = five()
    c.evaluate(gold["dev"])
    assert len(calls) == 5
    c.evaluate(gold["dev"])
    assert len(calls) == 5  # SC-3: zero live calls
    c.with_prompt("another prompt").evaluate(gold["dev"])
    assert len(calls) == 10  # one live call per item


def test_invalid_gold_labels_raise_with_ids_before_any_call():
    model, calls = answering({})
    gold = write_gold([g("1", ["a"]), g("2", ["zzz"]), g("3", ["a", "b"])])
    with pytest.raises(ValueError, match=r"\['2', '3'\].*orphaned"):
        clf(model).evaluate(gold["dev"])
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
    ev = clf(model).evaluate(gold["dev"])
    assert ev.n == 4 and ev.score("accuracy") == 1
    assert ev.sources == {"goldlabel-ui": 1, "imported": 1, "unstamped": 2}
    assert "goldlabel-ui 1, imported 1, unstamped 2" in repr(ev)


def test_repr_shows_the_per_label_table():
    gold, c, _ = five()
    text = repr(c.evaluate(gold["dev"]))
    assert "macro_f1 0.6111" in text and "micro_f1 0.6000" in text
    assert re.search(r"\ba\s+1\.00\s+0\.50\s+0\.67\s+2\s+1\b", text)
    assert re.search(r"\bb\s+0\.50\s+0\.50\s+0\.50\s+2\s+2\b", text)
    assert re.search(r"\boff_topic\s+0\.50\s+1\.00\s+0\.67\s+1\s+2\b", text)


def test_write_stores_the_numbers_as_json(tmp_path):
    gold, c, _ = five()
    ev = c.evaluate(gold["dev"], target=0.5)
    ev.write(tmp_path / "out" / "ev.json")
    data = json.loads((tmp_path / "out" / "ev.json").read_text())
    assert data["n"] == 5 and data["digest"] == c.digest
    assert data["metric"] == "accuracy" and data["score"] == approx(0.6)
    assert data["metrics"]["macro_f1"] == approx(11 / 18)
    assert data["disagreements"][0]["id"] in ("2", "4")
    datetime.fromisoformat(data["time"])


def test_the_module_functions_are_gone():
    import goldlabel

    for name in ("evaluate", "aevaluate", "band_sample", "eval_log", "EvalLog"):
        assert not hasattr(goldlabel, name), name
    assert goldlabel.Sample is Sample


async def test_aevaluate_matches_evaluate():
    gold, c, _ = five()
    ev = await c.aevaluate(gold["dev"])
    assert ev.score("accuracy") == approx(0.6)


# --- the evaluation log --------------------------------------------------------------------------


def log_rows(path=None):
    path = path or settings.root / "evals.jsonl"
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_each_call_appends_one_line_with_every_field():
    gold, c, _ = five()
    before = datetime.now(UTC)
    c.evaluate(gold["dev"], target=0.5)
    [row] = log_rows()
    assert set(row) == {
        "time", "samples", "rows_digest", "n", "gold", "model", "digest", "prompt",
        "taxonomy", "metric", "target", "score", "metrics", "dollars", "live_calls",
        "cached_calls", "goldlabel", "disagreements", "skipped_pending",
    }  # fmt: skip
    assert before <= datetime.fromisoformat(row["time"])
    assert (row["samples"], row["n"], row["model"]) == (["dev"], 5, "m")
    assert row["gold"] == str(gold.path)
    by_hand = [
        ["1", ["a"]],
        ["2", ["a"]],
        ["3", ["b"]],
        ["4", ["b"]],
        ["5", ["off_topic"]],
    ]
    assert (
        row["rows_digest"] == hashlib.sha256(json.dumps(by_hand).encode()).hexdigest()
    )
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


def test_an_identical_rerun_writes_no_line_and_a_new_target_does():
    gold, c, calls = five()
    first = c.evaluate(gold["dev"])
    text = (settings.root / "evals.jsonl").read_text()
    again = c.evaluate(gold["dev"])
    assert len(calls) == 5 and again.score() == first.score()
    assert (settings.root / "evals.jsonl").read_text() == text  # nothing appended
    c.evaluate(gold["dev"], target=0.9)
    assert len(log_rows()) == 2 and len(calls) == 5
    assert (log_rows()[1]["live_calls"], log_rows()[1]["cached_calls"]) == (0, 5)
    assert (settings.root / "evals.jsonl").read_text().startswith(text)


def test_there_is_no_way_to_skip_or_move_the_log():
    gold, c, calls = five()
    with pytest.raises(TypeError):
        c.evaluate(gold["dev"], log=False)
    for bad in (gold.all, gold.pending):
        with pytest.raises(GoldError, match="evaluate a Sample"):
            c.evaluate(bad)
    assert calls == [] and not (settings.root / "evals.jsonl").exists()


def test_a_combination_is_logged_with_every_sample_in_it():
    model, _ = answering({"t1": ["a"], "t2": ["b"]})
    gold = write_gold([g("1", ["a"]), g("2", ["b"], split="test")])
    ev = clf(model).evaluate(gold["dev"] + gold["test"])
    assert ev.samples == ("dev", "test")
    assert log_rows()[0]["samples"] == ["dev", "test"]
    assert clf(model).evaluate(gold["test"]).samples == ("test",)
    assert log_rows()[1]["samples"] == ["test"]


def test_priced_calls_log_dollars():
    model, _ = answering({"t1": ["a"]}, name="gpt-4o-mini", priced=True)
    gold = write_gold([g("1", ["a"])])
    clf(model).evaluate(gold["dev"])
    assert log_rows()[0]["dollars"] == approx(
        0.00021
    )  # 1000 in / 100 out of gpt-4o-mini


def test_a_sample_shows_how_often_exactly_it_was_evaluated():
    model, _ = answering({"t1": ["a"], "t2": ["b"]})
    gold = write_gold([g("1", ["a"]), g("2", ["b"], split="test")])
    c = clf(model)
    assert repr(gold["test"]).splitlines()[0].endswith("; not evaluated")
    c.evaluate(gold["dev"])
    c.evaluate(gold["test"])
    c.evaluate(gold["test"])  # identical: not a second look
    c.evaluate(gold["test"], target=0.5)  # a new line, the same prompt
    c.with_prompt("other").evaluate(gold["test"])
    assert len(log_rows()) == 4
    assert (
        repr(gold["test"]).splitlines()[0].endswith("; evaluated 3 times (2 prompts)")
    )
    assert repr(gold["dev"]).splitlines()[0].endswith("; evaluated 1 time (1 prompt)")
    c.evaluate(gold["dev"] + gold["test"])  # a combination counts for itself only
    assert repr(gold["dev"]).splitlines()[0].endswith("; evaluated 1 time (1 prompt)")
    both = gold["dev"] + gold["test"]
    assert repr(both).splitlines()[0].endswith("; evaluated 1 time (1 prompt)")


def test_counts_are_per_gold_file_and_older_lines_count_for_nothing():
    model, _ = answering({"t1": ["a"]})
    gold = write_gold([g("1", ["a"], split="test")])
    other = Gold(name="b")
    other.import_rows([{"id": "1", "text": "t1", "labels": ["a"]}], "test")
    clf(model).evaluate(other["test"])
    assert log_rows()[0]["gold"] == str(other.path)
    assert repr(gold["test"]).splitlines()[0].endswith("; not evaluated")
    with (settings.root / "evals.jsonl").open("a") as f:
        old = {"split": "test", "gold": str(gold.path), "digest": "x", "model": "m"}
        f.write(json.dumps(old) + "\n")
        f.write(json.dumps({"event": "test_folded", "rows": 1}) + "\n")
    assert repr(gold["test"]).splitlines()[0].endswith("; not evaluated")
    assert repr(other["test"]).splitlines()[0].endswith("; evaluated 1 time (1 prompt)")


def test_a_sample_made_before_its_labels_sees_them():
    model, _ = answering({"t1": ["a"], "t2": ["b"]})
    gold = write_gold([g("1", None), g("2", None)])
    dev = gold["dev"]
    write_gold([g("1", ["a"]), g("2", ["b"])])  # a person labelled them meanwhile
    ev = clf(model).evaluate(dev)
    assert (ev.n, ev.skipped_pending, ev.score()) == (2, 0, 1.0)


async def test_the_sync_methods_work_inside_a_running_loop():
    gold, c, _ = five()
    assert c.evaluate(gold["dev"]).score("accuracy") == approx(0.6)
    report = clf(answering(BAND_ANSWERS)[0]).band_sample(banded(), per_band=1)
    assert sum(r["n"] for r in report.rows) == 3


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
    report = clf(model).band_sample(banded(), per_band=30)
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


def test_band_sample_takes_at_most_per_band_in_the_id_order_with_no_seed():
    model, calls = answering({f"c{i}": ["a"] for i in range(10)})
    rows = [cand(i, 0.61) for i in range(10)]
    one = clf(model).band_sample(Candidates(rows), per_band=3)
    assert one.rows == [{"band": "0.600-0.625", "n": 3, "off_topic": 0, "rate": 0.0}]
    ids = [f"c{i}" for i in range(10)]
    by_hand = sorted(ids, key=lambda i: hashlib.sha256(f"\0{i}".encode()).hexdigest())
    assert sorted(calls) == sorted(by_hand[:3])
    calls.clear()
    again = clf(model, prompt="other").band_sample(Candidates(rows), per_band=3)
    assert again.rows == one.rows and sorted(calls) == sorted(by_hand[:3])
    with pytest.raises(TypeError):
        clf(model).band_sample(Candidates(rows), seed=1)


async def test_aband_sample_matches_band_sample():
    model, _ = answering(BAND_ANSWERS)
    report = await clf(model).aband_sample(banded(), per_band=30)
    assert [r["n"] for r in report.rows] == [4, 2, 3]


def test_band_sample_off_topic_means_exactly_off_topic():
    model, _ = answering({"c0": ["off_topic"], "c1": ["a", "b"]})
    c = clf(model, mode="multi")
    report = c.band_sample(Candidates([cand(0, 0.61), cand(1, 0.61)]))
    assert report.rows[0]["off_topic"] == 1 and report.rows[0]["rate"] == 0.5


def test_band_sample_refuses_a_list_without_similarity_scores():
    model, calls = answering({})
    other = Candidates([{"id": "a", "text": "t"}], source="all")
    with pytest.raises(ValueError, match="band_sample needs similarity scores.*all"):
        clf(model).band_sample(other)
    assert calls == []


def test_a_note_on_a_gold_row_never_reaches_the_model():
    # guard (013): green before the notes feature too, and it keeps the notes out of prompts
    gold = write_gold([g("1", ["a"], note="secret edge case"), g("2", ["b"])])
    model, calls = answering({"t1": ["a"], "t2": ["b"]})
    clf(model).evaluate(gold["dev"])
    assert sorted(calls) == [
        "t1",
        "t2",
    ]  # items run concurrently: arrival order is not fixed


@pytest.mark.parametrize("bad", [0, -1, 1.5, True])
def test_band_sample_refuses_a_per_band_below_one(bad):
    model, calls = answering(BAND_ANSWERS)
    with pytest.raises(ValueError, match="per_band"):
        clf(model).band_sample(banded(), per_band=bad)
    assert calls == []


def test_the_log_line_records_the_disagreements_without_their_text():
    gold, c, calls = five()
    c.evaluate(gold["dev"])
    [row] = log_rows()
    assert row["disagreements"] == [
        {"id": "2", "gold": ["a"], "predicted": ["b"], "reasoning": "why t2"},
        {"id": "4", "gold": ["b"], "predicted": ["off_topic"], "reasoning": "why t4"},
    ]
    assert all("text" not in d for d in row["disagreements"])
    text = (settings.root / "evals.jsonl").read_text()
    c.evaluate(gold["dev"])  # an identical rerun: no line, no model call
    assert (settings.root / "evals.jsonl").read_text() == text and len(calls) == 5
    replace(c, prompt="another prompt").evaluate(gold["dev"])
    assert len(log_rows()) == 2 and "disagreements" in log_rows()[1]


def test_an_item_that_failed_is_logged_with_no_prediction():
    model, _ = answering({"t1": ["a"], "t2": []})
    gold = write_gold([g("1", ["a"]), g("2", ["b"])])
    clf(model).evaluate(gold["dev"])
    [row] = log_rows()
    assert row["disagreements"] == [
        {"id": "2", "gold": ["b"], "predicted": None, "reasoning": None}
    ]


def test_a_line_written_before_disagreements_were_logged_still_counts():
    gold, c, _ = five()
    c.evaluate(gold["dev"])
    [row] = log_rows()
    old = {k: v for k, v in row.items() if k != "disagreements"}
    with (settings.root / "evals.jsonl").open("a") as f:
        f.write(json.dumps(old) + "\n")
    assert "evaluated 2 times (1 prompt)" in repr(gold["dev"])
