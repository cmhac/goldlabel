import json
from typing import Any

import pytest

import goldlabel as gl
from goldlabel.candidates import Candidates
from goldlabel.classifier import Classifier
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
    assert str(m) == doc(SEEDS_SECTION, LABELS_SECTION)
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
        "or the built-in `off_topic` (the item matches none of them)."
    )


def test_the_labels_come_from_the_gold_file_when_there_is_no_classifier():
    g = gl.Gold()
    g.path.parent.mkdir(parents=True)
    g.path.write_text(json.dumps({"taxonomy": TAXONOMY.model_dump(), "rows": []}))
    assert str(gl.get_methodology(gold=g)) == doc(LABELS_SECTION)


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
