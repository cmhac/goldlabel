import json
from dataclasses import replace
from typing import Any

import pytest

import goldlabel as gl
from goldlabel.candidates import Candidates
from goldlabel.classifier import Classifier, Predictions
from goldlabel.taxonomy import Taxonomy

CORPUS = "the table file corpus.jsonl (text column text, id column id)"
ROWS = [
    {"id": "a", "text": "x", "max_similarity": 0.8, "best_seed": "alpha"},
    {"id": "b", "text": "y", "max_similarity": 0.7, "best_seed": "beta"},
]
TAXONOMY = Taxonomy(
    mode="single", labels={"layoff": "Lost a job.", "burnout": "Worn out."}
)


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def doc(*sections):
    """The whole text, written by hand from the contract: a title, then each section."""
    return "## Methodology\n\n" + "\n\n".join(sections)


def seeds_list(**kw):
    return Candidates(
        ROWS,
        floor=0.6,
        embedding_model="embed-1",
        seeds=["alpha", "beta"],
        corpus=CORPUS,
        **kw,
    )


SEEDS_SECTION = (
    "### Corpus and candidates\n\n"
    f"We searched {CORPUS} for items similar to 2 example phrases "
    '("alpha"; "beta"). Each phrase was embedded with embed-1, and we kept every item '
    "whose highest similarity to any phrase was at least 0.6. This produced 2 candidates."
)
LABELS_SECTION = (
    "### Labels\n\nEach item received exactly one label from: `layoff`, `burnout`, "
    "or the built-in `off_topic` (the item matches none of them)."
)


def clf():
    return Classifier("openai:gpt-x", TAXONOMY, "Pick one.")


def test_candidates_from_seeds_and_the_labels_make_the_first_two_sections():
    m = gl.get_methodology(candidates=seeds_list(), classifier=clf())
    assert str(m) == doc(
        SEEDS_SECTION,
        LABELS_SECTION,
        "### Classifier\n\nThe classifier uses the model `openai:gpt-x`.",
    )
    assert m.warnings == ()


def test_a_cutoff_replaces_the_produced_sentence_and_says_what_was_left():
    chosen = seeds_list().above(0.75)
    text = str(gl.get_methodology(candidates=chosen))
    assert text == doc(
        SEEDS_SECTION.replace(
            "This produced 2 candidates.",
            "We then kept the items with similarity of at least 0.75, which left 1.",
        )
    )


def test_a_filter_and_a_capped_search_are_stated():
    text = str(
        gl.get_methodology(candidates=seeds_list(filter="year >= 2024", capped=True))
    )
    assert text == doc(
        SEEDS_SECTION.replace(
            " This produced 2 candidates.",
            " The corpus was filtered with: year >= 2024. This produced 2 candidates. "
            "A limit in the search backend may have hidden items above the floor.",
        )
    )


def test_keyword_and_whole_corpus_candidates_have_no_similarity_wording():
    kw = Candidates(
        ROWS, floor=None, source="keywords", keywords=["alpha", "gamma"], corpus=CORPUS
    )
    first = (
        f"### Corpus and candidates\n\nWe selected items from {CORPUS} containing any of "
        '2 terms ("alpha"; "gamma"), matched as literal text. This produced 2 candidates.'
    )
    assert str(gl.get_methodology(candidates=kw)) == doc(first)
    rx = Candidates(
        ROWS,
        floor=None,
        source="keywords",
        keywords=["al+pha"],
        regex=True,
        corpus=CORPUS,
    )
    assert str(gl.get_methodology(candidates=rx)) == doc(
        f"### Corpus and candidates\n\nWe selected items from {CORPUS} containing any of "
        '1 term ("al+pha"), matched as regular expressions. This produced 2 candidates.'
    )
    everything = Candidates(ROWS, floor=None, source="all", corpus=CORPUS)
    assert str(gl.get_methodology(candidates=everything)) == doc(
        f"### Corpus and candidates\n\nWe used every item of {CORPUS}. "
        "This produced 2 candidates."
    )


def test_a_multi_label_taxonomy_says_every_label_that_applies():
    t = Taxonomy(mode="multi", labels={"a": "x"})
    text = str(gl.get_methodology(classifier=Classifier("m", t, "p")))
    assert text == doc(
        "### Labels\n\nEach item received every label that applies from: `a`, "
        "or the built-in `off_topic` (the item matches none of them).",
        "### Classifier\n\nThe classifier uses the model `m`.",
    )


def test_the_labels_come_from_the_gold_file_when_there_is_no_classifier():
    g = gl.Gold()
    g.path.parent.mkdir(parents=True)
    g.path.write_text(json.dumps({"taxonomy": TAXONOMY.model_dump(), "rows": []}))
    assert str(gl.get_methodology(gold=g)) == doc(
        LABELS_SECTION,
        '### Gold labels\n\nThe gold dataset "default" holds no samples yet.',
    )


def test_an_explicit_candidates_list_wins_over_the_one_the_gold_holds():
    gold = gl.Gold(seeds_list())
    assert "We searched" in str(gl.get_methodology(gold=gold))
    other = Candidates(ROWS, floor=None, source="all", corpus=CORPUS)
    assert "We used every item" in str(gl.get_methodology(gold=gold, candidates=other))


def test_it_needs_at_least_one_object_and_checks_their_types():
    with pytest.raises(
        ValueError, match="give at least one of candidates, gold, classifier or results"
    ):
        gl.get_methodology()
    with pytest.raises(ValueError, match="give at least one"):
        gl.get_methodology(include_gold_table=False)
    for name, bad in [
        ("candidates", "x"),
        ("gold", 1),
        ("classifier", "m"),
        ("results", []),
    ]:
        kwargs: dict[str, Any] = {name: bad}
        with pytest.raises(TypeError, match=name):
            gl.get_methodology(**kwargs)


def test_two_calls_over_the_same_inputs_give_the_same_text():
    a = gl.get_methodology(candidates=seeds_list(), classifier=clf())
    b = gl.get_methodology(candidates=seeds_list(), classifier=clf())
    assert a.text == b.text and a == b


def test_the_repr_is_the_text_and_the_html_is_escaped_with_no_colour():
    c = Candidates(ROWS, seeds=["a<b"], corpus=CORPUS, embedding_model="e", floor=0.6)
    m = gl.get_methodology(candidates=c)
    assert str(m) == repr(m) == m.text and '"a<b"' in m.text
    html = m._repr_html_()
    assert html.startswith("<pre>") and html.endswith("</pre>")
    assert "&lt;" in html and "a<b" not in html
    assert "style" not in html and "color" not in html


def test_candidates_saved_before_the_search_was_recorded_say_what_is_missing():
    legacy = Candidates(ROWS, floor=0.6, embedding_model="embed-1")
    assert str(gl.get_methodology(candidates=legacy)) == doc(
        "### Corpus and candidates\n\nWe searched the corpus for items similar to example "
        "phrases. Each phrase was embedded with embed-1, and we kept every item whose "
        "highest similarity to any phrase was at least 0.6. The seed phrases were not "
        "recorded in the candidates file. The corpus and its filter were not recorded in "
        "the candidates file. This produced 2 candidates."
    )
    kw = Candidates(ROWS, floor=None, source="keywords", corpus=CORPUS)
    assert str(gl.get_methodology(candidates=kw)) == doc(
        f"### Corpus and candidates\n\nWe selected items from {CORPUS} containing any of "
        "the search terms. The keywords were not recorded in the candidates file. "
        "This produced 2 candidates."
    )
    everything = Candidates(ROWS, floor=None, source="all")
    assert str(gl.get_methodology(candidates=everything)) == doc(
        "### Corpus and candidates\n\nWe used every item of the corpus. The corpus and its "
        "filter were not recorded in the candidates file. This produced 2 candidates."
    )


# --- gold, classifier and evaluation: a gold file and a log built by hand ----------------------


def gold_row(id, sample, labels, by=None, **more):
    row = {"id": id, "text": f"text {id}", "labels": labels, "sample": sample}
    return {**row, **({"labelled_by": by} if by else {}), **more}


REVISION = {
    "at": "2026-11-02T10:00:00+00:00",
    "labels": ["layoff"],
    "note": None,
    "labelled_by": "goldlabel-ui",
}
GOLD_ROWS = [
    gold_row("d1", "dev", ["layoff"], "goldlabel-ui"),
    gold_row(
        "d2", "dev", ["burnout"], "goldlabel-ui", note="tricky", revisions=[REVISION]
    ),
    gold_row("d3", "dev", None),
    gold_row("t1", "test", ["layoff"], "imported"),
    gold_row("t2", "test", ["off_topic"]),
]


def eval_line(samples, time, clf_, score, n, skipped, dollars, prompt):
    return {
        "time": time,
        "samples": samples,
        "rows_digest": "x",
        "n": n,
        "skipped_pending": skipped,
        "gold": ".goldlabel/gold.json",
        "model": "openai:gpt-x",
        "digest": clf_.digest,
        "prompt": prompt,
        "metric": "accuracy",
        "target": 0.9,
        "score": score,
        "dollars": dollars,
        "disagreements": [],
    }


OLD = clf()
NEW = OLD.with_prompt("Pick better.")
LOG = [
    eval_line(["dev"], "2026-11-04T09:00:00+00:00", OLD, 0.8, 2, 1, 0.25, "Pick one."),
    eval_line(
        ["dev"], "2026-11-05T09:00:00+00:00", NEW, 1.0, 2, 1, 0.5, "Pick better."
    ),
    eval_line(
        ["test"], "2026-11-06T09:00:00+00:00", NEW, 0.5, 2, 0, 0.25, "Pick better."
    ),
]


def write_gold(rows=GOLD_ROWS, log=LOG):
    g = gl.Gold()
    g.path.parent.mkdir(parents=True, exist_ok=True)
    g.path.write_text(json.dumps({"taxonomy": TAXONOMY.model_dump(), "rows": rows}))
    if log is not None:
        log_path = g.path.parent / "evals.jsonl"
        log_path.write_text("".join(json.dumps(x) + "\n" for x in log))
    return g


GOLD_SECTION = (
    "### Gold labels\n\nPeople labelled items by hand, and the classifier was measured "
    'against their labels. The gold dataset "default" holds 2 samples:\n\n'
    "- **dev**: 3 rows, 2 labelled, 1 pending.\n"
    "- **test**: 2 rows, 2 labelled, 0 pending.\n\n"
    "The 4 labelled rows by how they were labelled: 2 in the labelling page, "
    "1 imported (labelled elsewhere), 1 with no record. "
    "Rows with a revised label or note: 1. Rows with a note: 1. "
    "The number of people who labelled is not recorded."
)
CLASSIFIER_SECTION = (
    "### Classifier\n\nThe classifier uses the model `openai:gpt-x`. "
    "Different prompts evaluated against the gold labels: 2."
)
EVAL_SECTION = (
    "### Evaluation\n\nThe classifier was scored against the gold labels:\n\n"
    "- **dev**: accuracy 1.00 on 2 labelled rows (1 pending row not scored), "
    "target 0.9, met. Latest evaluation 2026-11-05. Evaluated 2 times with 2 different prompts.\n"
    "- **test**: accuracy 0.50 on 2 labelled rows (0 pending rows not scored), "
    "target 0.9, not met. Latest evaluation 2026-11-06. Evaluated 1 time with 1 different prompt.\n\n"
    "Evaluation calls cost $1.00 in total."
)


def test_gold_classifier_and_evaluation_sections_from_a_hand_built_gold_file():
    g = write_gold()
    files = [(p, p.read_bytes()) for p in (g.path, g.path.parent / "evals.jsonl")]
    m = gl.get_methodology(gold=g, classifier=NEW)
    assert str(m) == doc(LABELS_SECTION, GOLD_SECTION, CLASSIFIER_SECTION, EVAL_SECTION)
    assert all(p.read_bytes() == data for p, data in files)  # read-only (SC-006)


def test_a_classifier_gets_the_evaluation_that_was_run_with_its_own_prompt():
    g = write_gold()
    text = str(gl.get_methodology(gold=g, classifier=OLD))
    # dev: the older prompt's own evaluation, though a later one exists; test: none, so the latest
    assert (
        "- **dev**: accuracy 0.80 on 2 labelled rows (1 pending row not scored), "
        "target 0.9, not met. Latest evaluation 2026-11-04. Evaluated 2 times with 2 different prompts."
    ) in text
    assert "- **test**: accuracy 0.50" in text


def test_a_gold_dataset_without_samples_says_so():
    g = write_gold(rows=[], log=None)
    assert str(gl.get_methodology(gold=g)) == doc(
        LABELS_SECTION,
        '### Gold labels\n\nThe gold dataset "default" holds no samples yet.',
    )


def test_a_classifier_loaded_from_a_bundle_brings_its_own_evaluation():
    bundle = replace(clf())
    object.__setattr__(
        bundle,
        "evaluation",
        {
            "samples": ["test"],
            "n": 50,
            "score": 0.9,
            "metric": "accuracy",
            "digest": bundle.digest,
            "date": "2026-11-06T10:00:00+00:00",
        },
    )
    assert str(gl.get_methodology(classifier=bundle)) == doc(
        LABELS_SECTION,
        "### Classifier\n\nThe classifier uses the model `openai:gpt-x`.",
        "### Evaluation\n\nThe classifier was scored against the gold labels:\n\n"
        "- **test**: accuracy 0.90 on 50 labelled rows, evaluated 2026-11-06 "
        "(read from the classifier's saved bundle).",
    )


def test_an_evaluation_cost_that_includes_an_unknown_price_is_a_question_mark():
    log = [{**x, "dollars": None} if x["samples"] == ["dev"] else x for x in LOG]
    text = str(gl.get_methodology(gold=write_gold(log=log), classifier=NEW))
    assert "Evaluation calls cost ? (a price is unknown)." in text and "$1" not in text


# --- the run: a Predictions built by hand ------------------------------------------------------


def run_row(id, at, sim, error=None):
    row = {
        "id": id,
        "text": f"text {id}",
        "labels": None if error else ["layoff"],
        "run": "d",
        "run_model": "m1",
        "run_at": at,
        "max_similarity": sim,
    }
    return {**row, "error": error} if error else row


RUN_ROWS = [
    run_row("a", "2026-11-07T10:00:00+00:00", 0.8),
    run_row("b", "2026-11-06T09:00:00+00:00", 0.72),
    run_row("c", "2026-11-07T11:00:00+00:00", 0.75, error="boom"),
]


def run_section(tail):
    return (
        "### Run\n\n3 items were classified by `m1` between 2026-11-06 and 2026-11-07: "
        "2 by live model calls, 0 from the cache, 1 resumed from an earlier run, 1 failed. "
        + tail
    )


def test_the_run_section_counts_items_names_model_and_dates_and_the_lowest_similarity():
    p = Predictions(RUN_ROWS, live=2, cached=0, resumed=1, cost=0.25)
    assert str(gl.get_methodology(results=p)) == doc(
        run_section(
            "The live model calls cost $0.25. The lowest similarity among the items was 0.72."
        )
    )


def test_the_run_section_states_the_cutoff_the_candidates_carry():
    p = Predictions(RUN_ROWS, live=2, cached=0, resumed=1, cost=0.25)
    text = str(gl.get_methodology(results=p, candidates=seeds_list().above(0.7)))
    assert text.endswith(
        run_section(
            "The live model calls cost $0.25. The similarity cutoff was 0.7; "
            "the lowest similarity among the items was 0.72."
        )
    )


def test_one_day_one_item_and_no_similarity_scores_and_an_unknown_price():
    rows = [
        {
            "id": "a",
            "text": "x",
            "labels": ["a"],
            "run": "d",
            "run_model": "m1",
            "run_at": "2026-11-07T10:00:00+00:00",
        }
    ]
    p = Predictions(rows, live=1, cost=None)
    assert str(gl.get_methodology(results=p)) == doc(
        "### Run\n\n1 item was classified by `m1` on 2026-11-07: 1 by live model calls, "
        "0 from the cache, 0 resumed from an earlier run, 0 failed. "
        "The live model calls cost ? (a price is unknown)."
    )
