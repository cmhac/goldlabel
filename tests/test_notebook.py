import dataclasses
import re
import sys

import pytest

import goldlabel
from goldlabel.candidates import Candidates
from goldlabel.classifier import Classifier, Estimate, Predictions
from goldlabel.cost import Cost
from goldlabel.evaluation import BandReport, EvalLog, Evaluation
from goldlabel.gold import Gold, GoldRow, GoldSet
from goldlabel.metrics import compute_metrics
from goldlabel.taxonomy import Label, Taxonomy

HOSTILE = "<script>alert(1)</script> & co"
ESCAPED = "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co"


def tax():
    return Taxonomy(
        mode="single",
        labels=[Label(name="a", description=HOSTILE), Label(name="b", description="B")],
    )


def candidates(n=3, capped=True):
    sims = [0.61, 0.66, 0.76] + [0.62] * (n - 3)
    rows = [
        {"id": f"i{k}", "text": HOSTILE, "max_similarity": s, "best_seed": "s1"}
        for k, s in enumerate(sims[:n])
    ]
    return Candidates(rows, capped=capped)


def other_sources():
    kw = [{"id": "k", "text": HOSTILE, "terms_matched": 1, "matches": 2}]
    both = [{"id": "w", "text": HOSTILE}]
    return {
        "keywords": Candidates(kw, source="keywords"),
        "all": Candidates(both, source="all"),
    }


def predictions(cost=None):
    rows = [
        {
            "id": "1",
            "text": HOSTILE,
            "labels": ["a", "b"],
            "reasoning": HOSTILE,
            "run": "d1",
        },
        {"id": "2", "text": "t2", "labels": None, "error": HOSTILE, "run": "d1"},
    ]
    return Predictions(rows, live=1, cached=1, resumed=0, cost=cost)


def gold_set():
    return GoldSet(
        [
            GoldRow(
                id="1", text=HOSTILE, labels=["a"], split="dev", labelled_by="imported"
            ),
            GoldRow(id="2", text="t2", labels=None, split="dev"),
        ],
        name="dev",
    )


def evaluation():
    m = compute_metrics([{"a"}, {"b"}], [{"a"}, {"a"}], ["a", "b", "off_topic"])
    return Evaluation(
        metrics=m,
        metric="macro_f1",
        target=0.9,
        n=2,
        skipped_pending=1,
        sources={"goldlabel-ui": 0, "imported": 2, "unstamped": 0},
        digest="d" * 64,
        disagreements=[
            {
                "id": "2",
                "text": HOSTILE,
                "gold": ["b"],
                "predicted": ["a"],
                "reasoning": HOSTILE,
            },
            {
                "id": "3",
                "text": "t3",
                "gold": ["a"],
                "predicted": None,
                "reasoning": None,
            },
        ],
        labels=["a", "b", "off_topic"],
        split="dev",
    )


def eval_log():
    row = {
        "time": "2026-01-02T03:04:05+00:00",
        "split": "test",
        "n": 7,
        "score": 0.5,
        "digest": "abcdef0123456789",
        "model": "<i>m</i>",
    }
    return EvalLog([row, {**row, "split": "dev", "n": 9}])


def band_report(cost=None):
    rows = [{"band": "0.600-0.625", "n": 4, "off_topic": 1, "rate": 0.25}]
    return BandReport(rows, cost=cost, errors=2)


def cost_obj(unknown=True):
    m1 = {"dollars": 0.5, "calls": 2, "input_tokens": 10, "output_tokens": 5}
    m2 = {
        "dollars": None if unknown else 0.25,
        "calls": 1,
        "input_tokens": 3,
        "output_tokens": 1,
    }
    return Cost({"m<1>": m1, "m2": m2})


def classifier(evaluation=None):
    prompt = "\n".join(
        f"line {k} {HOSTILE}" if k == 0 else f"line {k}" for k in range(20)
    )
    clf = Classifier("test", tax(), prompt)
    object.__setattr__(clf, "evaluation", evaluation)
    return clf


def gold(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(
        '{"id": "1", "text": "x", "labels": ["a"], "split": "dev", "labelled_by": "goldlabel-ui"}\n'
        '{"id": "2", "text": "y", "labels": null, "split": "test"}\n'
    )
    return Gold(path)


def everything(tmp_path):
    return {
        "Candidates": candidates(),
        "Taxonomy": tax(),
        "Classifier": classifier(),
        "Predictions": predictions(),
        "Estimate": Estimate(10, 4, 6, None, None),
        "Gold": gold(tmp_path),
        "GoldSet": gold_set(),
        "Evaluation": evaluation(),
        "EvalLog": eval_log(),
        "BandReport": band_report(),
        "Cost": cost_obj(),
    }


def test_every_object_returns_a_string_and_escapes_item_text(tmp_path):
    for name, obj in everything(tmp_path).items():
        out = obj._repr_html_()
        assert isinstance(out, str) and out, name
        assert "<script" not in out and "<i>" not in out and "<b>x" not in out, name
    for name in ("Candidates", "Predictions", "GoldSet", "Evaluation", "Taxonomy"):
        assert ESCAPED in everything(tmp_path)[name]._repr_html_(), name
    for name, c in other_sources().items():
        out = c._repr_html_()
        assert ESCAPED in out and "<script" not in out, name
    assert "&lt;i&gt;m&lt;/i&gt;" in eval_log()._repr_html_()
    assert "m&lt;1&gt;" in cost_obj()._repr_html_()
    assert ESCAPED in classifier()._repr_html_()


def test_no_colour_anywhere(tmp_path):
    bad = re.compile(r"color\s*:|background|#[0-9a-fA-F]{3,8}\b|rgb|hsl", re.IGNORECASE)
    with_eval = classifier(
        {
            "split": "dev",
            "n": 2,
            "score": 0.5,
            "metric": "macro_f1",
            "date": "2026-01-01",
        }
    )
    objs = list(everything(tmp_path).values()) + [
        with_eval,
        Estimate(10, 4, 6, 0.12, 30.0),
        predictions(cost=0.5),
        band_report(cost=0.1),
        cost_obj(unknown=False),
        candidates(60),
        *other_sources().values(),
    ]
    for obj in objs:
        assert not bad.search(obj._repr_html_()), type(obj).__name__


def test_candidates_numbers_bars_and_warning():
    out = candidates()._repr_html_()
    assert "3 candidates" in out and "floor 0.60" in out
    assert "0.600-0.625" in out and "0.750+" in out
    assert re.search(r"0\.650-0\.675.*?</span> 1</div>", out)  # count beside its bar
    assert "WARNING" in out and "capped" in out
    assert "WARNING" not in candidates(capped=False)._repr_html_()


def test_row_cap_ends_with_n_more():
    out = candidates(60, capped=False)._repr_html_()
    assert out.count("<tr") == 51  # header + 50 rows
    assert "10 more" in out
    assert "more" not in candidates(50, capped=False)._repr_html_()
    out = candidates(51, capped=False)._repr_html_()
    assert "1 more" in out


def test_taxonomy_lists_labels_and_descriptions():
    out = tax()._repr_html_()
    for text in ("single", "a", "b", "off_topic", "B"):
        assert text in out


def test_classifier_preview_digest_and_evaluation():
    clf = classifier()
    out = clf._repr_html_()
    assert "test" in out and clf.digest[:12] in out
    assert "line 11" in out and "line 12" not in out  # 12-line preview
    assert "8 more" in out
    assert "evaluation" not in out.lower() or "no evaluation" in out.lower()
    rec = {
        "split": "dev",
        "n": 2,
        "score": 0.5,
        "metric": "macro_f1",
        "date": "2026-01-01",
    }
    out = classifier(rec)._repr_html_()
    assert "macro_f1" in out and "0.5000" in out and "dev" in out


def test_predictions_numbers_and_unknown_cost():
    out = predictions(cost=0.5)._repr_html_()
    assert "2 items" in out and "1 live" in out and "1 cached" in out
    assert "cost $0.5000" in out and "WARNING" not in out
    assert "ERROR" in out
    out = predictions(cost=None)._repr_html_()
    assert "cost ?" in out and "WARNING" in out and "$0.0000" not in out


def test_estimate_known_and_unknown():
    out = Estimate(10, 4, 6, 0.12, 30.0)._repr_html_()
    assert "10 items" in out and "4 cached" in out and "6 live" in out
    assert "~$0.1200" in out and "~30s" in out and "WARNING" not in out
    out = Estimate(10, 4, 6, None, None)._repr_html_()
    assert (
        "cost ?" in out
        and "time ?" in out
        and "WARNING" in out
        and "$0.0000" not in out
    )


def test_goldset_and_gold(tmp_path):
    out = gold_set()._repr_html_()
    assert "2 rows" in out and "1 labelled" in out and "1 pending" in out
    assert "imported 1" in out and "pending" in out
    out = gold(tmp_path)._repr_html_()
    assert "gold.jsonl" in out
    assert re.search(r"dev\D+1\D", out) and "test" in out and "pending" in out


def test_evaluation_numbers_pass_fail_and_bounded_disagreements():
    out = evaluation()._repr_html_()
    # hand-computed: macro_f1 (2/3 + 0)/2 = 0.3333, micro_f1 0.5, target 0.9
    assert "macro_f1 0.3333" in out and "FAIL" in out and "PASS" not in out
    assert "micro_f1 0.5000" in out and "0.67" in out
    assert "1 pending" in out and "imported 2" in out
    assert "2 disagreements" in out
    ev = evaluation()
    ev.target = 0.3
    assert "PASS" in ev._repr_html_() and "FAIL" not in ev._repr_html_()
    ev.target = None
    assert "PASS" not in ev._repr_html_() and "FAIL" not in ev._repr_html_()
    ev.disagreements = [
        {"id": str(k), "text": "t", "gold": ["a"], "predicted": ["b"], "reasoning": "r"}
        for k in range(30)
    ]
    out = ev._repr_html_()
    assert "10 more" in out  # disagreement list capped at 20


def test_evallog_bandreport_cost():
    out = eval_log()._repr_html_()
    assert "2026-01-02T03:04" in out and "abcdef01" in out and "0.5000" in out
    assert "test split evaluated 1 times" in out
    assert "no evaluations logged yet" in EvalLog([])._repr_html_()
    out = band_report(cost=0.1)._repr_html_()
    assert "0.600-0.625" in out and "25%" in out and "cost $0.1000" in out
    assert "2 errors" in out and "WARNING" not in out
    out = band_report()._repr_html_()
    assert "cost ?" in out and "WARNING" in out
    out = cost_obj()._repr_html_()
    assert (
        "cost ?" in out
        and "WARNING" in out
        and "m2" in out
        and "at least $0.5000" in out
    )
    out = cost_obj(unknown=False)._repr_html_()
    assert "cost $0.7500" in out and "WARNING" not in out


def test_plain_reprs_unchanged():
    assert repr(Estimate(10, 4, 6, None, None)).startswith("Estimate: 10 items")
    assert repr(candidates()).startswith("3 candidates (floor 0.60)")
    assert repr(cost_obj()).startswith("cost ?")


# ---- exports -------------------------------------------------------------------------------

pl = pytest.importorskip("polars")
pd = pytest.importorskip("pandas")


def tables(tmp_path):
    return {
        "Candidates": (candidates(), "to_polars", "to_pandas"),
        "Predictions": (predictions(), "to_polars", "to_pandas"),
        "GoldSet": (gold_set(), "to_polars", "to_pandas"),
        "Evaluation": (
            evaluation(),
            "disagreements_to_polars",
            "disagreements_to_pandas",
        ),
        "EvalLog": (eval_log(), "to_polars", "to_pandas"),
        "BandReport": (band_report(), "to_polars", "to_pandas"),
    }


def test_both_exports_agree(tmp_path):
    for name, (obj, p, q) in tables(tmp_path).items():
        a, b = getattr(obj, p)(), getattr(obj, q)()
        assert a.shape == b.shape, name
        assert list(a.columns) == list(b.columns), name
        assert a.to_dicts() == b.to_dict("records"), name


def test_predictions_columns_values_lists_and_nulls():
    a, b = predictions().to_polars(), predictions().to_pandas()
    expected = [
        {
            "id": "1",
            "text": HOSTILE,
            "labels": ["a", "b"],
            "reasoning": HOSTILE,
            "run": "d1",
            "error": None,
        },
        {
            "id": "2",
            "text": "t2",
            "labels": None,
            "reasoning": None,
            "run": "d1",
            "error": HOSTILE,
        },
    ]
    assert a.columns == ["id", "text", "labels", "reasoning", "run", "error"]
    assert a.to_dicts() == expected
    assert b.to_dict("records") == expected
    assert a["labels"].dtype == pl.List(pl.String)
    assert b["labels"].dtype == object
    assert "None" not in {v for v in a["reasoning"].to_list() if isinstance(v, str)}


def test_numbers_and_types_candidates_and_gold():
    a = candidates().to_polars()
    assert a.columns == ["id", "text", "max_similarity", "best_seed"]
    assert a["max_similarity"].to_list() == [0.61, 0.66, 0.76]
    assert a["max_similarity"].dtype == pl.Float64
    b = candidates().to_pandas()
    assert b["max_similarity"].dtype == "float64"
    g = gold_set().to_polars()
    assert g.columns == ["id", "text", "labels", "split", "labelled_by", "labelled_at"]
    assert g["labels"].to_list() == [["a"], None]
    assert g["labelled_by"].to_list() == ["imported", None]
    assert gold_set().to_pandas().to_dict("records") == g.to_dicts()


def test_mixed_ints_and_floats_agree():
    band = BandReport(
        [{"band": "x", "n": 1, "rate": 1}, {"band": "y", "n": 2, "rate": 0.5}], None
    )
    assert band.to_polars()["rate"].to_list() == [1.0, 0.5]
    assert band.to_pandas()["rate"].to_list() == [1.0, 0.5]


def test_later_keys_are_not_lost():
    rows = [{"id": "1", "text": "a", "labels": ["x"]}] * 150 + [
        {"id": "2", "text": "b", "labels": ["y"], "error": "late"}
    ]
    p = Predictions(rows)
    assert p.to_polars().columns == ["id", "text", "labels", "error"]
    assert p.to_polars()["error"][-1] == "late"
    assert p.to_pandas()["error"].iloc[-1] == "late"


def test_empty_tables_export():
    for empty in (EvalLog([]), Candidates([]), Predictions([])):
        assert empty.to_polars().shape == (0, 0) and empty.to_pandas().shape == (0, 0)


def test_evaluation_disagreements_values():
    a = evaluation().disagreements_to_polars()
    assert a.columns == ["id", "text", "gold", "predicted", "reasoning"]
    assert a["gold"].to_list() == [["b"], ["a"]]
    assert a["predicted"].to_list() == [["a"], None]
    assert a["reasoning"].to_list() == [HOSTILE, None]


@pytest.mark.parametrize("lib", ["polars", "pandas"])
def test_missing_library_message(lib, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, lib, None)
    for obj, p, q in tables(tmp_path).values():
        method = p if lib == "polars" else q
        with pytest.raises(
            ImportError, match=f"{lib} is not installed: pip install {lib}"
        ):
            getattr(obj, method)()


def test_public_result_classes_have_both_exports():
    found = []
    for name in goldlabel.__all__:
        cls = getattr(goldlabel, name)
        if not isinstance(cls, type) or not dataclasses.is_dataclass(cls):
            continue
        if "rows" in {f.name for f in dataclasses.fields(cls)}:
            found.append(name)
            assert callable(getattr(cls, "to_polars", None)), name
            assert callable(getattr(cls, "to_pandas", None)), name
    assert sorted(found) == [
        "BandReport",
        "Candidates",
        "EvalLog",
        "GoldSet",
        "Predictions",
    ]
    assert callable(Evaluation.disagreements_to_polars)
    assert callable(Evaluation.disagreements_to_pandas)
    for name in (
        "Candidates",
        "Taxonomy",
        "Classifier",
        "Predictions",
        "Estimate",
        "Gold",
        "GoldSet",
        "Evaluation",
        "EvalLog",
        "BandReport",
        "Cost",
    ):
        assert callable(getattr(goldlabel, name)._repr_html_), name
