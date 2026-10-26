from pathlib import Path

import pytest
from pydantic import ValidationError

from hunches.taxonomy import Label, Taxonomy, all_labels, validate_labels

FIXTURE = Path(__file__).parent / "fixtures" / "pre006" / "taxonomy.yaml"


def test_dict_form_equals_model_form():
    by_dict = Taxonomy(mode="multi", labels={"a": "A thing", "b": ""})
    by_model = Taxonomy(
        mode="multi", labels=[Label(name="a", description="A thing"), Label(name="b")]
    )
    assert by_dict == by_model
    assert [(x.name, x.description) for x in by_dict.labels] == [
        ("a", "A thing"),
        ("b", ""),
    ]


def test_names_include_off_topic_last():
    tax = Taxonomy(mode="single", labels={"a": "x", "b": "y"})
    assert tax.names == ["a", "b", "off_topic"]
    assert all_labels(tax) == ["a", "b", "off_topic"]


def test_taxonomy_is_frozen():
    tax = Taxonomy(mode="single", labels={"a": ""})
    with pytest.raises(ValidationError):
        tax.mode = "multi"  # ty: ignore[invalid-assignment]


@pytest.mark.parametrize(
    "labels", [{"off_topic": ""}, [Label(name="off_topic")]], ids=["dict", "model"]
)
def test_off_topic_cannot_be_listed(labels):
    with pytest.raises(ValidationError, match="built in"):
        Taxonomy(mode="single", labels=labels)


def test_read_the_old_taxonomy_yaml_and_write_it_back_unchanged(tmp_path):
    tax = Taxonomy.read(FIXTURE)
    assert tax.mode == "multi"
    assert [(x.name, x.description) for x in tax.labels] == [
        ("alpha", "about alpha"),
        ("beta", "about beta"),
    ]
    out = tmp_path / "sub" / "t.yaml"
    tax.write(out)
    assert out.read_text() == FIXTURE.read_text()
    assert Taxonomy.read(out) == tax


def test_write_quotes_what_yaml_needs_and_round_trips(tmp_path):
    tax = Taxonomy(mode="single", labels={"a": "A: thing", "b": ""})
    tax.write(tmp_path / "t.yaml")
    assert Taxonomy.read(tmp_path / "t.yaml") == tax


SINGLE = Taxonomy(mode="single", labels={"a": "", "b": ""})
MULTI = Taxonomy(mode="multi", labels={"a": "", "b": ""})


@pytest.mark.parametrize("tax", [SINGLE, MULTI])
def test_validate_labels_rules_both_modes(tax):
    validate_labels(["a"], tax)
    validate_labels(["off_topic"], tax)
    with pytest.raises(ValueError, match="at least one"):
        validate_labels([], tax)
    with pytest.raises(ValueError, match="unknown"):
        validate_labels(["zzz"], tax)
    with pytest.raises(ValueError, match="only label"):
        validate_labels(["a", "off_topic"], tax)


def test_validate_labels_mode_specific():
    with pytest.raises(ValueError, match="exactly one"):
        validate_labels(["a", "b"], SINGLE)
    validate_labels(["a", "b"], MULTI)
