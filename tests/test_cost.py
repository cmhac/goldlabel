import importlib
import json
import shutil
import threading
from pathlib import Path

import pytest
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RequestUsage

from hunches.settings import settings

cost = importlib.import_module("hunches.cost")  # `hunches.cost` is the function

FIXTURES = Path(__file__).parent / "fixtures" / "pre006"


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_cache_key_changes_with_each_part():
    base = cost.cache_key("m", "p", "t")
    assert base == cost.cache_key("m", "p", "t")
    assert (
        len({base, cost.cache_key("m2", "p", "t"), cost.cache_key("m", "p2", "t")}) == 3
    )
    assert base != cost.cache_key("m", "p", "t2")
    assert cost.cache_key("ab", "c", "") != cost.cache_key("a", "bc", "")


def test_cache_round_trip_and_hit_changes_no_totals():
    key = cost.cache_key("m", "p", "t")
    assert cost.cache_get(None, key) is None
    usage = RequestUsage(input_tokens=10, output_tokens=2)
    cost.record(None, "m", usage, 0.5)
    cost.cache_put(None, key, ["a"], usage)
    before = (
        cost.total(None),
        json.loads((settings.root / "cache" / "cost.json").read_text()),
    )
    hit = cost.cache_get(None, key)
    assert hit == {"output": ["a"], "usage": {"input_tokens": 10, "output_tokens": 2}}
    after = (
        cost.total(None),
        json.loads((settings.root / "cache" / "cost.json").read_text()),
    )
    assert before == after


def test_record_known_price_and_persistence():
    cost.record(None, "m", RequestUsage(input_tokens=100, output_tokens=10), 0.25)
    cost.record(None, "m", RequestUsage(input_tokens=50, output_tokens=5), 0.25)
    assert cost.total(None) == (0.5, False)
    # a fresh read from disk sees the same data
    assert cost.breakdown(None)["m"] == {
        "input_tokens": 150,
        "output_tokens": 15,
        "calls": 2,
        "dollars": 0.5,
    }


def test_unknown_price_is_null_and_flagged():
    cost.record(None, "known", RequestUsage(input_tokens=1, output_tokens=1), 1.0)
    cost.record(None, "mystery", RequestUsage(input_tokens=1, output_tokens=1), None)
    cost.record(None, "mystery", RequestUsage(input_tokens=1, output_tokens=1), 2.0)
    assert cost.breakdown(None)["mystery"]["dollars"] is None
    assert (
        json.loads((settings.root / "cache" / "cost.json").read_text())["models"][
            "mystery"
        ]["dollars"]
        is None
    )
    assert cost.total(None) == (1.0, True)


def test_testmodel_price_is_unknown():
    result = Agent(TestModel()).run_sync("hi")
    dollars = cost.messages_dollars(result.new_messages())
    assert dollars is None
    cost.record(None, "test", result.usage, dollars)
    assert cost.total(None) == (0.0, True)
    assert cost.breakdown(None)["test"]["input_tokens"] > 0


def test_known_price_from_genai_prices():
    # claude-haiku-4-5 is known to genai-prices; assert only that it is a positive number
    from pydantic_ai.messages import ModelResponse, TextPart

    response = ModelResponse(
        parts=[TextPart("x")],
        usage=RequestUsage(input_tokens=1000, output_tokens=100),
        model_name="claude-haiku-4-5",
        provider_name="anthropic",
    )
    dollars = cost.messages_dollars([response])
    assert dollars is not None and dollars > 0


def test_timing():
    assert cost.items_per_second(None) is None
    cost.record_timing(None, "dev", 10, 2.0)
    cost.record_timing(None, "dev", 10, 3.0)
    cost.record_timing(None, "band", 5, 5.0)
    assert cost.items_per_second(None, "dev") == 4.0
    assert cost.items_per_second(None) == 25 / 10
    assert cost.total(None) == (0.0, False)  # timings never touch dollars


UNKNOWN = RequestUsage(input_tokens=1, output_tokens=1)


def test_ledger_lives_in_the_cache_directory(tmp_path):
    cache = tmp_path / "elsewhere"
    cost.record(cache, "m", RequestUsage(input_tokens=4, output_tokens=1), 0.25)
    cost.record_timing(cache, "dev", 2, 1.0)
    assert json.loads((cache / "cost.json").read_text()) == {
        "models": {
            "m": {"input_tokens": 4, "output_tokens": 1, "calls": 1, "dollars": 0.25}
        },
        "timings": [{"label": "dev", "n_items": 2, "seconds": 1.0}],
    }
    assert [p.name for p in cache.iterdir()] == ["cost.json"]  # no temp file left
    assert cost.total(cache) == (0.25, False)
    assert cost.items_per_second(cache, "dev") == 2.0
    assert cost.per_call_dollars(cache, "m") == (0.25, True)
    assert cost.per_call_dollars(cache, "other") == (None, False)
    assert not (settings.root / "cache").exists()


def test_entries_use_the_sha256_layout_in_the_given_directory(tmp_path):
    key = cost.cache_key("m", "p", "t")
    cost.cache_put(tmp_path / "c", key, {"labels": ["a"]}, UNKNOWN)
    assert json.loads((tmp_path / "c" / f"{key}.json").read_text()) == {
        "output": {"labels": ["a"]},
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    hit = cost.cache_get(tmp_path / "c", key)
    assert hit is not None and hit["output"] == {"labels": ["a"]}
    assert cost.cache_get(tmp_path / "other", key) is None


def test_cache_false_writes_nothing_and_reads_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "root", tmp_path / "root")
    key = cost.cache_key("m", "p", "t")
    cost.cache_put(False, key, ["a"], UNKNOWN)
    cost.record(False, "m", UNKNOWN, 1.0)
    cost.record_timing(False, "dev", 1, 1.0)
    assert cost.cache_get(False, key) is None
    assert cost.total(False) == (0.0, False)
    assert cost.breakdown(False) == {}
    assert cost.items_per_second(False) is None
    assert cost.per_call_dollars(False, "m") == (None, False)
    assert not (tmp_path / "root").exists()
    assert list(tmp_path.iterdir()) == []
    # and a real entry in the default place is invisible through False
    cost.cache_put(None, key, ["a"], UNKNOWN)
    assert cost.cache_get(None, key) is not None
    assert cost.cache_get(False, key) is None


def test_cache_dir_resolves_none_to_settings_root_and_keeps_false(
    tmp_path, monkeypatch
):
    assert cost.cache_dir(None) == Path(".hunches") / "cache"
    monkeypatch.setattr(settings, "root", tmp_path / "r")
    assert cost.cache_dir(None) == tmp_path / "r" / "cache"
    assert cost.cache_dir(tmp_path / "x") == tmp_path / "x"
    assert cost.cache_dir(False) is False
    cost.record(None, "m", UNKNOWN, 0.5)
    assert (tmp_path / "r" / "cache" / "cost.json").exists()


def test_pre006_ledger_in_the_root_is_not_read(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "root", tmp_path / "old")
    shutil.copytree(FIXTURES, tmp_path / "old")  # has old/cost.json and old/cache/
    assert cost.breakdown(None) == {}
    assert cost.total(None) == (0.0, False)
    assert cost.items_per_second(None) is None


def test_pre006_cache_entries_hit_and_keys_match_expected(tmp_path):
    expected = json.loads((FIXTURES / "expected.json").read_text())
    cls, emb = expected["classification"], expected["seed_embedding"]
    cache = tmp_path / "cache"
    shutil.copytree(FIXTURES / "cache", cache)
    # keys recomputed from the recorded inputs equal the recorded file names
    assert (
        cost.cache_key(cls["model"], cls["system_prompt"], cls["text"])
        == cls["cache_key"]
    )
    assert cost.cache_key(emb["model"], "embed_query", emb["seed"]) == emb["cache_key"]
    hit_cls = cost.cache_get(cache, cls["cache_key"])
    hit_emb = cost.cache_get(cache, emb["cache_key"])
    assert hit_cls is not None and hit_emb is not None
    assert hit_cls["output"] == {"labels": ["alpha"], "reasoning": "It mentions alpha."}
    assert hit_emb["output"] == [1.0, 0.0, 0.0]


def test_cost_object_known_prices():
    cost.record(None, "a", RequestUsage(input_tokens=10, output_tokens=2), 0.5)
    cost.record(None, "b", RequestUsage(input_tokens=1, output_tokens=1), 0.25)
    c = cost.cost()
    assert c.total == 0.75 and c.unknown is False
    assert c.by_model["a"]["calls"] == 1 and c.by_model["b"]["dollars"] == 0.25
    text = repr(c)
    assert "$0.7500" in text and "$0.5000" in text and "$0.2500" in text
    assert "?" not in text and "warning" not in text.lower()


def test_cost_object_unknown_price_is_never_zero():
    cost.record(None, "known", UNKNOWN, 1.0)
    cost.record(None, "mystery", UNKNOWN, None)
    c = cost.cost()
    assert c.total is None and c.unknown is True
    text = repr(c)
    assert "cost ?" in text
    assert "warning" in text.lower() and "mystery" in text
    assert "$0.0000" not in text
    assert cost.cost(False).total == 0.0  # nothing recorded is a real zero


def test_cost_for_an_explicit_directory(tmp_path):
    cost.record(tmp_path, "m", UNKNOWN, 0.125)
    assert cost.cost(tmp_path).total == 0.125
    assert "$0.1250" in repr(cost.cost(tmp_path))
    assert cost.cost().by_model == {}


def test_cache_hit_records_no_cost_and_no_timing(tmp_path):
    key = cost.cache_key("m", "p", "t")
    cost.record(tmp_path, "m", UNKNOWN, 0.5)
    cost.record_timing(tmp_path, "dev", 1, 1.0)
    cost.cache_put(tmp_path, key, ["a"], UNKNOWN)
    before = (tmp_path / "cost.json").read_text()
    for _ in range(3):
        assert cost.cache_get(tmp_path, key) is not None
    assert (tmp_path / "cost.json").read_text() == before


def test_concurrent_writers_lose_no_update(tmp_path):
    def work():
        for _ in range(25):
            cost.record(
                tmp_path, "m", RequestUsage(input_tokens=1, output_tokens=0), 0.5
            )
            cost.record_timing(tmp_path, "dev", 1, 1.0)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert cost.breakdown(tmp_path)["m"]["calls"] == 200
    assert cost.total(tmp_path) == (100.0, False)
    assert cost.items_per_second(tmp_path, "dev") == 1.0
    assert len(json.loads((tmp_path / "cost.json").read_text())["timings"]) == 200
