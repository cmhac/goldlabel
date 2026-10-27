import json
import os
import shutil
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from hunches import gold as gold_module
from hunches.candidates import Candidates
from hunches.gold import Gold, GoldSet
from hunches.settings import settings
from hunches.taxonomy import Label, Taxonomy

FIXTURE = Path(__file__).parent / "fixtures" / "pre006" / "gold.jsonl"


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def taxonomy(mode="multi", *names):
    return Taxonomy(mode=mode, labels=[Label(name=n) for n in (names or ("a", "b"))])


def cands(n):
    return Candidates(
        [
            {
                "id": f"c{i}",
                "text": f"text {i}",
                "max_similarity": 0.7,
                "best_seed": "s",
            }
            for i in range(n)
        ]
    )


def write(path, *rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def lines(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def row(id, labels, split="dev", **extra):
    return {"id": id, "text": f"text {id}", "labels": labels, "split": split, **extra}


# --- loading ------------------------------------------------------------------------------------


def test_default_path_follows_settings_root_and_nothing_is_written_on_load(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(settings, "root", tmp_path / "root")
    g = Gold()
    assert g.path == tmp_path / "root" / "gold.jsonl"
    assert len(g.all) == 0 and len(g.dev) == 0
    assert not (tmp_path / "root").exists()


def test_pre006_file_loads_unchanged_and_counts_match(tmp_path):
    shutil.copy(FIXTURE, tmp_path / "g.jsonl")
    g = Gold(tmp_path / "g.jsonl")
    tax = Taxonomy(
        mode="multi", labels=[Label(name="alpha"), Label(name="beta")]
    )  # same labels as the fixture
    # file: a1 alpha dev, b1 beta dev, a2 alpha test, c1 [] test (no labels yet)
    assert [r.id for r in g.dev.rows] == ["a1", "b1"]
    assert [r.id for r in g.test.rows] == ["a2"]
    assert [r.id for r in g.pending.rows] == ["c1"]
    assert len(g.all) == 4
    assert g.dev.counts(tax) == {"alpha": 1, "beta": 1, "off_topic": 0}
    assert g.test.counts(tax) == {"alpha": 1, "beta": 0, "off_topic": 0}
    assert g.all.rows[0].labelled_by is None and g.all.rows[0].labelled_at is None
    assert (tmp_path / "g.jsonl").read_bytes() == FIXTURE.read_bytes()


def test_hand_edited_file_with_extra_keys_loads_and_keeps_them(tmp_path):
    path = write(
        tmp_path / "g.jsonl",
        row("x", ["a"], note="hand", labelled_by="somebody"),
    )
    g = Gold(path)
    assert g.dev.rows[0].labelled_by == "somebody"
    g.import_rows([{"id": "y", "text": "t", "labels": ["b"]}], "test")
    assert lines(path)[0]["note"] == "hand"


def test_malformed_line_raises_with_its_number(tmp_path):
    path = tmp_path / "g.jsonl"
    path.write_text(json.dumps(row("a", ["a"])) + "\n\n{not json\n")
    with pytest.raises(ValueError, match=r"g\.jsonl:3"):
        _ = Gold(path).all
    path.write_text(json.dumps(row("a", ["a"])) + "\n" + json.dumps({"id": "b"}) + "\n")
    with pytest.raises(ValueError, match=r"g\.jsonl:2"):
        _ = Gold(path).all


# --- draw ---------------------------------------------------------------------------------------


def test_draw_appends_pending_rows_with_null_labels(tmp_path):
    path = tmp_path / "g.jsonl"
    drawn = Gold(path).draw(cands(10), n=4, seed=1)
    assert len(drawn) == 4 and all(r.labels is None for r in drawn.rows)
    on_disk = lines(path)
    assert len(on_disk) == 4
    assert all(r["labels"] is None and r["split"] == "dev" for r in on_disk)
    assert all("labelled_by" not in r for r in on_disk)
    assert {r["text"] for r in on_disk} == {f"text {r['id'][1:]}" for r in on_disk}
    assert Gold(path).pending.rows == drawn.rows


def test_draw_works_on_a_whole_corpus_list(tmp_path):
    whole = Candidates(
        [{"id": f"w{i}", "text": f"w text {i}"} for i in range(5)],
        floor=None,
        source="all",
    )
    drawn = Gold(tmp_path / "g.jsonl").draw(whole, n=3, seed=1)
    assert len(drawn) == 3 and all(r.labels is None for r in drawn.rows)
    assert {r.id for r in drawn.rows} <= {f"w{i}" for i in range(5)}


def test_draw_never_repeats_an_id_across_dev_and_test(tmp_path):
    g = Gold(tmp_path / "g.jsonl")
    dev = g.draw(cands(10), n=5, split="dev", seed=3)
    test = g.draw(cands(10), n=5, split="test", seed=3)
    assert not {r.id for r in dev.rows} & {r.id for r in test.rows}
    assert len({r.id for r in g.all.rows}) == 10
    assert {r.id for r in test.rows} == {f"c{i}" for i in range(10)} - {
        r.id for r in dev.rows
    }


def test_draw_is_deterministic_per_seed(tmp_path):
    a = Gold(tmp_path / "a.jsonl").draw(cands(20), n=5, seed=7)
    b = Gold(tmp_path / "b.jsonl").draw(cands(20), n=5, seed=7)
    c = Gold(tmp_path / "c.jsonl").draw(cands(20), n=5, seed=8)
    assert [r.id for r in a.rows] == [r.id for r in b.rows]
    assert [r.id for r in a.rows] != [r.id for r in c.rows]


def test_draw_raises_when_short_and_names_how_many(tmp_path):
    path = tmp_path / "g.jsonl"
    g = Gold(path)
    g.draw(cands(6), n=4, seed=0)
    before = path.read_bytes()
    with pytest.raises(ValueError, match="only 2 "):
        g.draw(cands(6), n=3, split="test")
    assert path.read_bytes() == before


def test_draw_rejects_an_unknown_split(tmp_path):
    with pytest.raises(ValueError, match="split"):
        Gold(tmp_path / "g.jsonl").draw(cands(3), n=1, split="train")


def test_draw_default_n_is_50(tmp_path):
    assert len(Gold(tmp_path / "g.jsonl").draw(cands(60), seed=0)) == 50


# --- import_rows --------------------------------------------------------------------------------


def test_import_rows_stamps_and_writes(tmp_path):
    path = tmp_path / "g.jsonl"
    g = Gold(path)
    got = g.import_rows(
        [
            {"id": "1", "text": "one", "labels": ["a"]},
            {"id": "2", "text": "two", "labels": ["a", "b"]},
        ],
        "test",
    )
    assert len(got) == 2
    on_disk = lines(path)
    assert [(r["id"], r["labels"], r["split"], r["labelled_by"]) for r in on_disk] == [
        ("1", ["a"], "test", "imported"),
        ("2", ["a", "b"], "test", "imported"),
    ]
    assert all(r["labelled_at"] for r in on_disk)
    assert [r.id for r in g.test.rows] == ["1", "2"]


def test_import_rows_refuses_an_id_already_present_and_writes_nothing(tmp_path):
    path = tmp_path / "g.jsonl"
    write(path, row("1", ["a"]))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="'1'"):
        Gold(path).import_rows(
            [
                {"id": "2", "text": "t", "labels": ["a"]},
                {"id": "1", "text": "t", "labels": ["a"]},
            ],
            "test",
        )
    with pytest.raises(ValueError, match="'3'"):
        Gold(path).import_rows(
            [
                {"id": "3", "text": "t", "labels": ["a"]},
                {"id": "3", "text": "t", "labels": ["b"]},
            ],
            "dev",
        )
    assert path.read_bytes() == before


def test_import_rows_does_not_check_labels_against_a_taxonomy(tmp_path):
    g = Gold(tmp_path / "g.jsonl")
    g.import_rows([{"id": "1", "text": "t", "labels": ["not-in-any-taxonomy"]}], "dev")
    assert g.dev.rows[0].labels == ["not-in-any-taxonomy"]


def test_import_rows_needs_id_text_and_labels(tmp_path):
    g = Gold(tmp_path / "g.jsonl")
    for bad in (
        {"id": "1", "text": "t"},
        {"id": "1", "labels": ["a"]},
        {"id": "1", "text": "t", "labels": []},
    ):
        with pytest.raises(ValueError):
            g.import_rows([bad], "dev")
    assert not (tmp_path / "g.jsonl").exists()


# --- views, counts, repr ------------------------------------------------------------------------


def test_views_and_counts_single_and_multi(tmp_path):
    path = write(
        tmp_path / "g.jsonl",
        row("1", ["a"]),
        row("2", ["a", "b"]),
        row("3", ["off_topic"]),
        row("4", None),
        row("5", ["b"], "test"),
    )
    g = Gold(path)
    assert [r.id for r in g.dev.rows] == ["1", "2", "3"]  # labelled only
    assert [r.id for r in g.pending.rows] == ["4"]
    assert [r.id for r in g.all.rows] == ["1", "2", "3", "4", "5"]
    multi = taxonomy("multi")
    assert g.dev.counts(multi) == {
        "a": 2,
        "b": 1,
        "off_topic": 1,
    }  # row 2 counted once per label
    assert g.all.counts(multi) == {"a": 2, "b": 2, "off_topic": 1}
    single = Gold(
        write(tmp_path / "s.jsonl", row("1", ["a"]), row("2", ["a"]), row("3", ["b"]))
    )
    assert single.dev.counts(taxonomy("single")) == {"a": 2, "b": 1, "off_topic": 0}
    assert len(g.dev) == 3 and len(g.test) == 1


def test_goldset_repr_is_plain_text_with_sources(tmp_path):
    path = write(
        tmp_path / "g.jsonl",
        row("1", ["a"], labelled_by="hunches-ui"),
        row("2", ["a"], labelled_by="imported"),
        row("3", ["b"], labelled_by="imported"),
        row("4", ["b"]),
        row("5", None),
    )
    # the last line is the Short gold rule (006/15), tested in test_gold_rule.py
    assert repr(Gold(path).dev).splitlines()[0] == (
        "GoldSet dev: 4 rows (4 labelled, 0 pending); hunches-ui 1, imported 2, unstamped 1"
    )
    assert repr(Gold(path).all).splitlines()[0] == (
        "GoldSet all: 5 rows (4 labelled, 1 pending); hunches-ui 1, imported 2, unstamped 1"
    )


def test_views_are_read_only():
    s = Gold.__dict__
    assert isinstance(s["dev"], property) and isinstance(s["all"], property)
    with pytest.raises(FrozenInstanceError):
        GoldSet([], "x").rows = []  # frozen  # ty: ignore[invalid-assignment]


# --- orphaned and remove ------------------------------------------------------------------------


def test_orphaned_are_rows_with_a_label_outside_the_taxonomy(tmp_path):
    path = write(
        tmp_path / "g.jsonl",
        row("1", ["a"]),
        row("2", ["a", "gone"]),
        row("3", ["old"], "test"),
        row("4", None),
        row("5", ["off_topic"]),
    )
    got = Gold(path).orphaned(taxonomy())
    assert [r.id for r in got.rows] == ["2", "3"]


def test_remove_moves_rows_to_removed_file_and_keeps_all_fields(tmp_path):
    path = write(
        tmp_path / "g.jsonl",
        row(
            "1",
            ["a"],
            labelled_by="hunches-ui",
            labelled_at="2026-01-01T00:00:00+00:00",
            note="n",
        ),
        row("2", ["b"], "test"),
        row("3", None),
    )
    g = Gold(path)
    gone = g.remove(["1", "3"])
    assert [r.id for r in gone.rows] == ["1", "3"]
    assert [r["id"] for r in lines(path)] == ["2"]
    removed = tmp_path / "g.removed.jsonl"
    assert lines(removed) == [
        row(
            "1",
            ["a"],
            labelled_by="hunches-ui",
            labelled_at="2026-01-01T00:00:00+00:00",
            note="n",
        ),
        row("3", None),
    ]
    g.remove(["2"])  # appends, never overwrites
    assert [r["id"] for r in lines(removed)] == ["1", "3", "2"]
    assert lines(path) == []


def test_remove_unknown_id_raises_and_changes_nothing(tmp_path):
    path = write(tmp_path / "g.jsonl", row("1", ["a"]))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="'zz'"):
        Gold(path).remove(["1", "zz"])
    assert path.read_bytes() == before and not (tmp_path / "g.removed.jsonl").exists()
    with pytest.raises(TypeError):
        Gold(path).remove("1")


# --- atomic write -------------------------------------------------------------------------------


def test_a_crash_between_temp_write_and_replace_leaves_the_old_file(
    tmp_path, monkeypatch
):
    path = write(tmp_path / "g.jsonl", row("1", ["a"]))
    before = path.read_bytes()

    def boom(*a, **k):
        raise OSError("crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="crash"):
        Gold(path).draw(cands(5), n=2, seed=0)
    with pytest.raises(OSError, match="crash"):
        Gold(path).import_rows([{"id": "9", "text": "t", "labels": ["a"]}], "test")
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["g.jsonl"]  # no temp file left


# --- the gold rule ------------------------------------------------------------------------------


def test_only_import_rows_can_set_a_label():
    public = {n for n in dir(Gold) if not n.startswith("_")}
    # any new public name must be reviewed against the gold rule before it is added here
    assert public == {
        "dev",
        "test",
        "pending",
        "all",
        "draw",
        "import_rows",
        "orphaned",
        "remove",
    }
    module_public = {
        n
        for n in vars(gold_module)
        if not n.startswith("_")
        and callable(getattr(gold_module, n))
        and getattr(getattr(gold_module, n), "__module__", None) == "hunches.gold"
    }
    assert module_public == {"Gold", "GoldRow", "GoldSet"}
    assert not {n for n in dir(GoldSet) if not n.startswith("_")} - {
        "rows",
        "name",
        "path",
        "counts",
        "to_polars",  # read-only exports (006/12)
        "to_pandas",
    }


def test_nothing_but_import_rows_changes_a_labelled_row(tmp_path):
    path = write(
        tmp_path / "g.jsonl", row("1", ["a"]), row("2", None), row("3", ["b"], "test")
    )
    g = Gold(path)
    g.draw(cands(5), n=2, seed=0)
    g.orphaned(taxonomy())
    g.remove(["3"])
    by_id = {r["id"]: r["labels"] for r in lines(path)}
    assert by_id["1"] == ["a"] and by_id["2"] is None
    assert sum(v is None for v in by_id.values()) == 3  # row 2 plus the two drawn
