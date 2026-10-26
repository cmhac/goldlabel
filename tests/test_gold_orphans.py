"""Spec 004 task 06: gold orphans and coverage."""

import pytest

from hunches import files
from hunches.files import GoldRow


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def pool(ids) -> None:
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": i, "text": f"item {i}", "max_similarity": 0.7, "best_seed": "x"}
            for i in ids
        ],
    )


def row(id, split="dev", labels=("a",)) -> GoldRow:
    return GoldRow(id=id, text=f"text {id}", labels=list(labels), split=split)


def test_orphaned_gold_is_exactly_the_rows_missing_from_the_pool():
    pool(["a", "b", "c"])
    files.write_gold(
        [row("a"), row("x"), row("b", "test"), row("y", "test"), row("z", labels=())]
    )
    assert [r.id for r in files.orphaned_gold()] == ["x", "y", "z"]
    assert [r.id for r in files.orphaned_gold("dev")] == ["x", "z"]
    assert [r.id for r in files.orphaned_gold("test")] == ["y"]


def test_orphaned_gold_with_no_candidates_file_is_every_row():
    files.write_gold([row("a")])
    assert [r.id for r in files.orphaned_gold()] == ["a"]


def test_gold_coverage_counts_per_split():
    pool(["a", "b"])
    files.write_gold(
        [
            row("a", labels=("p",)),
            row("x", labels=("p",)),
            row("y", labels=("p", "q")),
            row("z", labels=()),
            row("t1", "test"),
        ]
    )
    assert files.gold_coverage() == {
        "dev": {
            "rows": 4,
            "labelled": 3,
            "orphaned": 3,
            "orphaned_labelled": 2,
            "orphaned_by_label": {"p": 2, "q": 1},
        },
        "test": {
            "rows": 1,
            "labelled": 1,
            "orphaned": 1,
            "orphaned_labelled": 1,
            "orphaned_by_label": {"a": 1},
        },
    }
