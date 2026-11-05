import hashlib
import json
import os
from dataclasses import FrozenInstanceError

import pytest

from goldlabel import gold as gold_module
from goldlabel._gold_rule import GoldError
from goldlabel.candidates import Candidates, order_by_id
from goldlabel.gold import Gold, GoldSet, Sample
from goldlabel.settings import settings
from goldlabel.taxonomy import Label, Taxonomy


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "root", tmp_path)


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


def row(id, labels, sample="dev", **extra):
    return {"id": id, "text": f"text {id}", "labels": labels, "sample": sample, **extra}


def by_hash(ids, salt=""):
    """The draw order, computed here directly (not through the code under test)."""
    return sorted(
        ids, key=lambda i: hashlib.sha256(f"{salt}\0{i}".encode()).hexdigest()
    )


# --- files and names ----------------------------------------------------------------------------


def test_files_follow_settings_root_and_the_dataset_name(tmp_path, monkeypatch):
    assert Gold().path == tmp_path / "gold.jsonl"
    assert Gold(name="corpus-b").path == tmp_path / "gold-corpus-b.jsonl"
    assert Gold(name="gold").path == tmp_path / "gold-gold.jsonl"
    monkeypatch.setattr(settings, "root", tmp_path / "root")
    g = Gold()
    assert g.path == tmp_path / "root" / "gold.jsonl"
    assert len(g.all) == 0 and len(g.pending) == 0
    assert not (tmp_path / "root").exists()  # nothing is written on load


@pytest.mark.parametrize("bad", ["CorpusB", "", "a.b", "a/b", "a b", 5])
def test_a_dataset_name_is_lowercase_letters_digits_dash_underscore(bad):
    with pytest.raises(GoldError, match="lowercase"):
        Gold(name=bad)


def test_gold_has_no_path_argument(tmp_path):
    with pytest.raises(TypeError):
        Gold(path=tmp_path / "g.jsonl")  # ty: ignore[unknown-argument]


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "50"])
def test_sample_size_is_a_whole_number_of_at_least_one(bad):
    with pytest.raises(GoldError, match="sample_size"):
        Gold(sample_size=bad)
    assert Gold(sample_size=7).sample_size == 7


def test_a_row_without_a_sample_name_is_not_a_gold_row(tmp_path):
    write(
        tmp_path / "gold.jsonl",
        {"id": "1", "text": "t", "labels": None, "split": "dev"},
    )
    with pytest.raises(GoldError, match="not a gold row"):
        _ = Gold().all
    write(tmp_path / "gold.jsonl", row("1", None, "Dev"))
    with pytest.raises(GoldError, match="not a gold row"):
        _ = Gold().all


def test_hand_edited_file_with_extra_keys_loads_and_keeps_them(tmp_path):
    path = write(
        tmp_path / "gold.jsonl",
        row("x", ["a"], extra="hand", labelled_by="somebody"),
    )
    g = Gold()
    assert g["dev"].rows[0].labelled_by == "somebody"
    g.import_rows([{"id": "y", "text": "t", "labels": ["b"]}], "test")
    assert lines(path)[0]["extra"] == "hand"


def test_malformed_line_raises_with_its_number(tmp_path):
    path = tmp_path / "gold.jsonl"
    path.write_text(json.dumps(row("a", ["a"])) + "\n\n{not json\n")
    with pytest.raises(ValueError, match=r"gold\.jsonl:3"):
        _ = Gold().all
    path.write_text(json.dumps(row("a", ["a"])) + "\n" + json.dumps({"id": "b"}) + "\n")
    with pytest.raises(ValueError, match=r"gold\.jsonl:2"):
        _ = Gold().all


# --- draw_sample --------------------------------------------------------------------------------


def test_draw_sample_appends_pending_rows_and_a_rerun_draws_nothing(tmp_path):
    g = Gold(cands(60))
    dev = g.draw_sample("dev")
    assert isinstance(dev, Sample) and dev.drawn == 50 and dev.names == ("dev",)
    on_disk = lines(tmp_path / "gold.jsonl")
    assert len(on_disk) == 50
    assert all(r["labels"] is None and r["sample"] == "dev" for r in on_disk)
    assert all("labelled_by" not in r and "split" not in r for r in on_disk)
    assert {r["text"] for r in on_disk} == {f"text {r['id'][1:]}" for r in on_disk}
    before = (tmp_path / "gold.jsonl").read_bytes()
    again = g.draw_sample("dev")
    assert again.drawn == 0 and len(again) == 50
    assert (tmp_path / "gold.jsonl").read_bytes() == before
    assert [r.id for r in again.rows] == [r["id"] for r in on_disk]


def test_samples_are_disjoint_and_n_tops_up_without_changing_sample_size():
    g = Gold(cands(200))
    dev, test, test2 = (g.draw_sample(n) for n in ("dev", "test", "test-2"))
    ids = [{r.id for r in s.rows} for s in (dev, test, test2)]
    assert [len(x) for x in ids] == [50, 50, 50]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2])
    assert g.draw_sample("dev", n=80).drawn == 30
    assert len(g["dev"]) == 80 and g.sample_size == 50
    assert g.draw_sample("dev", n=30).drawn == 0 and len(g["dev"]) == 80
    assert (
        g.draw_sample("dev").drawn == 0
    )  # the default size is below 80: nothing drawn


def test_draw_sample_works_on_a_whole_corpus_list():
    whole = Candidates(
        [{"id": f"w{i}", "text": f"w text {i}"} for i in range(5)],
        floor=None,
        source="all",
    )
    drawn = Gold(whole, sample_size=3).draw_sample("dev")
    assert len(drawn) == 3 and all(r.labels is None for r in drawn.rows)
    assert {r.id for r in drawn.rows} <= {f"w{i}" for i in range(5)}


@pytest.mark.parametrize("bad", [0, -2, 2.5, True])
def test_n_is_a_whole_number_of_at_least_one(bad, tmp_path):
    with pytest.raises(GoldError, match="n must be"):
        Gold(cands(5)).draw_sample("dev", n=bad)
    assert not (tmp_path / "gold.jsonl").exists()


@pytest.mark.parametrize("bad", ["Test", "", "a b", "a.b", None])
def test_a_sample_name_is_lowercase_letters_digits_dash_underscore(bad, tmp_path):
    with pytest.raises(GoldError, match="lowercase"):
        Gold(cands(5)).draw_sample(bad)
    with pytest.raises(TypeError):
        Gold(cands(5)).draw_sample()  # ty: ignore[missing-argument]
    assert not (tmp_path / "gold.jsonl").exists()


def test_draw_sample_refuses_when_short_names_both_numbers_and_writes_nothing(tmp_path):
    g = Gold(cands(60))
    g.draw_sample("dev")
    before = (tmp_path / "gold.jsonl").read_bytes()
    with pytest.raises(GoldError, match="needs 20 more rows, but only 10 candidates"):
        g.draw_sample("test", n=20)
    assert (tmp_path / "gold.jsonl").read_bytes() == before


def test_a_gold_without_candidates_reads_and_tops_up_only_when_full(tmp_path):
    Gold(cands(60)).draw_sample("dev")
    assert Gold().draw_sample("dev").drawn == 0
    with pytest.raises(GoldError, match=r"gl\.Gold\(candidates\)"):
        Gold().draw_sample("test")


def test_the_draw_order_is_fixed_by_the_ids_and_the_dataset_name(tmp_path, monkeypatch):
    def ids(name, root):
        monkeypatch.setattr(settings, "root", tmp_path / root)
        return [r.id for r in Gold(cands(200), name=name).draw_sample("dev").rows]

    assert ids(None, "one") == ids(None, "two")
    assert set(ids("a", "three")) != set(ids("b", "three"))


def test_order_by_id_matches_sha256_of_salt_and_id():
    rows = [{"id": i} for i in ("a", "b", "c")]
    assert [r["id"] for r in order_by_id(rows)] == by_hash(["a", "b", "c"])
    assert [r["id"] for r in order_by_id(rows, "x")] == by_hash(["a", "b", "c"], "x")
    three = Candidates([{"id": i, "text": i} for i in ("a", "b", "c")], source="all")
    drawn = Gold(three, sample_size=2).draw_sample("dev")
    assert [r.id for r in drawn.rows] == by_hash(["a", "b", "c"])[:2]


def test_more_candidates_never_move_rows_already_drawn(tmp_path):
    Gold(cands(60)).draw_sample("dev")
    before = (tmp_path / "gold.jsonl").read_bytes()
    assert Gold(cands(120)).draw_sample("dev").drawn == 0
    assert (tmp_path / "gold.jsonl").read_bytes() == before
    shared = {f"c{i}" for i in range(60)}
    narrow = [r["id"] for r in order_by_id(cands(60).rows)]
    wide = [r["id"] for r in order_by_id(cands(120).rows) if r["id"] in shared]
    assert wide == narrow


def test_a_removed_row_is_never_drawn_again(tmp_path):
    g = Gold(cands(10), sample_size=5)
    first = [r.id for r in g.draw_sample("dev").rows]
    gone = first[:2]
    g.remove(gone)
    again = g.draw_sample("dev")
    assert again.drawn == 2 and len(again) == 5
    assert not set(gone) & {r.id for r in again.rows}
    assert [r["id"] for r in lines(tmp_path / "gold.removed.jsonl")] == gone


def test_getitem_returns_a_sample_without_drawing_or_lists_the_names(tmp_path):
    g = Gold(cands(200))
    for name in ("dev", "test", "test-2"):
        g.draw_sample(name)
    before = (tmp_path / "gold.jsonl").read_bytes()
    s = g["test-2"]
    assert s.drawn == 0 and len(s) == 50 and s.names == ("test-2",)
    with pytest.raises(KeyError, match="dev, test, test-2"):
        g["nope"]
    assert (tmp_path / "gold.jsonl").read_bytes() == before


# --- Sample -------------------------------------------------------------------------------------


def test_a_sample_is_live(tmp_path):
    dev = Gold(cands(5), sample_size=2).draw_sample("dev")
    a, b = (r.id for r in dev.rows)
    write(tmp_path / "gold.jsonl", row(a, ["a"]), row(b, None), row("x", None, "test"))
    assert [(r.id, r.labels) for r in dev.rows] == [(a, ["a"]), (b, None)]


def test_sample_counts_len_and_frames(tmp_path):
    write(
        tmp_path / "gold.jsonl",
        row("1", ["a"]),
        row("2", ["a", "b"]),
        row("3", ["off_topic"]),
        row("4", None),
        row("5", ["b"], "test"),
    )
    dev = Gold()["dev"]
    assert len(dev) == 4
    assert dev.counts(taxonomy("multi")) == {"a": 2, "b": 1, "off_topic": 1}
    assert dev.to_polars()["sample"].to_list() == ["dev"] * 4
    assert dev.to_pandas()["id"].tolist() == ["1", "2", "3", "4"]
    assert "split" not in dev.to_polars().columns


def test_sample_repr_says_what_was_drawn_and_html_escapes(tmp_path):
    g = Gold(cands(60))
    assert repr(g.draw_sample("dev")).splitlines()[0] == (
        'Sample "dev" of default: 50 rows (0 labelled, 50 pending); drew 50 now; '
        "not evaluated"
    )
    assert repr(g["dev"]).splitlines()[0] == (
        'Sample "dev" of default: 50 rows (0 labelled, 50 pending); nothing drawn; '
        "not evaluated"
    )
    b = Gold(cands(5), name="corpus-b", sample_size=1).draw_sample("test")
    assert repr(b).startswith(
        'Sample "test" of corpus-b: 1 rows (0 labelled, 1 pending)'
    )
    write(tmp_path / "gold.jsonl", row("1", None) | {"text": "<b>x</b>"})
    html = Gold()["dev"]._repr_html_()
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "<b>x" not in html


def test_adding_samples_gives_the_union_and_writes_nothing(tmp_path):
    g = Gold(cands(200))
    dev, test = g.draw_sample("dev"), g.draw_sample("test")
    before = (tmp_path / "gold.jsonl").read_bytes()
    both = dev + test
    assert isinstance(both, Sample) and both.names == ("dev", "test")
    assert len(both) == 100
    assert repr(both).splitlines()[0] == (
        'Sample "dev" + "test" of default: 100 rows (0 labelled, 100 pending); '
        "not evaluated"
    )
    assert len(dev + dev) == 50 and len(both + test) == 100
    assert (tmp_path / "gold.jsonl").read_bytes() == before


def test_samples_of_two_datasets_cannot_be_added():
    a = Gold(cands(5), sample_size=1).draw_sample("dev")
    b = Gold(cands(5), name="b", sample_size=1).draw_sample("dev")
    with pytest.raises(GoldError, match="two gold datasets"):
        a + b
    with pytest.raises(TypeError):
        a + 1


# --- two datasets -------------------------------------------------------------------------------


def test_two_datasets_keep_their_own_rows_files_and_locks(tmp_path):
    a, b = Gold(), Gold(name="b")
    a.import_rows([{"id": "1", "text": "t", "labels": ["a"]}], "test")
    b.import_rows([{"id": "1", "text": "t", "labels": ["b"]}], "test")
    assert [r.labels for r in a["test"].rows] == [["a"]]
    assert [r.labels for r in b["test"].rows] == [["b"]]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["gold-b.jsonl", "gold.jsonl"]
    assert a.path.name + ".lock" != b.path.name + ".lock"


# --- import_rows --------------------------------------------------------------------------------


def test_import_rows_stamps_and_writes_the_sample_name(tmp_path):
    g = Gold()
    got = g.import_rows(
        [
            {"id": "1", "text": "one", "labels": ["a"]},
            {"id": "2", "text": "two", "labels": ["a", "b"]},
        ],
        "test",
    )
    assert len(got) == 2
    on_disk = lines(tmp_path / "gold.jsonl")
    assert [(r["id"], r["labels"], r["sample"], r["labelled_by"]) for r in on_disk] == [
        ("1", ["a"], "test", "imported"),
        ("2", ["a", "b"], "test", "imported"),
    ]
    assert all(r["labelled_at"] for r in on_disk)
    assert [r.id for r in g["test"].rows] == ["1", "2"]
    with pytest.raises(GoldError, match="lowercase"):
        g.import_rows([{"id": "3", "text": "t", "labels": ["a"]}], "Test")


def test_import_rows_refuses_an_id_already_present_and_writes_nothing(tmp_path):
    path = write(tmp_path / "gold.jsonl", row("1", ["a"]))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="'1'"):
        Gold().import_rows(
            [
                {"id": "2", "text": "t", "labels": ["a"]},
                {"id": "1", "text": "t", "labels": ["a"]},
            ],
            "test",
        )
    with pytest.raises(ValueError, match="'3'"):
        Gold().import_rows(
            [
                {"id": "3", "text": "t", "labels": ["a"]},
                {"id": "3", "text": "t", "labels": ["b"]},
            ],
            "dev",
        )
    assert path.read_bytes() == before


def test_import_rows_does_not_check_labels_against_a_taxonomy():
    g = Gold()
    g.import_rows([{"id": "1", "text": "t", "labels": ["not-in-any-taxonomy"]}], "dev")
    assert g["dev"].rows[0].labels == ["not-in-any-taxonomy"]


def test_import_rows_needs_id_text_and_labels(tmp_path):
    g = Gold()
    for bad in (
        {"id": "1", "text": "t"},
        {"id": "1", "labels": ["a"]},
        {"id": "1", "text": "t", "labels": []},
    ):
        with pytest.raises(ValueError):
            g.import_rows([bad], "dev")
    assert not (tmp_path / "gold.jsonl").exists()


# --- views, counts, repr ------------------------------------------------------------------------


def test_pending_and_all_views(tmp_path):
    write(
        tmp_path / "gold.jsonl",
        row("1", ["a"]),
        row("2", None),
        row("3", ["b"], "test"),
    )
    g = Gold()
    assert [r.id for r in g.pending.rows] == ["2"]
    assert [r.id for r in g.all.rows] == ["1", "2", "3"]
    assert g.all.counts(taxonomy("multi")) == {"a": 1, "b": 1, "off_topic": 0}
    assert g.all.to_polars()["sample"].to_list() == ["dev", "dev", "test"]


def test_goldset_and_gold_reprs_are_plain_text(tmp_path):
    write(
        tmp_path / "gold.jsonl",
        row("1", ["a"], labelled_by="goldlabel-ui"),
        row("2", ["a"], "test", labelled_by="imported"),
        row("3", None),
    )
    # the last line is the Short gold rule (006/15), tested in test_gold_rule.py
    assert repr(Gold().all).splitlines()[0] == (
        "GoldSet all: 3 rows (2 labelled, 1 pending); goldlabel-ui 1, imported 1, unstamped 0"
    )
    assert repr(Gold()).splitlines()[0] == (
        f"Gold default ({tmp_path / 'gold.jsonl'}): dev 2 (1 labelled), test 1 (1 labelled); "
        "goldlabel-ui 1, imported 1, unstamped 0"
    )


def test_goldset_is_frozen():
    with pytest.raises(FrozenInstanceError):
        GoldSet([], "x").rows = []  # frozen  # ty: ignore[invalid-assignment]


# --- orphaned and remove ------------------------------------------------------------------------


def test_orphaned_are_rows_with_a_label_outside_the_taxonomy(tmp_path):
    write(
        tmp_path / "gold.jsonl",
        row("1", ["a"]),
        row("2", ["a", "gone"]),
        row("3", ["old"], "test"),
        row("4", None),
        row("5", ["off_topic"]),
    )
    assert [r.id for r in Gold().orphaned(taxonomy()).rows] == ["2", "3"]


def test_remove_moves_rows_to_removed_file_and_keeps_all_fields(tmp_path):
    path = write(
        tmp_path / "gold.jsonl",
        row(
            "1",
            ["a"],
            labelled_by="goldlabel-ui",
            labelled_at="2026-01-01T00:00:00+00:00",
            note="n",
        ),
        row("2", ["b"], "test"),
        row("3", None),
    )
    g = Gold()
    gone = g.remove(["1", "3"])
    assert [r.id for r in gone.rows] == ["1", "3"]
    assert [r["id"] for r in lines(path)] == ["2"]
    removed = tmp_path / "gold.removed.jsonl"
    assert lines(removed) == [
        row(
            "1",
            ["a"],
            labelled_by="goldlabel-ui",
            labelled_at="2026-01-01T00:00:00+00:00",
            note="n",
        ),
        row("3", None),
    ]
    g.remove(["2"])  # appends, never overwrites
    assert [r["id"] for r in lines(removed)] == ["1", "3", "2"]
    assert lines(path) == []


def test_remove_unknown_id_raises_and_changes_nothing(tmp_path):
    path = write(tmp_path / "gold.jsonl", row("1", ["a"]))
    before = path.read_bytes()
    with pytest.raises(ValueError, match="'zz'"):
        Gold().remove(["1", "zz"])
    assert path.read_bytes() == before
    assert not (tmp_path / "gold.removed.jsonl").exists()
    with pytest.raises(TypeError):
        Gold().remove("1")


# --- atomic write -------------------------------------------------------------------------------


def test_a_crash_between_temp_write_and_replace_leaves_the_old_file(
    tmp_path, monkeypatch
):
    path = write(tmp_path / "gold.jsonl", row("1", ["a"]))
    before = path.read_bytes()

    def boom(*a, **k):
        raise OSError("crash")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError, match="crash"):
        Gold(cands(5), sample_size=2).draw_sample("test")
    with pytest.raises(OSError, match="crash"):
        Gold().import_rows([{"id": "9", "text": "t", "labels": ["a"]}], "test")
    assert path.read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["gold.jsonl"]  # no temp file left


# --- the gold rule ------------------------------------------------------------------------------


def test_only_import_rows_can_set_a_label():
    public = {n for n in dir(Gold) if not n.startswith("_")}
    # any new public name must be reviewed against the gold rule before it is added here
    assert public == {
        "pending",
        "all",
        "label",
        "draw_sample",  # reviewed in 014/T001: writes pending rows only
        "import_rows",
        "orphaned",
        "remove",
    }
    module_public = {
        n
        for n in vars(gold_module)
        if not n.startswith("_")
        and callable(getattr(gold_module, n))
        and getattr(getattr(gold_module, n), "__module__", None) == "goldlabel.gold"
    }
    assert module_public == {
        "Gold",
        "GoldRow",
        "GoldSet",
        "Sample",
    }
    read_only = {"rows", "name", "path", "counts", "to_polars", "to_pandas"}
    assert not {n for n in dir(GoldSet) if not n.startswith("_")} - read_only
    assert not {n for n in dir(Sample) if not n.startswith("_")} - read_only


def test_nothing_but_import_rows_changes_a_labelled_row(tmp_path):
    path = write(
        tmp_path / "gold.jsonl",
        row("1", ["a"]),
        row("2", None),
        row("3", ["b"], "test"),
    )
    g = Gold(cands(5), sample_size=4)
    g.draw_sample("dev")
    g.orphaned(taxonomy())
    g.remove(["3"])
    _ = g["dev"] + g["dev"]
    by_id = {r["id"]: r["labels"] for r in lines(path)}
    assert by_id["1"] == ["a"] and by_id["2"] is None
    assert sum(v is None for v in by_id.values()) == 3  # row 2 plus the two drawn


# --- notes (013) ----------------------------------------------------------------------------


def test_a_note_round_trips_and_an_unset_note_writes_no_key(tmp_path):
    p = write(
        tmp_path / "gold.jsonl",
        row("1", ["a"], note="two policies in one sentence"),
        row("2", ["a"]),
    )
    g = Gold()
    assert [r.note for r in g.all.rows] == ["two policies in one sentence", None]
    g._write(g._read())
    assert [("note" in r, r.get("note")) for r in lines(p)] == [
        (True, "two policies in one sentence"),
        (False, None),
    ]


def test_import_rows_keeps_a_note_key_as_given(tmp_path):
    g = Gold()
    g.import_rows([{"id": "1", "text": "t", "labels": ["a"], "note": "sarcasm"}], "dev")
    assert lines(g.path)[0]["note"] == "sarcasm"
    assert lines(g.path)[0]["labelled_by"] == "imported"


def test_gold_frames_carry_the_note_column(tmp_path):
    write(tmp_path / "gold.jsonl", row("1", ["a"], note="n"), row("2", ["b"]))
    assert Gold().all.to_polars()["note"].to_list() == ["n", None]
    assert Gold().all.to_pandas()["note"].tolist() == ["n", None]
