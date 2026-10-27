import importlib
import json
import math
import shutil
import threading
from pathlib import Path

import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

from hunches import candidates
from hunches.candidates import Candidates, aget_candidates, get_candidates, read_seeds
from hunches.search import PgCorpus, S3Corpus, Table
from hunches.settings import settings

cost = importlib.import_module("hunches.cost")  # `hunches.cost` is the function

FIXTURES = Path(__file__).parent / "fixtures" / "pre006"


class StubEmbedder(Embedder):
    """Maps seed text to a fixed vector; counts live calls."""

    def __init__(self, vectors, name="m"):
        super().__init__(TestEmbeddingModel(name))
        self.vectors, self.calls, self.name = vectors, [], name

    async def embed_query(self, query, *, settings=None):
        self.calls.append(query)
        return EmbeddingResult(
            [self.vectors[query]],
            inputs=[query],
            input_type="query",
            model_name=self.name,
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


def unit(a, b):
    """A 3-d unit vector whose cosine with [1,0,0] is a and with [0,1,0] is b."""
    return [a, b, math.sqrt(1 - a * a - b * b)]


SEEDS = {"alpha": [1, 0, 0], "beta": [0, 1, 0]}
# similarity to alpha / beta, by hand:
#   i0 0.61/0   i1 0.63/0.1   i2 0/0.71   i3 0.1/0.76   i4 0.5/0.5 (below the floor)   i5 0.66/0
VECTORS = [
    unit(0.61, 0),
    unit(0.63, 0.1),
    unit(0, 0.71),
    unit(0.1, 0.76),
    unit(0.5, 0.5),
    unit(0.66, 0),
]


def local(vectors=VECTORS, model="m"):
    rows = [
        {"id": f"i{i}", "text": f"t{i}", "v": list(v)} for i, v in enumerate(vectors)
    ]
    return Table(rows, id_column="id", vector_column="v", embedding_model=model)


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings.root = tmp_path / "root"


def ids(c):
    return [(r["id"], r["best_seed"]) for r in c.rows]


WANT = [
    ("i3", "beta"),
    ("i2", "beta"),
    ("i5", "alpha"),
    ("i1", "alpha"),
    ("i0", "alpha"),
]


def test_max_across_seeds_sorted_by_score_then_id(tmp_path):
    c = get_candidates(local(), seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS))
    assert ids(c) == WANT
    assert c.rows[0]["max_similarity"] == pytest.approx(0.76)
    assert c.rows[0]["text"] == "t3"
    assert set(c.rows[0]) == {"id", "text", "max_similarity", "best_seed"}
    assert c.capped is False and c.floor == 0.60


def test_tie_goes_to_the_earlier_seed(tmp_path):
    corpus = local([[1, 1, 0]])  # exactly the same similarity to both
    emb = lambda: StubEmbedder(SEEDS)
    assert ids(get_candidates(corpus, seeds=["alpha", "beta"], embedder=emb())) == [
        ("i0", "alpha")
    ]
    assert ids(get_candidates(corpus, seeds=["beta", "alpha"], embedder=emb())) == [
        ("i0", "beta")
    ]


def test_bands_and_top_seeds_by_hand(tmp_path):
    c = get_candidates(local(), seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS))
    # 0.61 and (0.63, 0.66) and 0.71 and 0.76 fall in bands 0, 1, 2, 4 and 6
    assert c.bands() == [1, 1, 1, 0, 1, 0, 1]
    assert c.top_seeds(0.60) == [("alpha", 3), ("beta", 2)]
    assert c.top_seeds(0.70) == [("beta", 2)]
    assert c.top_seeds(0.60, n=1) == [("alpha", 3)]


def test_above_is_inclusive_and_returns_candidates():
    rows = [
        {"id": s, "text": s, "max_similarity": v, "best_seed": "a"}
        for s, v in [("x", 0.8), ("y", 0.7), ("z", 0.69999)]
    ]
    c = Candidates(rows, capped=True, floor=0.6)
    top = c.above(0.7)
    assert isinstance(top, Candidates)
    assert [r["id"] for r in top.rows] == ["x", "y"]
    assert top.capped is True and top.floor == 0.6
    assert len(c.rows) == 3  # the original is untouched


def sample_pool():
    rows = [
        {"id": f"r{i}", "text": "t", "max_similarity": 0.6 + i / 100, "best_seed": "a"}
        for i in range(10)
    ]
    return Candidates(rows)


def test_sample_without_replacement_and_deterministic():
    pool = sample_pool()
    first = pool.sample(5, seed=1)
    assert isinstance(first, Candidates)
    got = [r["id"] for r in first.rows]
    assert len(got) == 5 and len(set(got)) == 5
    assert set(got) <= {f"r{i}" for i in range(10)}
    assert [r["id"] for r in pool.sample(5, seed=1).rows] == got


def test_sample_exclude_and_oversized_n():
    pool = sample_pool()
    taken = {"r0", "r1", "r2"}
    got = pool.sample(5, seed=3, exclude=taken)
    assert not taken & {r["id"] for r in got.rows}
    everything = pool.sample(50, seed=3, exclude=taken)
    assert sorted(r["id"] for r in everything.rows) == [f"r{i}" for i in range(3, 10)]
    assert pool.sample(0).rows == []


def test_unseeded_sample_still_valid():
    got = [r["id"] for r in sample_pool().sample(4).rows]
    assert len(set(got)) == 4


def test_round_trip_and_meta_beside_the_file(tmp_path):
    c = get_candidates(
        local(), seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS), out=False
    )
    path = tmp_path / "out" / "mine.jsonl"
    c.write(path)
    meta = json.loads((tmp_path / "out" / "mine.meta.json").read_text())
    assert set(meta) == {
        "seeds_digest",
        "written_at",
        "floor",
        "embedding_model",
        "capped",
        "source",
    }
    assert meta["seeds_digest"] == candidates.seeds_digest(["alpha", "beta"])
    assert meta["floor"] == 0.6 and meta["embedding_model"] == "m"
    assert meta["capped"] is False
    assert meta["written_at"].endswith("+00:00")
    back = Candidates.read(path)
    assert back.rows == c.rows and back.capped is False and back.floor == 0.6


def test_capped_survives_the_round_trip(tmp_path):
    Candidates([], capped=True, floor=0.65).write(tmp_path / "c.jsonl")
    back = Candidates.read(tmp_path / "c.jsonl")
    assert back.capped is True and back.floor == 0.65 and back.rows == []


def test_the_pre006_candidates_file_loads():
    c = Candidates.read(FIXTURES / "candidates.jsonl")
    assert [(r["id"], r["best_seed"]) for r in c.rows] == [
        ("a1", "alpha seed"),
        ("a2", "alpha seed"),
    ]
    assert c.rows[1]["max_similarity"] == pytest.approx(0.8)
    assert c.floor == 0.6 and c.capped is False  # from its meta, which has no `capped`
    assert c.embedding_model == "fake-embed"


def test_read_without_a_meta_file_uses_the_default_floor(tmp_path):
    shutil.copy(FIXTURES / "candidates.jsonl", tmp_path / "c.jsonl")
    c = Candidates.read(tmp_path / "c.jsonl")
    assert len(c.rows) == 2 and c.floor == 0.6 and c.capped is False


def test_repr_plain_text():
    rows = [
        {"id": s, "text": s, "max_similarity": v, "best_seed": "a"}
        for s, v in [("x", 0.8), ("y", 0.61), ("z", 0.62)]
    ]
    text = repr(Candidates(rows, floor=0.6))
    assert text.splitlines()[0] == "3 candidates (floor 0.60)"
    assert "0.600-0.625  2" in text and "0.750+  1" in text
    assert "WARNING" not in text
    warned = repr(Candidates(rows, capped=True))
    assert "WARNING: results were capped" in warned


def test_default_out_is_under_settings_root(tmp_path):
    get_candidates(local(), seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS))
    rows = (tmp_path / "root" / "candidates.jsonl").read_text().splitlines()
    assert [json.loads(r)["id"] for r in rows] == [i for i, _ in WANT]
    assert (tmp_path / "root" / "candidates.meta.json").exists()
    assert (tmp_path / "root" / "cache").is_dir()  # seed embeddings cached


def test_out_false_and_cache_false_write_nothing(tmp_path):
    get_candidates(
        local(),
        seeds=["alpha", "beta"],
        embedder=StubEmbedder(SEEDS),
        out=False,
        cache=False,
    )
    assert not (tmp_path / "root").exists()


def test_out_path_and_cache_path(tmp_path):
    out, cache = tmp_path / "x" / "c.jsonl", tmp_path / "mycache"
    get_candidates(
        local(),
        seeds=["alpha", "beta"],
        embedder=StubEmbedder(SEEDS),
        out=out,
        cache=cache,
    )
    assert out.exists() and (tmp_path / "x" / "c.meta.json").exists()
    assert len(list(cache.glob("*.json"))) == 3  # two vectors and the ledger
    assert not (tmp_path / "root").exists()


def test_seeds_as_list_and_as_csv(tmp_path):
    csv_path = tmp_path / "seeds.csv"
    csv_path.write_text("seed\nalpha\n\n  beta  \n")
    assert read_seeds(csv_path) == ["alpha", "beta"]
    assert read_seeds(str(csv_path)) == ["alpha", "beta"]
    csv_path.write_text("alpha\nbeta\n")  # no header
    assert read_seeds(csv_path) == ["alpha", "beta"]
    corpus = local()
    a = get_candidates(
        corpus, seeds=read_seeds(csv_path), embedder=StubEmbedder(SEEDS), out=False
    )
    b = get_candidates(
        corpus, seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS), out=False
    )
    assert a.rows == b.rows and ids(a) == WANT


def test_a_bare_string_is_not_a_list_of_seeds(tmp_path):
    with pytest.raises(TypeError, match="list"):
        get_candidates(local(), seeds="alpha", embedder=StubEmbedder(SEEDS))


def test_changed_seed_reembeds_only_that_seed_and_a_repeat_embeds_nothing(tmp_path):
    corpus = local()
    vectors = {**SEEDS, "gamma": [0, 0, 1]}
    emb = StubEmbedder(vectors)
    get_candidates(corpus, seeds=["alpha", "beta"], embedder=emb, out=False)
    assert emb.calls == ["alpha", "beta"]
    get_candidates(corpus, seeds=["alpha", "beta"], embedder=emb, out=False)
    assert emb.calls == ["alpha", "beta"]  # identical: no new calls
    get_candidates(corpus, seeds=["alpha", "gamma"], embedder=emb, out=False)
    assert emb.calls == ["alpha", "beta", "gamma"]  # only the changed seed
    assert cost.breakdown(None)["m"]["calls"] == 3  # hits are not recorded as spend


def test_cache_false_embeds_every_time(tmp_path):
    corpus = local()
    emb = StubEmbedder(SEEDS)
    for _ in range(2):
        get_candidates(corpus, seeds=["alpha"], embedder=emb, out=False, cache=False)
    assert emb.calls == ["alpha", "alpha"]


def test_the_pre006_seed_embedding_entry_is_a_hit(tmp_path):
    cache = tmp_path / "cache"
    shutil.copytree(FIXTURES / "cache", cache)
    emb = StubEmbedder({}, name="fake-embed")  # any live call is a KeyError
    c = get_candidates(
        Table(
            FIXTURES / "corpus.jsonl",
            id_column="id",
            vector_column="embedding",
            embedding_model="fake-embed",
        ),
        seeds=["alpha seed"],
        embedder=emb,
        out=False,
        cache=cache,
    )
    assert emb.calls == []
    assert [(r["id"], r["best_seed"]) for r in c.rows] == [
        ("a1", "alpha seed"),
        ("a2", "alpha seed"),
    ]
    assert c.rows[0]["max_similarity"] == pytest.approx(1.0)
    assert c.rows[1]["max_similarity"] == pytest.approx(0.8)


def test_embedding_model_mismatch_raises(tmp_path):
    corpus = local(model="other")
    with pytest.raises(ValueError, match="mismatch"):
        get_candidates(corpus, seeds=["alpha"], embedder=StubEmbedder(SEEDS), out=False)


def test_a_model_string_is_wrapped_and_names_the_cache_key(tmp_path, monkeypatch):
    made = []
    stub = StubEmbedder(SEEDS)

    def fake(name):
        made.append(name)
        return stub

    monkeypatch.setattr(candidates, "Embedder", fake)
    corpus = local(model="openai:text-embedding-3-small")
    get_candidates(
        corpus, seeds=["alpha"], embedder="openai:text-embedding-3-small", out=False
    )
    assert made == ["openai:text-embedding-3-small"]
    key = cost.cache_key("openai:text-embedding-3-small", "embed_query", "alpha")
    assert (cost.cache_get(None, key) or {})["output"] == [1.0, 0.0, 0.0]


def test_async_and_sync_agree_also_inside_a_running_loop(tmp_path):
    corpus = local()
    sync = get_candidates(
        corpus, seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS), out=False
    )
    assert ids(sync) == WANT


async def test_aget_candidates_and_get_candidates_in_a_running_loop_agree(tmp_path):
    corpus = local()
    a = await aget_candidates(
        corpus, seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS), out=False
    )
    b = get_candidates(
        corpus, seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS), out=False
    )
    assert ids(a) == WANT and a.rows == b.rows


HITS = [
    # alpha: i1 ties with beta
    [("i0", "t0", 1.0), ("i1", "t1", 0.8), ("i5", "t5", 0.7), ("i2", "t2", 0.6)],
    # beta
    [("i3", "t3", 1.0), ("i4", "t4", 0.866), ("i1", "t1", 0.8), ("i5", "t5", 0.75)],
]
PG_WANT = [
    ("i0", "alpha", 1.0),
    ("i3", "beta", 1.0),
    ("i4", "beta", 0.866),
    ("i1", "alpha", 0.8),
    ("i5", "beta", 0.75),
    ("i2", "alpha", 0.6),
]


def test_pgvector_exact_is_one_query_and_merges_like_the_per_seed_path(monkeypatch):
    calls = []

    def stub(corpus, vectors, floor, progress=None, stop=None):
        calls.append((corpus, vectors, floor))
        return HITS, True

    def no_per_seed(*a, **k):
        raise AssertionError("search_vectors() must not run in exact mode")

    monkeypatch.setattr(candidates, "search_pg_exact", stub)
    monkeypatch.setattr(candidates, "search_vectors", no_per_seed)
    pg = PgCorpus("t")
    c = get_candidates(
        pg, seeds=["alpha", "beta"], embedder=StubEmbedder(SEEDS), out=False
    )
    assert calls == [(pg, [[1, 0, 0], [0, 1, 0]], 0.6)]
    assert [(r["id"], r["best_seed"], r["max_similarity"]) for r in c.rows] == PG_WANT
    # i1: alpha 0.8 ties beta 0.8 -> earlier seed; i5: beta 0.75 beats alpha 0.7
    assert c.capped is True and "WARNING" in repr(c)


def test_pgvector_exact_queries_once_however_many_seeds(monkeypatch):
    calls = []

    def stub(corpus, vectors, floor, progress=None, stop=None):
        calls.append(len(vectors))
        return [[] for _ in vectors], False

    monkeypatch.setattr(candidates, "search_pg_exact", stub)
    vec = {"a": [1], "b": [2], "c": [3], "d": [4]}
    c = get_candidates(
        PgCorpus("t"), seeds=list(vec), embedder=StubEmbedder(vec), out=False
    )
    assert calls == [4] and c.rows == [] and c.capped is False


@pytest.mark.parametrize("kind", ["s3", "index"])
def test_other_corpora_search_once_per_seed(monkeypatch, kind):
    corpus = S3Corpus("b", "i") if kind == "s3" else PgCorpus("t", search="index")
    calls = []

    def per_seed(corpus, vector, floor, *, embedding_model):
        calls.append((vector, floor, embedding_model))
        return [("i0", "t0", 0.9)], kind == "s3"

    def no_exact(*a, **k):
        raise AssertionError("search_pg_exact must not run")

    monkeypatch.setattr(candidates, "search_vectors", per_seed)
    monkeypatch.setattr(candidates, "search_pg_exact", no_exact)
    c = get_candidates(
        corpus,
        seeds=["alpha", "beta"],
        embedder=StubEmbedder(SEEDS),
        floor=0.7,
        out=False,
    )
    assert calls == [([1, 0, 0], 0.7, "m"), ([0, 1, 0], 0.7, "m")]
    assert ids(c) == [("i0", "alpha")] and c.floor == 0.7
    assert c.capped is (kind == "s3")


def test_floor_is_applied_and_recorded(tmp_path):
    c = get_candidates(
        local(),
        seeds=["alpha", "beta"],
        embedder=StubEmbedder(SEEDS),
        floor=0.7,
        out=False,
    )
    assert ids(c) == [("i3", "beta"), ("i2", "beta")] and c.floor == 0.7


@pytest.mark.parametrize(
    ("sim", "band"),
    [
        (0.5999, -1),
        (0.60, 0),
        (0.6249, 0),
        (0.625, 1),
        (0.70, 4),
        (0.7249, 4),
        (0.725, 5),
        (0.7499, 5),
        (0.75, 6),
        (0.99, 6),
    ],
)
def test_band_of(sim, band):
    assert candidates.band_of(sim) == band


def test_band_counts():
    rows = [{"max_similarity": s} for s in (0.60, 0.61, 0.625, 0.75, 0.9)]
    assert candidates.band_counts(rows) == [2, 1, 0, 0, 0, 0, 2]


def test_seeds_digest_is_sha256_of_json_list():
    import hashlib

    assert (
        candidates.seeds_digest(["a", "b"]) == hashlib.sha256(b'["a", "b"]').hexdigest()
    )
    assert candidates.seeds_digest(["a", "b"]) != candidates.seeds_digest(["b", "a"])


def test_top_seeds_function_at_two_thresholds():
    rows = [
        {"max_similarity": s, "best_seed": b}
        for s, b in [(0.61, "A"), (0.62, "A"), (0.63, "A"), (0.7, "B"), (0.8, "B")]
    ]
    assert candidates.top_seeds(rows, 0.6) == [("A", 3), ("B", 2)]
    assert candidates.top_seeds(rows, 0.7) == [("B", 2)]
    assert len(candidates.top_seeds(rows, 0.6, n=1)) == 1


# --- source: lists that did not come from seeds ---------------------------------------------------


def kw_list():
    rows = [
        {"id": "a", "text": "one", "terms_matched": 2, "matches": 3},
        {"id": "b", "text": "two", "terms_matched": 1, "matches": 1},
    ]
    return Candidates(rows, floor=None, source="keywords")


def all_list():
    return Candidates(
        [{"id": "a", "text": "one"}, {"id": "b", "text": "two"}],
        floor=None,
        source="all",
    )


def test_source_defaults_to_seeds_and_other_fields_are_none_outside_seeds():
    assert Candidates([]).source == "seeds"
    c = kw_list()
    assert c.floor is None and c.seeds_digest is None and c.embedding_model is None
    assert c.capped is False


@pytest.mark.parametrize("make", [kw_list, all_list])
@pytest.mark.parametrize("call", ["above", "bands", "top_seeds"])
def test_similarity_operations_refuse_other_sources(make, call):
    c = make()
    args = {"above": (0.7,), "bands": (), "top_seeds": (0.7,)}[call]
    with pytest.raises(
        ValueError, match=rf"{call} needs similarity scores.*{c.source}"
    ):
        getattr(c, call)(*args)


def test_seed_operations_are_unchanged_by_the_source_field():
    c = Candidates([{"id": "x", "text": "t", "max_similarity": 0.7, "best_seed": "s"}])
    assert c.above(0.7).rows == c.rows and c.bands()[4] == 1


def test_non_seed_lists_round_trip_with_source_and_rank_values(tmp_path):
    for c in (kw_list(), all_list()):
        c.write(tmp_path / "c.jsonl")
        meta = json.loads((tmp_path / "c.meta.json").read_text())
        assert meta["source"] == c.source and meta["floor"] is None
        back = Candidates.read(tmp_path / "c.jsonl")
        assert back.rows == c.rows and back.source == c.source and back.floor is None


def test_a_file_without_source_loads_as_seeds_with_its_bands():
    c = Candidates.read(FIXTURES / "candidates.jsonl")
    assert c.source == "seeds" and c.bands()[:2] == [0, 0] and sum(c.bands()) == 2


def test_other_sources_repr_says_where_they_came_from_and_never_mentions_scores():
    assert repr(kw_list()) == "2 candidates (from keywords)"
    assert repr(all_list()) == "2 candidates (whole corpus)"
    for c in (kw_list(), all_list()):
        both = (repr(c) + c._repr_html_()).lower()
        for word in ("floor", "similarity", "seed", "band"):
            assert word not in both, (c.source, word)
    html = kw_list()._repr_html_()
    assert "terms matched" in html and "<td" in html


def test_sample_and_frames_work_on_every_source():
    for c in (kw_list(), all_list()):
        got = c.sample(1, seed=1)
        assert got.source == c.source and len(got.rows) == 1
        assert c.to_polars().height == 2 and len(c.to_pandas()) == 2


def test_limit_keeps_the_most_similar():
    got = get_candidates(
        local(),
        seeds=["alpha", "beta"],
        embedder=StubEmbedder(SEEDS),
        limit=2,
        out=False,
    )
    assert ids(got) == WANT[:2]


def test_limit_and_seeds_are_checked():
    emb = StubEmbedder(SEEDS)
    with pytest.raises(ValueError, match="limit"):
        get_candidates(local(), seeds=["alpha"], embedder=emb, limit=0, out=False)
    with pytest.raises(ValueError, match="seeds"):
        get_candidates(local(), seeds=[], embedder=emb, out=False)
    assert emb.calls == []


def test_seeds_and_embedder_are_keyword_only():
    with pytest.raises(TypeError):
        get_candidates(local(), ["alpha"], embedder=StubEmbedder(SEEDS))  # ty: ignore[too-many-positional-arguments]


# --- no filter: the whole corpus ------------------------------------------------------------------


def plain(n=4):
    return Table(
        [{"id": f"r{i}", "text": f"text {i}"} for i in range(n)], id_column="id"
    )


def test_no_filter_returns_the_whole_corpus_in_table_order():
    got = get_candidates(plain(), out=False)
    assert got.source == "all" and got.floor is None and got.capped is False
    assert got.rows == [{"id": f"r{i}", "text": f"text {i}"} for i in range(4)]
    assert repr(got) == "4 candidates (whole corpus)"


def test_limit_keeps_the_first_rows_of_the_table():
    assert [r["id"] for r in get_candidates(plain(), limit=2, out=False).rows] == [
        "r0",
        "r1",
    ]


def test_an_empty_corpus_gives_an_empty_result_that_says_so():
    got = get_candidates(Table([]), out=False)
    assert got.rows == [] and repr(got) == "0 candidates (whole corpus)"


def test_the_same_text_under_two_ids_stays_two_rows():
    table = Table(
        [{"id": "a", "text": "same"}, {"id": "b", "text": "same"}], id_column="id"
    )
    assert [r["id"] for r in get_candidates(table, out=False).rows] == ["a", "b"]


@pytest.mark.parametrize(
    ("kwargs", "word"),
    [
        ({"embedder": "x"}, "embedder"),
        ({"floor": 0.7}, "floor"),
        ({"cache": False}, "cache"),
    ],
)
def test_seed_only_arguments_are_refused_without_seeds(kwargs, word):
    with pytest.raises(ValueError, match=word):
        get_candidates(plain(), out=False, **kwargs)


def test_seeds_without_an_embedder_are_refused():
    with pytest.raises(ValueError, match="embedder"):
        get_candidates(plain(), seeds=["alpha"], out=False)


def test_the_read_runs_off_the_event_loop_thread(monkeypatch):
    seen = []
    real = candidates.table_rows
    monkeypatch.setattr(
        candidates,
        "table_rows",
        lambda *a, **k: seen.append(threading.get_ident()) or real(*a, **k),
    )
    get_candidates(plain(), out=False)
    assert seen and seen[0] != threading.get_ident()


async def test_the_sync_form_works_inside_a_running_loop():
    assert len(get_candidates(plain(), out=False).rows) == 4


def test_only_seed_results_write_the_default_file(tmp_path):
    get_candidates(local(), seeds=["alpha"], embedder=StubEmbedder(SEEDS))
    path = tmp_path / "root" / "candidates.jsonl"
    before = (path.read_bytes(), path.with_suffix(".meta.json").read_bytes())
    get_candidates(plain(), limit=5)
    assert (path.read_bytes(), path.with_suffix(".meta.json").read_bytes()) == before


def test_a_path_writes_the_whole_corpus_list_and_nothing_else_does(tmp_path):
    get_candidates(plain())
    assert not (tmp_path / "root").exists()
    out = tmp_path / "x" / "all.jsonl"
    got = get_candidates(plain(), out=out)
    back = Candidates.read(out)
    assert back.rows == got.rows and back.source == "all"
