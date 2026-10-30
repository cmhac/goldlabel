import importlib

import numpy as np
import pytest

from goldlabel.candidates import get_candidates
from goldlabel.search import S3Corpus, Table

search = importlib.import_module(
    "goldlabel.search"
)  # `goldlabel.search` is the function


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def table():
    # unit vectors at known angles to the query [1, 0]
    vectors = np.array(
        [[1, 0], [0.6, 0.8], [0.5, 0.8660254], [0.59, 0.80752], [0, 1]], np.float32
    )
    rows = [
        {
            "id": f"i{i}",
            "text": f"t{i}",
            "v": (v * 3).tolist(),
        }  # un-normalised on purpose
        for i, v in enumerate(vectors)
    ]
    return Table(rows, id_column="id", vector_column="v", embedding_model="m")


def test_table_floor_inclusive_and_sorted():
    (hits,), capped = search.search_table(table(), [[2.0, 0.0]], 0.6, "m")
    # i1 is exactly 0.6; i3 is 0.59
    assert not capped
    assert [h[0] for h in hits] == ["i0", "i1"]
    assert hits[0] == ("i0", "t0", pytest.approx(1.0))
    assert hits[1][2] == pytest.approx(0.6, abs=1e-6)


class FakeS3:
    """Only the read calls exist: any write call fails with AttributeError."""

    def __init__(self, pages, listing=()):
        self.pages, self.calls = pages, []
        self.listing, self.list_calls = list(listing), []

    def query_vectors(self, **kw):
        self.calls.append(kw)
        return self.pages[len(self.calls) - 1]

    def list_vectors(self, **kw):
        self.list_calls.append(kw)
        page = self.listing[len(self.list_calls) - 1]
        if isinstance(page, Exception):
            raise page
        return page


def vec(key, distance):
    return {"key": key, "distance": distance, "metadata": {"text": f"text {key}"}}


def s3_setup(monkeypatch, pages, listing=()):
    fake = FakeS3(pages, listing)
    monkeypatch.setattr("boto3.client", lambda name, **kw: fake)
    return fake


def s3_search(corpus=None):
    return search.search_vectors(
        corpus or S3Corpus("b", "i"), [1.0, 0.0], 0.6, embedding_model="m"
    )


def test_s3_pages_and_floor(monkeypatch):
    fake = s3_setup(
        monkeypatch,
        [
            {"vectors": [vec("a", 0.25)], "nextToken": "t"},
            {"vectors": [vec("b", 0.4), vec("c", 0.5)]},  # c is below the 0.6 floor
        ],
    )
    hits, capped = s3_search()
    assert [(h[0], h[1]) for h in hits] == [("a", "text a"), ("b", "text b")]
    assert hits[0][2] == pytest.approx(0.75)
    assert not capped
    assert fake.calls[0]["topK"] == search.S3_TOP_K
    assert fake.calls[0]["returnDistance"] and fake.calls[0]["returnMetadata"]
    assert fake.calls[1]["nextToken"] == "t"


def test_s3_capped(monkeypatch):
    monkeypatch.setattr(search, "S3_TOP_K", 2)
    s3_setup(monkeypatch, [{"vectors": [vec("a", 0.1), vec("b", 0.2)]}])
    hits, capped = s3_search()
    assert len(hits) == 2 and capped


def test_s3_uses_the_configured_region(monkeypatch):
    made = []

    def client(name, **kw):
        made.append((name, kw))
        return FakeS3([{"vectors": []}])

    monkeypatch.setattr("boto3.client", client)
    s3_search(S3Corpus("b", "i", region="eu-west-1"))
    assert made == [("s3vectors", {"region_name": "eu-west-1"})]
    made.clear()
    s3_search()  # no region: boto3's own resolution
    assert made == [("s3vectors", {"region_name": None})]


# --- listing without vectors (whole corpus and keywords) -------------------------------------------


def listed(key, text=None):
    return {"key": key, "metadata": {"text": text or f"text {key}"}}


PAGES = [
    {"vectors": [listed("k1"), listed("k2", "a needle")], "nextToken": "t"},
    {"vectors": [listed("k3", "needle needle")]},
]


def test_s3_whole_corpus_lists_every_page_without_vectors(monkeypatch):
    fake = s3_setup(monkeypatch, [], PAGES)
    got = get_candidates(S3Corpus("b", "i"), out=False)
    assert got.source == "all"
    assert [(r["id"], r["text"]) for r in got.rows] == [
        ("k1", "text k1"),
        ("k2", "a needle"),
        ("k3", "needle needle"),
    ]
    first, second = fake.list_calls
    assert first == {
        "vectorBucketName": "b",
        "indexName": "i",
        "returnMetadata": True,
        "maxResults": 1000,
    }
    assert "returnData" not in first and "returnData" not in second
    assert second["nextToken"] == "t"
    assert fake.calls == []  # no query


def test_s3_keywords_keep_only_hits(monkeypatch):
    s3_setup(monkeypatch, [], PAGES)
    got = get_candidates(S3Corpus("b", "i"), keywords=["needle"], out=False)
    assert [(r["id"], r["matches"]) for r in got.rows] == [("k3", 2), ("k2", 1)]


def test_s3_limit_keeps_the_first_listed_and_stops_asking(monkeypatch):
    fake = s3_setup(monkeypatch, [], PAGES)
    got = get_candidates(S3Corpus("b", "i"), limit=1, out=False)
    assert [r["id"] for r in got.rows] == ["k1"] and len(fake.list_calls) == 1


def test_s3_access_denied_names_both_permissions(monkeypatch):
    from botocore.exceptions import ClientError

    denied = ClientError({"Error": {"Code": "AccessDeniedException"}}, "ListVectors")
    s3_setup(monkeypatch, [], [denied])
    with pytest.raises(
        RuntimeError, match="s3vectors:ListVectors.*s3vectors:GetVectors"
    ):
        get_candidates(S3Corpus("b", "i"), out=False)


def test_s3_other_errors_are_not_rewritten(monkeypatch):
    from botocore.exceptions import ClientError

    other = ClientError({"Error": {"Code": "NotFoundException"}}, "ListVectors")
    s3_setup(monkeypatch, [], [other])
    with pytest.raises(ClientError, match="NotFoundException"):
        get_candidates(S3Corpus("b", "i"), out=False)


def test_s3_an_item_without_text_is_an_error(monkeypatch):
    s3_setup(monkeypatch, [], [{"vectors": [{"key": "k", "metadata": {}}]}])
    with pytest.raises(KeyError, match="text"):
        get_candidates(S3Corpus("b", "i"), out=False)


def test_a_corpus_of_the_wrong_kind_is_refused():
    with pytest.raises(TypeError, match="Table.*S3Corpus.*PgCorpus"):
        get_candidates("corpus/", out=False)  # ty: ignore[invalid-argument-type]


# --- the corpus filter (010) ---------------------------------------------------------------------

META = {  # key -> metadata, written by hand; v5 has no year, v6 no tags
    "v1": {"section": "politics", "year": 2023, "tags": ["a", "b"]},
    "v2": {"section": "politics", "year": 2024, "tags": ["c"]},
    "v3": {"section": "sports", "year": 2024, "tags": ["a"]},
    "v4": {"section": "sports", "year": 2025, "tags": []},
    "v5": {"section": "politics", "tags": ["b"]},
    "v6": {"section": "opinion", "year": 2022},
}
LISTING = [
    {
        "vectors": [
            {"key": k, "metadata": {"text": f"needle {k}", **m}}
            for k, m in META.items()
        ]
    }
]


@pytest.mark.parametrize(
    "where, keys",
    [
        ({"section": "politics"}, ["v1", "v2", "v5"]),
        ({"section": {"$eq": "politics"}}, ["v1", "v2", "v5"]),
        ({"tags": "a"}, ["v1", "v3"]),  # $eq on a list: any element (documented)
        ({"section": {"$ne": "politics"}}, ["v3", "v4", "v6"]),
        ({"year": {"$gt": 2023}}, ["v2", "v3", "v4"]),
        ({"year": {"$gte": 2024, "$lte": 2024}}, ["v2", "v3"]),
        ({"year": {"$lt": 2023}}, ["v6"]),
        ({"section": {"$in": ["opinion", "sports"]}}, ["v3", "v4", "v6"]),
        ({"section": {"$nin": ["politics"]}}, ["v3", "v4", "v6"]),
        ({"year": {"$exists": False}}, ["v5"]),
        ({"tags": {"$exists": True}}, ["v1", "v2", "v3", "v4", "v5"]),
        ({"$and": [{"section": "politics"}, {"year": {"$gte": 2024}}]}, ["v2"]),
        ({"$or": [{"section": "opinion"}, {"year": 2025}]}, ["v4", "v6"]),
        # the library's rules where the AWS docs are silent (research R5, unverified)
        ({"section": "politics", "year": 2023}, ["v1"]),  # two keys: AND
        ({"year": {"$ne": 2024}}, ["v1", "v4", "v5", "v6"]),  # missing passes $ne
        (
            {"tags": {"$nin": ["a"]}},
            ["v2", "v4", "v5", "v6"],
        ),  # list: none in; missing passes
        ({"tags": {"$in": ["b", "c"]}}, ["v1", "v2", "v5"]),  # list: any element in
        ({"tags": {"$ne": "a"}}, ["v2", "v4", "v5", "v6"]),  # list: no element equal
    ],
)
def test_s3_listing_keeps_what_the_filter_passes(monkeypatch, where, keys):
    s3_setup(monkeypatch, [], LISTING)
    got = get_candidates(S3Corpus("b", "i", where=where), out=False)
    assert [r["id"] for r in got.rows] == keys


def test_s3_keywords_over_a_filtered_listing(monkeypatch):
    s3_setup(monkeypatch, [], LISTING)
    corpus = S3Corpus("b", "i", where={"section": "sports"})
    got = get_candidates(corpus, keywords=["needle"], out=False)
    assert [r["id"] for r in got.rows] == ["v3", "v4"]


def test_s3_seed_queries_send_the_document_unchanged(monkeypatch):
    where = {"$and": [{"section": "politics"}, {"year": {"$gte": 2024}}]}
    fake = s3_setup(monkeypatch, [{"vectors": []}])
    s3_search(S3Corpus("b", "i", where=where))
    assert fake.calls[0]["filter"] == where
    fake = s3_setup(monkeypatch, [{"vectors": []}])
    s3_search()
    assert "filter" not in fake.calls[0]


def test_s3_starts_with_is_refused_when_listing(monkeypatch):
    s3_setup(monkeypatch, [], LISTING)
    corpus = S3Corpus("b", "i", where={"section": {"$startsWith": "pol"}})
    with pytest.raises(ValueError, match=r"\$startsWith"):
        get_candidates(corpus, out=False)


@pytest.mark.parametrize(
    "where, path",
    [
        ("section = 'x'", "where"),
        ({}, "where"),
        ({"section": {"$like": "x"}}, r"where\['section'\]\['\$like'\]"),
        ({"$not": {"a": 1}}, r"where\['\$not'\]"),
        ({"$and": []}, r"where\['\$and'\]"),
        ({"section": {"$in": []}}, r"where\['section'\]\['\$in'\]"),
        (
            {"$and": [{"year": {"$gte": "2024"}}]},
            r"where\['\$and'\]\[0\]\['year'\]\['\$gte'\]",
        ),
        ({"year": {"$exists": "yes"}}, r"where\['year'\]\['\$exists'\]"),
        ({"tags": ["a"]}, r"where\['tags'\]"),
    ],
)
def test_s3_a_malformed_filter_is_refused_naming_the_path(where, path):
    with pytest.raises(ValueError, match=path):
        S3Corpus("b", "i", where=where)
