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
    '("alpha"; "beta"). We embedded each phrase with embed-1 and kept every item '
    "whose highest similarity to any phrase was at least 0.6. That gave us 2 candidates."
)
LABELS_SECTION = (
    "### Labels\n\nEach item received exactly one of these labels: `layoff`, `burnout`, "
    "or the built-in `off_topic`, which means the item fits none of them."
)


def clf():
    return Classifier("openai:gpt-x", TAXONOMY, "Pick one.")


def test_candidates_from_seeds_and_the_labels_make_the_first_two_sections():
    m = gl.get_methodology(candidates=seeds_list(), classifier=clf())
    assert str(m) == doc(
        SEEDS_SECTION,
        LABELS_SECTION,
        "### Classifier\n\nThe classifier uses the model `openai:gpt-x`.",
        appendix_head("Pick one."),
    )
    assert m.warnings == ()


def test_a_cutoff_replaces_the_produced_sentence_and_says_what_was_left():
    chosen = seeds_list().above(0.75)
    text = str(gl.get_methodology(candidates=chosen))
    assert text == doc(
        SEEDS_SECTION.replace(
            "That gave us 2 candidates.",
            "We then kept the items with similarity of at least 0.75, which left 1.",
        )
    )


def test_a_filter_and_a_capped_search_are_stated():
    text = str(
        gl.get_methodology(candidates=seeds_list(filter="year >= 2024", capped=True))
    )
    assert text == doc(
        SEEDS_SECTION.replace(
            " That gave us 2 candidates.",
            " We filtered the corpus with: year >= 2024. That gave us 2 candidates. "
            "A limit in the search backend may have hidden items above the floor.",
        )
    )


def test_keyword_and_whole_corpus_candidates_have_no_similarity_wording():
    kw = Candidates(
        ROWS, floor=None, source="keywords", keywords=["alpha", "gamma"], corpus=CORPUS
    )
    first = (
        f"### Corpus and candidates\n\nWe selected items from {CORPUS} that contain any of "
        '2 terms ("alpha"; "gamma"), matching them as literal text. That gave us 2 candidates.'
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
        f"### Corpus and candidates\n\nWe selected items from {CORPUS} that contain any of "
        '1 term ("al+pha"), matching them as regular expressions. That gave us 2 candidates.'
    )
    everything = Candidates(ROWS, floor=None, source="all", corpus=CORPUS)
    assert str(gl.get_methodology(candidates=everything)) == doc(
        f"### Corpus and candidates\n\nWe used every item of {CORPUS}. "
        "That gave us 2 candidates."
    )


def test_a_multi_label_taxonomy_says_every_label_that_applies():
    t = Taxonomy(mode="multi", labels={"a": "x"})
    text = str(gl.get_methodology(classifier=Classifier("m", t, "p")))
    assert text == doc(
        "### Labels\n\nEach item received every label that applies from `a`, "
        "or the built-in `off_topic` when none of them applies.",
        "### Classifier\n\nThe classifier uses the model `m`.",
        "### Appendix\n\nThe model was `m`.\n\nThe prompt, exactly as stored:\n\n> p\n\n"
        "The labels:\n\n- `a`: x\n- `off_topic`: The item matches none of the labels above.",
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
        "phrases. We embedded each phrase with embed-1 and kept every item whose "
        "highest similarity to any phrase was at least 0.6. The seed phrases were not "
        "recorded in the candidates file. The corpus and its filter were not recorded in "
        "the candidates file. That gave us 2 candidates."
    )
    kw = Candidates(ROWS, floor=None, source="keywords", corpus=CORPUS)
    assert str(gl.get_methodology(candidates=kw)) == doc(
        f"### Corpus and candidates\n\nWe selected items from {CORPUS} that contain any of "
        "the search terms. The keywords were not recorded in the candidates file. "
        "That gave us 2 candidates."
    )
    everything = Candidates(ROWS, floor=None, source="all")
    assert str(gl.get_methodology(candidates=everything)) == doc(
        "### Corpus and candidates\n\nWe used every item of the corpus. The corpus and its "
        "filter were not recorded in the candidates file. That gave us 2 candidates."
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
    log_path = g.path.parent / "evals.jsonl"
    if log is None:
        log_path.unlink(missing_ok=True)
    else:
        log_path.write_text("".join(json.dumps(x) + "\n" for x in log))
    return g


GOLD_SECTION = (
    "### Gold labels\n\nPeople labelled items by hand, and we measured the classifier "
    'against their labels. The gold dataset "default" holds 2 samples:\n\n'
    "- dev: 3 rows, 2 labelled, 1 pending.\n"
    "- test: 2 rows, 2 labelled, 0 pending.\n\n"
    "By source, the 4 labelled rows split into 2 labelled in the labelling page, "
    "1 imported (labelled elsewhere) and 1 with no record of how they were labelled. "
    "1 row had a label or note revised after it was first set, and 1 row had a note. "
    "The number of people who labelled was not recorded."
)
CLASSIFIER_SECTION = (
    "### Classifier\n\nThe classifier uses the model `openai:gpt-x`. "
    "We evaluated 2 prompts against the gold labels."
)
EVAL_SECTION = (
    "### Evaluation\n\nWe scored the classifier against the gold labels:\n\n"
    "- On dev, accuracy was 1.00 across 2 labelled rows, meeting the 0.9 target. "
    "1 pending row was left unscored. The latest evaluation ran on 2026-11-05 UTC, "
    "and we evaluated the sample 2 times with 2 different prompts.\n"
    "- On test, accuracy was 0.50 across 2 labelled rows, short of the 0.9 target. "
    "The latest evaluation ran on 2026-11-06 UTC, and we evaluated the sample "
    "1 time with 1 different prompt.\n\n"
    "The evaluation calls cost $1.00 in total."
)


def test_gold_classifier_and_evaluation_sections_from_a_hand_built_gold_file():
    g = write_gold()
    files = [(p, p.read_bytes()) for p in (g.path, g.path.parent / "evals.jsonl")]
    m = gl.get_methodology(gold=g, classifier=NEW)
    assert str(m) == doc(
        LABELS_SECTION,
        GOLD_SECTION,
        CLASSIFIER_SECTION,
        EVAL_SECTION,
        f"{APPENDIX_HEAD}\n\n{GOLD_TABLE}",
    )
    assert all(p.read_bytes() == data for p, data in files)  # read-only (SC-006)


def test_a_classifier_gets_the_evaluation_that_was_run_with_its_own_prompt():
    g = write_gold()
    text = str(gl.get_methodology(gold=g, classifier=OLD))
    # dev: the older prompt's own evaluation, though a later one exists; test: none, so the latest
    assert (
        "- On dev, accuracy was 0.80 across 2 labelled rows, short of the 0.9 target. "
        "1 pending row was left unscored. The latest evaluation ran on 2026-11-04 UTC, "
        "and we evaluated the sample 2 times with 2 different prompts."
    ) in text
    assert "- On test, accuracy was 0.50" in text


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
        "### Evaluation\n\nWe scored the classifier against the gold labels:\n\n"
        "- On test, accuracy was 0.90 across 50 labelled rows, evaluated on 2026-11-06 UTC "
        "(read from the classifier's saved bundle).",
        appendix_head("Pick one."),
    )


def test_an_evaluation_cost_that_includes_an_unknown_price_is_a_question_mark():
    log = [{**x, "dollars": None} if x["samples"] == ["dev"] else x for x in LOG]
    text = str(gl.get_methodology(gold=write_gold(log=log), classifier=NEW))
    assert (
        "The evaluation calls cost ? (a price is unknown)." in text and "$1" not in text
    )


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
        "### Run\n\nWe classified 3 items with `m1` between 2026-11-06 and 2026-11-07 UTC: "
        "2 by live model calls, 0 from the cache, 1 resumed from an earlier run and 1 failed. "
        + tail
    )


def test_the_run_section_counts_items_names_model_and_dates_and_the_lowest_similarity():
    p = Predictions(RUN_ROWS, live=2, cached=0, resumed=1, cost=0.25)
    assert str(gl.get_methodology(results=p)) == doc(
        run_section(
            "The live model calls cost $0.25. The similarity cutoff was not recorded, "
            "and the lowest similarity among the items was 0.72."
        )
    )


def test_the_run_section_states_the_cutoff_the_candidates_carry():
    p = Predictions(RUN_ROWS, live=2, cached=0, resumed=1, cost=0.25)
    text = str(gl.get_methodology(results=p, candidates=seeds_list().above(0.7)))
    assert text.endswith(
        run_section(
            "The live model calls cost $0.25. The similarity cutoff was 0.7, "
            "and the lowest similarity among the items was 0.72."
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
        "### Run\n\nWe classified 1 item with `m1` on 2026-11-07 UTC: 1 by live model calls, "
        "0 from the cache, 0 resumed from an earlier run and 0 failed. "
        "The live model calls cost ? (a price is unknown)."
    )


# --- what is not known is said, never guessed -------------------------------------------------


def test_result_rows_without_the_model_and_time_say_how_many_lack_them():
    bare = {"id": "a", "text": "x", "labels": ["a"], "run": "d"}
    stamped = {**bare, "run_model": "m1", "run_at": "2026-11-07T10:00:00+00:00"}
    p = Predictions([bare, {**bare, "id": "b"}, stamped], live=3, cost=0.25)
    assert str(gl.get_methodology(results=p)) == doc(
        "### Run\n\nWe classified 3 items with `m1` on 2026-11-07 UTC: 3 by live model calls, "
        "0 from the cache, 0 resumed from an earlier run and 0 failed. "
        "The live model calls cost $0.25. The model and time were not recorded on 2 of the 3 rows."
    )


def test_rows_imported_from_elsewhere_are_never_called_page_labels():
    g = write_gold(
        rows=[
            gold_row("a", "dev", ["layoff"], "imported"),
            gold_row("b", "dev", ["burnout"], "imported"),
        ],
        log=None,
    )
    text = str(gl.get_methodology(gold=g))
    assert (
        "split into 0 labelled in the labelling page, 2 imported (labelled elsewhere) "
        "and 0 with no record of how they were labelled"
    ) in text


def test_no_evaluation_log_means_no_evaluation_claims():
    text = str(gl.get_methodology(gold=write_gold(log=None), classifier=NEW))
    assert "### Evaluation" not in text and "prompts against the gold" not in text
    assert "The classifier uses the model `openai:gpt-x`." in text


def test_a_damaged_log_line_is_skipped_and_the_rest_still_counts():
    g = write_gold()
    log = g.path.parent / "evals.jsonl"
    log.write_text("{this is not json\n" + log.read_text())
    assert EVAL_SECTION in str(gl.get_methodology(gold=g, classifier=NEW))


@pytest.mark.parametrize(
    ("missing", "header"),
    [
        ("candidates", "### Corpus and candidates"),
        ("gold", "### Gold labels"),
        ("classifier", "### Classifier"),
        ("results", "### Run"),
    ],
)
def test_with_each_input_missing_in_turn_the_text_has_no_section_for_it(
    missing, header
):
    p = Predictions(RUN_ROWS, live=2, cached=0, resumed=1, cost=0.25)
    given: dict[str, Any] = {
        "candidates": seeds_list(),
        "gold": write_gold(),
        "classifier": NEW,
        "results": p,
    }
    del given[missing]
    text = str(gl.get_methodology(**given))
    assert header not in text
    assert all(h in text for h in ("### Labels",))


# --- warnings: real problems only; tuning a sample many times is not one -----------------------


def clean_inputs():
    rows = [{**r, "run": NEW.digest} for r in RUN_ROWS]
    return {
        "gold": write_gold(),
        "classifier": NEW,
        "results": Predictions(rows, live=3, cost=0.25),
    }


def test_a_clean_tuning_history_has_no_warning_even_with_two_prompts_on_dev():
    m = gl.get_methodology(**clean_inputs())
    assert m.warnings == () and "### Warnings" not in m.text


def warnings_of(**kw):
    return gl.get_methodology(**{**clean_inputs(), **kw}).warnings


def test_a_label_revised_after_the_evaluation_ran_is_flagged_as_stale():
    late = {"at": "2026-11-05T12:00:00+00:00", "labels": ["burnout"], "note": None}
    rows = [
        gold_row("d1", "dev", ["layoff"], "goldlabel-ui", revisions=[late]),
        *GOLD_ROWS[1:],
    ]
    m = gl.get_methodology(**{**clean_inputs(), "gold": write_gold(rows=rows)})
    stale = (
        "The dev evaluation of 2026-11-05 UTC predates a revision of 1 gold label; "
        "its score may no longer match the labels."
    )
    assert m.warnings == (stale,)
    assert f"### Warnings\n\n- {stale}\n\n### Appendix" in m.text


def test_a_classifier_that_was_never_evaluated_is_flagged_once():
    other = NEW.with_prompt("Something else")
    expected = (
        "The classifier passed in is not the one that was evaluated: its prompt, model or "
        "labels differ from every logged evaluation."
    )
    assert warnings_of(classifier=other, results=None) == (expected,)


def test_a_score_from_another_prompt_is_flagged_for_the_sample_that_has_no_own_evaluation():
    # OLD was evaluated on dev only; the test score shown is NEW's
    expected = (
        "The test score shown is from a different prompt than the classifier passed in "
        "(no evaluation of it was logged for that sample)."
    )
    assert warnings_of(classifier=OLD, results=None) == (expected,)


def test_labels_that_differ_from_the_gold_files_are_flagged():
    other = Classifier("m", Taxonomy(mode="multi", labels={"layoff": "x"}), "p")
    got = gl.get_methodology(gold=write_gold(log=None), classifier=other).warnings
    assert got == (
        "The classifier's labels differ from the labels stored in the gold file.",
    )


def test_results_from_another_classifier_are_flagged():
    rows = [{**r, "run": "someone-else"} for r in RUN_ROWS]
    got = warnings_of(results=Predictions(rows, live=3, cost=0.25))
    assert got == (
        "The results were produced by a different classifier from the one passed in.",
    )


def test_gold_rows_missing_from_the_candidates_are_flagged_unless_a_cutoff_was_applied():
    full = seeds_list()  # ids a and b; the gold rows are d1, d2, d3, t1, t2
    assert warnings_of(candidates=full) == (
        "5 gold rows are not among the candidates passed in.",
    )
    assert warnings_of(candidates=full.above(0.75)) == ()


# --- the appendix: the exact prompt, the labels and the gold dataset ---------------------------


def appendix_head(prompt="Pick better."):
    return (
        "### Appendix\n\nThe model was `openai:gpt-x`.\n\n"
        f"The prompt, exactly as stored:\n\n> {prompt}\n\n"
        "The labels:\n\n- `layoff`: Lost a job.\n- `burnout`: Worn out.\n"
        "- `off_topic`: The item matches none of the labels above."
    )


APPENDIX_HEAD = appendix_head()
GOLD_TABLE = (
    "The gold dataset:\n\n"
    "| sample | id | text | label | labelled by |\n"
    "|---|---|---|---|---|\n"
    "| dev | d1 | text d1 | layoff | labelling page |\n"
    "| dev | d2 | text d2 | burnout | labelling page |\n"
    "| dev | d3 | text d3 | (pending) |  |\n"
    "| test | t1 | text t1 | layoff | imported |\n"
    "| test | t2 | text t2 | off_topic | unstamped |"
)


def appendix_of(**kw):
    text = str(gl.get_methodology(**kw))
    return text[text.index("### Appendix") :]


def test_the_appendix_has_the_model_the_prompt_the_labels_and_every_gold_row():
    assert (
        appendix_of(gold=write_gold(), classifier=NEW)
        == f"{APPENDIX_HEAD}\n\n{GOLD_TABLE}"
    )


def test_a_multi_line_prompt_is_quoted_line_by_line_and_keeps_its_blank_lines():
    multi = replace(NEW, prompt="Line one\n\nLine two")
    assert "> Line one\n>\n> Line two\n\nThe labels:" in appendix_of(classifier=multi)


def test_with_no_classifier_the_appendix_is_only_the_gold_table():
    assert appendix_of(gold=write_gold()) == f"### Appendix\n\n{GOLD_TABLE}"


def test_a_pipe_or_a_line_break_in_a_row_cannot_break_the_table():
    rows = [gold_row("x|y", "dev", ["layoff"], "imported", text="a | b\nc\r\nd")]
    g = write_gold(rows=rows, log=None)
    table = appendix_of(gold=g).split("\n")
    assert table[-1] == "| dev | x\\|y | a \\| b<br>c<br>d | layoff | imported |"
    assert (
        len([line for line in table if line.startswith("|")]) == 3
    )  # header, rule, row


def test_the_gold_table_can_be_left_out_and_nothing_else_changes():
    g = write_gold()
    full = str(gl.get_methodology(gold=g, classifier=NEW))
    short = str(gl.get_methodology(gold=g, classifier=NEW, include_gold_table=False))
    assert full == f"{short}\n\n{GOLD_TABLE}"
    assert "The gold dataset:" not in short and "| sample" not in short
    assert (
        str(gl.get_methodology(gold=g, include_gold_table=False)).count("Appendix") == 0
    )


def test_a_note_never_appears_in_the_text_with_the_table_on_or_off():
    rows = [gold_row("a", "dev", ["layoff"], "goldlabel-ui", note="TOPSECRET-NOTE")]
    g = write_gold(rows=rows, log=None)
    for table in (True, False):
        text = str(gl.get_methodology(gold=g, classifier=NEW, include_gold_table=table))
        assert "TOPSECRET" not in text and "1 row had a note" in text


def test_results_from_another_classifier_withhold_the_prompt():
    rows = [{**r, "run": "someone-else"} for r in RUN_ROWS]
    text = appendix_of(classifier=NEW, results=Predictions(rows, live=3, cost=0.25))
    assert "Pick better." not in text
    assert (
        "The prompt is not given, because the results were produced by a different "
        "classifier from the one passed in, so its prompt is not the prompt of the run."
    ) in text


def test_a_bundle_saved_before_samples_existed_names_its_split():
    old = replace(clf())
    object.__setattr__(
        old,
        "evaluation",  # the shape `Classifier.save` wrote before it recorded `samples`
        {
            "split": "test",
            "n": 50,
            "score": 0.9,
            "metric": "accuracy",
            "digest": old.digest,
            "date": "2026-11-06T10:00:00+00:00",
        },
    )
    assert "- On test, accuracy was 0.90 across 50 labelled rows" in str(
        gl.get_methodology(classifier=old)
    )
