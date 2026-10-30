import csv
import importlib
import json
import sys

import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

from goldlabel.candidates import aget_candidates, get_candidates
from goldlabel.search import Table, search_table, table_rows
from goldlabel.settings import settings

FIVE = [
    {"post_id": "a", "body": "the ballot", "note": 1},
    {"post_id": "b", "body": "an election", "note": 2},
    {"post_id": "c", "body": "Vote today", "note": 3},
    {"post_id": "d", "body": "weather", "note": 4},
    {"post_id": "e", "body": "ballot box", "note": 5},
]
WANT = [
    {"id": "a", "text": "the ballot"},
    {"id": "b", "text": "an election"},
    {"id": "c", "text": "Vote today"},
    {"id": "d", "text": "weather"},
    {"id": "e", "text": "ballot box"},
]
COLS = {"text_column": "body", "id_column": "post_id"}


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings.root = tmp_path / "root"


def write_csv(path):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(FIVE[0]))
        w.writeheader()
        w.writerows(FIVE)


def write_jsonl(path):
    path.write_text("".join(json.dumps(r) + "\n" for r in FIVE))


def test_the_same_five_rows_from_every_plain_source(tmp_path):
    write_csv(tmp_path / "t.csv")
    write_jsonl(tmp_path / "t.jsonl")
    for source in (tmp_path / "t.csv", str(tmp_path / "t.jsonl"), FIVE):
        assert table_rows(Table(source, **COLS)) == WANT, source


def test_the_same_five_rows_from_polars_pandas_and_parquet(tmp_path):
    pl = pytest.importorskip("polars")
    pd = pytest.importorskip("pandas")
    pl.DataFrame(FIVE).write_parquet(tmp_path / "t.parquet")
    for source in (
        pl.DataFrame(FIVE),
        pd.DataFrame(FIVE),
        tmp_path / "t.parquet",
    ):
        assert table_rows(Table(source, **COLS)) == WANT


def test_every_form_gives_the_same_get_candidates_result(tmp_path):
    pl = pytest.importorskip("polars")
    pd = pytest.importorskip("pandas")
    write_csv(tmp_path / "t.csv")
    write_jsonl(tmp_path / "t.jsonl")
    pl.DataFrame(FIVE).write_parquet(tmp_path / "t.parquet")
    sources = [
        tmp_path / "t.csv",
        tmp_path / "t.jsonl",
        tmp_path / "t.parquet",
        pl.DataFrame(FIVE),
        pd.DataFrame(FIVE),
        FIVE,
    ]
    for source in sources:
        got = get_candidates(Table(source, **COLS), out=False)
        assert got.rows == WANT, source
    assert not (tmp_path / "root").exists()


def test_parquet_through_pandas_when_polars_is_missing(tmp_path, monkeypatch):
    pl = pytest.importorskip("polars")
    pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    pl.DataFrame(FIVE).write_parquet(tmp_path / "t.parquet")
    monkeypatch.setitem(sys.modules, "polars", None)
    assert table_rows(Table(tmp_path / "t.parquet", **COLS)) == WANT


def test_parquet_with_neither_library_names_both(tmp_path, monkeypatch):
    (tmp_path / "t.parquet").write_bytes(b"x")
    monkeypatch.setitem(sys.modules, "polars", None)
    monkeypatch.setitem(sys.modules, "pandas", None)
    with pytest.raises(ImportError, match="polars.*pandas"):
        table_rows(Table(tmp_path / "t.parquet"))


def test_an_unknown_suffix_lists_the_accepted_ones(tmp_path):
    (tmp_path / "t.txt").write_text("x")
    with pytest.raises(ValueError, match=r"\.csv.*\.parquet.*\.jsonl"):
        table_rows(Table(tmp_path / "t.txt"))


def test_defaults_are_a_text_column_and_the_position_as_id():
    got = table_rows(Table([{"text": "x"}, {"text": "y"}]))
    assert got == [{"id": "0", "text": "x"}, {"id": "1", "text": "y"}]


def test_ids_become_strings():
    got = table_rows(Table([{"text": "x", "n": 7}], id_column="n"))
    assert got == [{"id": "7", "text": "x"}]


def test_a_csv_with_a_byte_order_mark_keeps_its_first_column_name(tmp_path):
    (tmp_path / "t.csv").write_bytes("text,id\nhello,1\n".encode("utf-8-sig"))
    assert table_rows(Table(tmp_path / "t.csv", id_column="id")) == [
        {"id": "1", "text": "hello"}
    ]


def test_an_empty_table_is_valid():
    assert table_rows(Table([])) == []


@pytest.mark.parametrize(
    "rows, id_column, message",
    [
        ([{"x": "a"}], None, "text"),  # missing text column
        ([{"text": "a"}, {"text": 5}], None, "row 1.*non-empty"),
        ([{"text": "a"}, {"text": None}], None, "row 1.*non-empty"),
        ([{"text": "a"}, {"text": "  "}], None, "row 1.*non-empty"),
        ([{"text": ""}], None, "row 0.*non-empty"),
        ([{"text": "a"}], "key", "key"),  # missing id column
        ([{"text": "a", "key": 1}, {"text": "b"}], "key", "row 1.*key"),
        ([{"text": "a", "key": 1}, {"text": "b", "key": 1}], "key", "repeated.*'1'"),
    ],
)
def test_validation_names_the_column_or_the_first_offending_row(
    rows, id_column, message
):
    with pytest.raises(ValueError, match=message):
        table_rows(Table(rows, id_column=id_column))


def test_a_pandas_nan_is_not_a_string():
    pd = pytest.importorskip("pandas")
    frame = pd.DataFrame({"text": ["a", float("nan")]})
    with pytest.raises(ValueError, match="row 1.*non-empty"):
        table_rows(Table(frame))


def test_a_csv_cannot_hold_vectors_and_the_text_column_is_required(tmp_path):
    with pytest.raises(ValueError, match="vector_column"):
        Table(tmp_path / "t.csv", vector_column="v")
    with pytest.raises(ValueError, match="text_column"):
        Table([], text_column="")


# --- seed search over a table ---------------------------------------------------------------------

# cosine to s_a [1,0] / s_b [0,1], by hand:  r0 1/0   r1 0/1   r2 .7071/.7071   r3 -1/0
VEC_ROWS = [
    {"id": "r0", "text": "t0", "v": [1.0, 0.0]},
    {"id": "r1", "text": "t1", "v": [0.0, 1.0]},
    {"id": "r2", "text": "t2", "v": [1.0, 1.0]},
    {"id": "r3", "text": "t3", "v": [-1.0, 0.0]},
]
VECTORS = {"sa": [1.0, 0.0], "sb": [0.0, 1.0]}


def vec_table(rows=VEC_ROWS, model="m"):
    return Table(rows, id_column="id", vector_column="v", embedding_model=model)


def test_two_seeds_one_pass_with_hand_computed_similarities():
    per_seed, capped = search_table(
        vec_table(), [VECTORS["sa"], VECTORS["sb"]], 0.6, "m"
    )
    assert capped is False
    assert [(i, t) for i, t, _ in per_seed[0]] == [("r0", "t0"), ("r2", "t2")]
    assert [s for *_, s in per_seed[0]] == pytest.approx([1.0, 0.70710678])
    assert [(i, t) for i, t, _ in per_seed[1]] == [("r1", "t1"), ("r2", "t2")]
    assert [s for *_, s in per_seed[1]] == pytest.approx([1.0, 0.70710678])


def test_the_floor_is_inclusive():
    per_seed, _ = search_table(vec_table(), [VECTORS["sa"]], 1.0, "m")
    assert [i for i, *_ in per_seed[0]] == ["r0"]


def test_the_table_is_read_once_for_all_seeds(monkeypatch):
    module = importlib.import_module(
        "goldlabel.search"
    )  # `goldlabel.search` is the function

    calls = []
    real = module.table_rows
    monkeypatch.setattr(
        module, "table_rows", lambda *a, **k: calls.append(1) or real(*a, **k)
    )
    search_table(vec_table(), [VECTORS["sa"], VECTORS["sb"]], 0.6, "m")
    assert calls == [1]


def test_seed_search_refusals():
    with pytest.raises(ValueError, match="no embedding column.*keywords"):
        search_table(Table(VEC_ROWS, id_column="id"), [[1.0, 0.0]], 0.6, "m")
    with pytest.raises(ValueError, match="embedding_model"):
        search_table(vec_table(model=None), [[1.0, 0.0]], 0.6, "m")
    with pytest.raises(ValueError, match="'old'.*'new'"):
        search_table(vec_table(model="old"), [[1.0, 0.0]], 0.6, "new")


def test_a_bad_vector_fails_naming_its_row():
    for bad in ("abc", None, [1.0], [[1.0, 0.0]]):
        rows = [*VEC_ROWS[:2], {"id": "r9", "text": "t9", "v": bad}]
        with pytest.raises(ValueError, match="row 2.*v"):
            search_table(vec_table(rows), [[1.0, 0.0]], 0.6, "m")


class StubEmbedder(Embedder):
    def __init__(self, vectors, name="m"):
        super().__init__(TestEmbeddingModel(name))
        self.vectors, self.name = vectors, name

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [self.vectors[query]],
            inputs=[query],
            input_type="query",
            model_name=self.name,
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


async def test_aget_candidates_reads_a_table_and_ranks_like_before():
    got = await aget_candidates(
        vec_table(), seeds=["sa", "sb"], embedder=StubEmbedder(VECTORS), out=False
    )
    assert [(r["id"], r["best_seed"]) for r in got.rows] == [
        ("r0", "sa"),
        ("r1", "sb"),
        ("r2", "sa"),
    ]
