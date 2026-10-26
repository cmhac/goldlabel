import hashlib
import json
from dataclasses import FrozenInstanceError

import pytest
from pydantic_ai.messages import ModelResponse, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.usage import RequestUsage

from hunches import classifier, cost
from hunches.settings import settings
from hunches.taxonomy import Label, Taxonomy

USAGE = RequestUsage(input_tokens=1, output_tokens=1)


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def taxonomy(mode="multi"):
    return Taxonomy(mode=mode, labels=[Label(name="a"), Label(name="b")])


def out(labels, reasoning="because"):
    return {"reasoning": reasoning, "labels": labels}


def scripted(*outputs, name="m", priced=False):
    """FunctionModel answering call k with outputs[k] (the last one repeats). `calls` collects requests.

    priced=True makes every response cost $0.00021 (1000 in / 100 out tokens of gpt-4o-mini).
    """
    calls = []

    def fn(messages, info: AgentInfo):
        calls.append(messages)
        labels = outputs[min(len(calls), len(outputs)) - 1]
        part = ToolCallPart(info.output_tools[0].name, out(labels))
        if not priced:
            return ModelResponse(parts=[part])
        return ModelResponse(
            parts=[part],
            model_name="gpt-4o-mini",
            provider_name="openai",
            usage=RequestUsage(input_tokens=1000, output_tokens=100),
        )

    return FunctionModel(fn, model_name=name), calls


def clf(model, prompt="prompt", mode="multi", **kw):
    return classifier.Classifier(model, taxonomy(mode), prompt, **kw)


def seed_cache(model_name, prompt, text, labels=("a",), mode="multi"):
    system = classifier.system_prompt(prompt, taxonomy(mode))
    key = cost.cache_key(model_name, system, text)
    cost.cache_put(None, key, out(list(labels), "r"), USAGE)


def seed_ledger(model_name, per_call, calls=2, seconds=None):
    for _ in range(calls):
        cost.record(None, model_name, USAGE, per_call)
    if seconds is not None:
        cost.record_timing(None, "classify", calls * 2, seconds)


# --- per-call logic, kept from before ---------------------------------------------------------


def test_valid_output_and_row_shape():
    model, _ = scripted(["a", "b"])
    p = clf(model).classify(["text"])
    assert p.rows == [
        {
            "id": 0,
            "text": "text",
            "labels": ["a", "b"],
            "reasoning": "because",
            "run": clf(model).digest,
        }
    ]
    assert p.labels == [["a", "b"]] and p.errors == []


def test_off_topic_with_other_label_is_retried():
    model, calls = scripted(["a", "off_topic"], ["off_topic"])
    p = clf(model).classify(["text"])
    assert p.labels == [["off_topic"]]
    assert len(calls) == 2


def test_single_mode_two_labels_rejected_and_retried():
    model, calls = scripted(["a", "b"], ["b"])
    p = clf(model, mode="single").classify(["text"])
    assert p.labels == [["b"]]
    assert len(calls) == 2


def test_unknown_label_is_retried():
    model, calls = scripted(["zzz"], ["a"])
    assert clf(model).classify(["text"]).labels == [["a"]]
    assert len(calls) == 2


def test_gives_up_with_error_row_not_crash_and_is_not_cached():
    model, calls = scripted([])  # an empty label list never validates
    p = clf(model).classify(["text"])
    assert p.labels == [None]
    assert len(p.errors) == 1 and p.errors[0]["error"] and p.errors[0]["id"] == 0
    assert "reasoning" not in p.errors[0]
    entries = (settings.root / "cache").glob("*.json")
    assert [e.name for e in entries if e.name != "cost.json"] == []
    n = len(calls)
    clf(model).classify(["text"])  # asked again, because nothing was cached
    assert len(calls) == 2 * n


def test_second_identical_run_is_all_cache_hits_with_no_added_cost():
    model, calls = scripted(["a"])
    c = clf(model)
    first = c.classify(["x", "y"])
    snapshot = (cost.breakdown(None), cost.items_per_second(None))
    second = c.classify(["x", "y"])
    assert (first.live, first.cached) == (2, 0)
    assert (second.live, second.cached) == (0, 2)
    assert second.labels == first.labels == [["a"], ["a"]]
    assert len(calls) == 2
    assert (cost.breakdown(None), cost.items_per_second(None)) == snapshot


def test_prompt_change_makes_exactly_one_live_call_per_item():
    model, calls = scripted(["a"])
    c1 = clf(model, "prompt one")
    c1.classify(["x", "y", "z"])
    assert len(calls) == 3
    p = c1.with_prompt("prompt two").classify(["x", "y", "z"])
    assert len(calls) == 6 and p.live == 3
    c1.classify(["x", "y", "z"])  # the old prompt still hits
    assert len(calls) == 6


def test_model_change_misses_cache():
    old, old_calls = scripted(["a"], name="old-model")
    new, new_calls = scripted(["b"], name="new-model")
    clf(old).classify(["text"])
    p = clf(new).classify(["text"])
    assert p.labels == [["b"]] and p.cached == 0
    assert len(old_calls) == 1 and len(new_calls) == 1


def test_reasoning_on_live_and_cached():
    model, calls = scripted(["a"])
    first = clf(model).classify(["text"])
    second = clf(model).classify(["text"])
    assert first.rows[0]["reasoning"] == second.rows[0]["reasoning"] == "because"
    assert len(calls) == 1


def test_old_shape_cache_entry_is_a_miss_and_replaced():
    model, calls = scripted(["a"])
    system = classifier.system_prompt("prompt", taxonomy())
    key = cost.cache_key("m", system, "text")
    cost.cache_put(None, key, ["b"], USAGE)
    assert clf(model).classify(["text"]).labels == [["a"]]
    assert len(calls) == 1
    hit = cost.cache_get(None, key)
    assert hit is not None
    assert hit["output"] == {"labels": ["a"], "reasoning": "because"}


def test_cache_false_never_caches():
    model, calls = scripted(["a"])
    c = clf(model, cache=False)
    c.classify(["x"])
    c.classify(["x"])
    assert len(calls) == 2
    assert not (settings.root / "cache").exists()


def test_cache_directory_argument(tmp_path):
    model, calls = scripted(["a"])
    c = clf(model, cache=tmp_path / "elsewhere")
    c.classify(["x"])
    c.classify(["x"])
    assert len(calls) == 1
    assert len(list((tmp_path / "elsewhere").glob("*.json"))) == 2  # entry + cost.json


def test_system_prompt_asks_for_reasoning_first():
    assert (
        "First give a short reasoning (one to three sentences) that names the "
        "evidence in the text, then the labels."
    ) in classifier.system_prompt("prompt", taxonomy())


# --- the object --------------------------------------------------------------------------------


def test_with_prompt_and_with_taxonomy_leave_the_original_alone():
    model, _ = scripted(["a"])
    c1 = clf(model, "one")
    c2 = c1.with_prompt("two")
    c3 = c1.with_taxonomy(Taxonomy(mode="single", labels={"a": "x"}))
    assert c1.prompt == "one" and c2.prompt == "two"
    assert c1.taxonomy == taxonomy() and c3.taxonomy.mode == "single"
    assert len({c1.digest, c2.digest, c3.digest}) == 3
    assert c2.model is model and c2.cache is None
    with pytest.raises(FrozenInstanceError):
        c1.prompt = "three"  # frozen


def test_digest_is_sha256_of_model_and_system_prompt():
    model, _ = scripted(["a"], name="the-model")
    c = clf(model, "p")
    system = classifier.system_prompt("p", taxonomy())
    want = hashlib.sha256(json.dumps(["the-model", system]).encode()).hexdigest()
    assert c.digest == want
    # a model given as a string names itself
    assert (
        clf("anthropic:x", "p").digest
        == hashlib.sha256(json.dumps(["anthropic:x", system]).encode()).hexdigest()
    )


def test_pre006_fixture_digest_and_hit_make_no_model_call():
    import shutil
    from pathlib import Path

    fixtures = Path(__file__).parent / "fixtures" / "pre006"
    shutil.copytree(fixtures, settings.root)
    want = json.loads((fixtures / "expected.json").read_text())["classification"]

    def never(messages, info):
        raise AssertionError("a cache hit must not call the model")

    c = classifier.Classifier(
        FunctionModel(never, model_name=want["model"]),
        Taxonomy.read(settings.root / "taxonomy.yaml"),
        want["prompt"],
    )
    assert c.digest == want["run_digest"]
    p = c.classify([want["text"]])
    assert p.cached == 1 and p.live == 0
    assert p.rows[0]["labels"] == want["labels"]
    assert p.rows[0]["reasoning"] == want["reasoning"]
    assert p.rows[0]["run"] == want["run_digest"]


# --- items -------------------------------------------------------------------------------------


def test_items_as_strings_dicts_and_objects_with_rows():
    model, _ = scripted(["a"])
    c = clf(model)
    assert [r["id"] for r in c.classify(["x", "y"]).rows] == [0, 1]
    rows = [{"id": "p9", "text": "x", "score": 0.5}, {"id": "p8", "text": "y"}]
    got = c.classify(rows).rows
    assert [r["id"] for r in got] == ["p9", "p8"]
    assert got[0]["score"] == 0.5 and list(got[0]) == [
        "id",
        "text",
        "labels",
        "reasoning",
        "run",
        "score",
    ]

    class Holder:
        def __init__(self, rows):
            self.rows = rows

    holder = Holder(rows)
    assert [r["id"] for r in c.classify(holder).rows] == ["p9", "p8"]


# --- sync, async, running loop -------------------------------------------------------------------


def test_sync_call():
    model, _ = scripted(["a"])
    assert clf(model).classify(["x"]).labels == [["a"]]


async def test_sync_call_inside_a_running_loop():
    model, _ = scripted(["a"])
    assert clf(model).classify(["x"]).labels == [["a"]]


async def test_async_call():
    model, _ = scripted(["a"])
    p = await clf(model).aclassify(["x"])
    assert p.labels == [["a"]]


# --- estimate ----------------------------------------------------------------------------------


def test_estimate_numbers_and_no_model_call():
    model, calls = scripted(["a"], name="m")
    seed_cache("m", "prompt", "t0")
    seed_cache("m", "prompt", "t1")
    seed_ledger("m", 0.01, calls=2, seconds=2.0)  # $0.01 a call; 4 items in 2 s = 2/s
    est = clf(model).estimate(["t0", "t1", "t2", "t3", "t4"])
    assert (est.n, est.cached, est.live) == (5, 2, 3)
    assert est.dollars == pytest.approx(0.03)
    assert est.seconds == pytest.approx(1.5)
    assert calls == []
    text = repr(est)
    assert "5 items" in text and "2 cached" in text and "3 live" in text
    assert "$0.0300" in text and "WARNING" not in text


def test_estimate_all_cached_is_zero_not_unknown():
    model, _ = scripted(["a"])
    seed_cache("m", "prompt", "t0")
    est = clf(model).estimate(["t0"])
    assert (est.live, est.dollars, est.seconds) == (0, 0.0, 0.0)


def test_estimate_unknown_price_is_none_with_warning():
    model, _ = scripted(["a"])
    seed_ledger("m", None, calls=1, seconds=1.0)
    est = clf(model).estimate(["t0", "t1"])
    assert est.dollars is None and est.live == 2
    text = repr(est)
    assert "cost ?" in text and "WARNING" in text and "$0" not in text


def test_estimate_without_any_sample_is_unknown_price_and_time():
    model, _ = scripted(["a"])
    est = clf(model).estimate(["t0"])
    assert est.dollars is None and est.seconds is None
    assert "cost ?" in repr(est) and "time ?" in repr(est)


# --- max_cost ----------------------------------------------------------------------------------


def test_max_cost_refuses_before_starting():
    model, calls = scripted(["a"])
    seed_ledger("m", 0.01)
    with pytest.raises(classifier.CostLimit, match="0.03"):
        clf(model).classify(["a", "b", "c"], max_cost=0.02)
    assert calls == []


def test_max_cost_allows_when_estimate_fits():
    model, calls = scripted(["a"], name="gpt-4o-mini", priced=True)
    seed_ledger("gpt-4o-mini", 0.01)
    assert len(clf(model).classify(["a", "b"], max_cost=0.05).rows) == 2
    assert len(calls) == 2


def test_max_cost_refuses_unknown_price():
    model, calls = scripted(["a"])
    with pytest.raises(classifier.CostLimit, match="unknown"):
        clf(model).classify(["a"], max_cost=100.0)
    assert calls == []


def test_max_cost_all_cached_needs_no_price():
    model, calls = scripted(["a"])
    seed_cache("m", "prompt", "a")
    assert clf(model).classify(["a"], max_cost=0.0).cached == 1
    assert calls == []


def test_max_cost_stops_mid_run_and_keeps_finished_rows(tmp_path):
    model, calls = scripted(["a"], name="gpt-4o-mini", priced=True)
    seed_ledger("gpt-4o-mini", 0.00005)  # estimate for 10 items: 0.0005, just fits
    path = tmp_path / "res.jsonl"
    with pytest.raises(classifier.CostLimit, match="0.0005"):
        clf(model).classify(
            [f"t{i}" for i in range(10)], out=path, max_cost=0.0005, concurrency=1
        )
    # each call costs $0.00021: 0.00042 is under, 0.00063 crosses the limit
    assert len(calls) == 3
    assert [json.loads(line)["id"] for line in path.read_text().splitlines()] == [
        0,
        1,
        2,
    ]


def test_max_cost_stops_when_a_live_price_turns_out_unknown(tmp_path):
    model, calls = scripted(["a"], name="m")  # "m" has no price in genai-prices
    seed_ledger("m", 0.01)  # but the ledger says it is known, so the estimate passes
    path = tmp_path / "res.jsonl"
    with pytest.raises(classifier.CostLimit, match="unknown"):
        clf(model).classify(["a", "b", "c"], out=path, max_cost=1.0, concurrency=1)
    assert len(calls) == 1
    assert len(path.read_text().splitlines()) == 1


# --- killing a run (FR-7) ------------------------------------------------------------------------


class Killed(Exception):
    pass


def test_killed_run_resumes_with_only_the_missing_live_calls():
    calls = []

    def fn(messages, info: AgentInfo):
        calls.append(1)
        if len(calls) == 4 and kill:
            raise Killed("killed")
        part = ToolCallPart(info.output_tools[0].name, out(["a"]))
        return ModelResponse(parts=[part])

    kill = True
    c = clf(FunctionModel(fn, model_name="m"))
    items = [f"t{i}" for i in range(6)]
    with pytest.raises(Killed):
        c.classify(items, concurrency=1)
    assert len(calls) == 4  # three finished, the fourth died
    kill = False
    calls.clear()
    p = c.classify(items, concurrency=1)
    assert len(calls) == 3 and (p.live, p.cached) == (3, 3)


# --- out ---------------------------------------------------------------------------------------


def test_out_rows_appended_flushed_and_resume_skips_done(tmp_path):
    model, calls = scripted(["a"])
    c = clf(model)
    path = tmp_path / "sub" / "res.jsonl"
    items = [{"id": "x", "text": "t0", "score": 1}, {"id": "y", "text": "t1"}]
    first = c.classify(items, out=path)
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert sorted(r["id"] for r in lines) == ["x", "y"]
    assert all(r["run"] == c.digest and r["labels"] == ["a"] for r in lines)
    assert len(calls) == 2
    # a rerun neither calls the model nor touches the file
    again = c.classify(items, out=path)
    assert len(path.read_text().splitlines()) == 2 and len(calls) == 2
    assert (again.live, again.cached, again.resumed) == (0, 0, 2)
    assert [r["id"] for r in again.rows] == ["x", "y"]
    assert again.rows[0]["labels"] == first.rows[0]["labels"]
    # a new item is classified and appended
    c.classify([*items, {"id": "z", "text": "t2"}], out=path)
    assert [json.loads(x)["id"] for x in path.read_text().splitlines()][-1] == "z"
    assert len(calls) == 3


def test_out_rows_of_another_run_are_reclassified_and_old_rows_stay(tmp_path):
    model, _ = scripted(["a"], ["b"])
    path = tmp_path / "res.jsonl"
    c1 = clf(model, "one")
    c1.classify(["x"], out=path)
    c2 = c1.with_prompt("two")
    p = c2.classify(["x"], out=path)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert [(r["run"], r["labels"]) for r in rows] == [
        (c1.digest, ["a"]),
        (c2.digest, ["b"]),
    ]
    assert p.resumed == 0 and p.live == 1
    assert "last row" in (classifier.Classifier.aclassify.__doc__ or "")


def test_failed_items_are_not_written_and_are_retried_next_time(tmp_path):
    model, _ = scripted([])
    path = tmp_path / "res.jsonl"
    p = clf(model).classify(["x"], out=path)
    assert len(p.errors) == 1
    assert not path.exists() or path.read_text() == ""
    good, _ = scripted(["a"])
    assert clf(good).classify(["x"], out=path).labels == [["a"]]


# --- Predictions and progress --------------------------------------------------------------------


def test_predictions_repr_counts_and_cost():
    model, _ = scripted(["a"], name="gpt-4o-mini", priced=True)
    seed_cache("gpt-4o-mini", "prompt", "t0")
    p = clf(model).classify(["t0", "t1", "t2"])
    assert (p.live, p.cached, p.resumed) == (2, 1, 0)
    assert p.cost == pytest.approx(0.00042)
    text = repr(p)
    assert "3 items" in text and "2 live" in text and "1 cached" in text
    assert "0 errors" in text and "cost $0.0004" in text


def test_predictions_repr_unknown_cost():
    model, _ = scripted(["a"], name="m")
    p = clf(model).classify(["t0"])
    assert p.cost is None
    assert "cost ?" in repr(p) and "WARNING" in repr(p)


def test_progress_callable_gets_done_total_info():
    model, _ = scripted(["a"], name="gpt-4o-mini", priced=True)
    seed_cache("gpt-4o-mini", "prompt", "t0")
    seen = []
    clf(model).classify(
        ["t0", "t1", "t2"],
        progress=lambda done, total, info: seen.append((done, total, dict(info))),
        concurrency=1,
    )
    assert [(d, t) for d, t, _ in seen] == [(1, 3), (2, 3), (3, 3)]
    last = seen[-1][2]
    assert (last["live"], last["cached"], last["errors"]) == (2, 1, 0)
    assert last["cost"] == pytest.approx(0.00042)


def test_progress_false_is_silent_and_true_prints_one_updating_line(
    capsys, monkeypatch
):
    model, _ = scripted(["a"])
    clf(model).classify(["x", "y"], progress=False)
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    # not a terminal (as under pytest): nothing is printed either
    clf(model).classify(["p", "q"])
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    import sys

    monkeypatch.setattr(sys.stderr, "isatty", lambda: True, raising=False)
    clf(model, "other").classify(["x", "y"], concurrency=1)
    err = capsys.readouterr().err
    assert err.count("\r") == 2 and "2/2" in err and "2 live" in err
    assert err.endswith("\n")
