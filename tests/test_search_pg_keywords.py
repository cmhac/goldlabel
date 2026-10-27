import importlib
from typing import Any

import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

from hunches.candidates import get_candidates
from hunches.search import PgCorpus
from hunches.settings import settings

search = importlib.import_module("hunches.search")  # for the pg_connect patch

EXT_VERSION = ("0.8.1", "extensions")


class Cur:
    def __init__(self, conn, name):
        self.conn, self.name, self.itersize = conn, name, None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, query, params=None):
        sql = query if isinstance(query, str) else query.as_string()
        self.conn.executed.append((sql, params, self.name, self.itersize))
        self.rows = self.conn.answers.pop(0)
        if isinstance(self.rows, Exception):
            raise self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def __iter__(self):
        return iter(self.rows)


class Conn:
    """Canned answers, one per execute()."""

    def __init__(self, *answers):
        self.answers, self.executed, self.closed = list(answers), [], False
        self.read_only = True

    def cursor(self, name=None):
        return Cur(self, name)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings.root = tmp_path / "root"
    monkeypatch.delenv("HUNCHES_PG_URL", raising=False)


def setup(monkeypatch, conn, **fields: Any):
    # no result limit, so most tests do not run the size guard's estimate queries
    kwargs: dict[str, Any] = {"table": "public.docs", "max_result_mb": 0, **fields}
    corpus = PgCorpus(**kwargs)
    monkeypatch.setattr(search, "pg_connect", lambda corpus: conn)
    return corpus


def rows(n=30):
    texts = {4: "a needle here", 11: "needle and Needle", 20: "NEEDLE hay needle"}
    return [(f"i{i}", texts.get(i, f"filler {i}")) for i in range(n)]


def test_single_table_statement_and_cursor(monkeypatch):
    conn = Conn(rows(3))
    corpus = setup(monkeypatch, conn)
    got = get_candidates(corpus, out=False)
    assert [(r["id"], r["text"]) for r in got.rows] == rows(3)
    assert len(conn.executed) == 1
    sql, params, name, itersize = conn.executed[0]
    assert sql == 'SELECT "id", "text" FROM "public"."docs" ORDER BY "id"'
    assert params is None and name is not None and itersize == search.PG_BATCH
    assert conn.closed


def test_column_names_are_quoted_identifiers(monkeypatch):
    conn = Conn([])
    corpus = setup(
        monkeypatch, conn, table="docs", id_column="doc id", text_column="body"
    )
    get_candidates(corpus, out=False)
    assert (
        conn.executed[0][0] == 'SELECT "doc id", "body" FROM "docs" ORDER BY "doc id"'
    )


def test_two_table_layout_joins_the_text_table(monkeypatch):
    conn = Conn([("a", "text a"), ("b", "text b")])
    corpus = setup(
        monkeypatch, conn, text_table="public.texts", text_id_column="doc_id"
    )
    got = get_candidates(corpus, out=False)
    assert [r["text"] for r in got.rows] == ["text a", "text b"]
    assert conn.executed[0][0] == (
        'SELECT t."id", x."text" FROM "public"."docs" t '
        'LEFT JOIN "public"."texts" x ON x."doc_id" = t."id" ORDER BY t."id"'
    )


def test_a_missing_text_row_names_the_id(monkeypatch):
    conn = Conn([("a", "text a"), ("b", None)])
    corpus = setup(monkeypatch, conn, text_table="public.texts")
    with pytest.raises(RuntimeError, match="no text row for id 'b'"):
        get_candidates(corpus, out=False)
    assert conn.closed


def test_ids_come_back_as_strings(monkeypatch):
    conn = Conn([(7, "seven")])
    got = get_candidates(setup(monkeypatch, conn), out=False)
    assert got.rows == [{"id": "7", "text": "seven"}]


def test_a_table_without_vectors_or_the_extension_is_read_with_one_statement(
    monkeypatch,
):
    conn = Conn(rows(3))
    get_candidates(setup(monkeypatch, conn), keywords=["filler"], out=False)
    assert len(conn.executed) == 1
    assert (
        "vector" not in conn.executed[0][0].lower()
        and "embedding" not in conn.executed[0][0]
    )
    assert "pg_" not in conn.executed[0][0]


class Emb(Embedder):
    def __init__(self):
        super().__init__(TestEmbeddingModel("m"))

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [[1.0, 0.0, 0.0]],
            inputs=[query],
            input_type="query",
            model_name="m",
            provider_name="test",
            usage=RequestUsage(input_tokens=1),
        )


def test_seed_search_on_a_table_with_no_embedding_column_names_it(monkeypatch):
    conn = Conn([EXT_VERSION], [])  # the extension is there, the column is not
    corpus = setup(monkeypatch, conn, max_result_mb=0)
    with pytest.raises(
        RuntimeError, match='column "embedding" of relation "public.docs"'
    ):
        get_candidates(corpus, seeds=["a"], embedder=Emb(), out=False, cache=False)


def test_keywords_keep_only_hits_ranked_and_limited(monkeypatch):
    conn = Conn(rows())
    got = get_candidates(setup(monkeypatch, conn), keywords=["needle"], out=False)
    # i11 and i20 each match twice, i4 once; the tie keeps table order
    assert [(r["id"], r["terms_matched"], r["matches"]) for r in got.rows] == [
        ("i11", 1, 2),
        ("i20", 1, 2),
        ("i4", 1, 1),
    ]
    limited = get_candidates(
        setup(monkeypatch, Conn(rows())), keywords=["needle"], limit=2, out=False
    )
    assert [r["id"] for r in limited.rows] == ["i11", "i20"]


def test_a_limit_stops_reading_and_still_closes_the_connection(monkeypatch):
    conn = Conn(rows())
    got = get_candidates(setup(monkeypatch, conn), limit=2, out=False)
    assert [r["id"] for r in got.rows] == ["i0", "i1"] and conn.closed


def test_nothing_but_select_runs(monkeypatch):
    conn = Conn(rows())
    get_candidates(setup(monkeypatch, conn), keywords=["needle"], out=False)
    assert all(e[0].lstrip().upper().startswith("SELECT") for e in conn.executed)


# --- the result size guard (whole corpus only) -----------------------------------------------------


def test_a_whole_corpus_over_the_limit_is_refused_before_reading(monkeypatch):
    # planner: 100,000 rows, average text 100 bytes: ~22 MB with the row overhead
    conn = Conn([(100_000,)], [(100,)])
    corpus = setup(monkeypatch, conn, max_result_mb=1)
    with pytest.raises(RuntimeError, match=r"1 MB.*max_result_mb"):
        get_candidates(corpus, out=False)
    assert len(conn.executed) == 2 and conn.closed  # only the two estimate queries


def test_a_limit_makes_a_big_table_fit(monkeypatch):
    conn = Conn([(100_000,)], [(100,)], rows(5))
    corpus = setup(monkeypatch, conn, max_result_mb=1)
    got = get_candidates(corpus, limit=3, out=False)
    assert [r["id"] for r in got.rows] == ["i0", "i1", "i2"]


def test_streaming_aborts_when_the_received_size_passes_the_limit(monkeypatch):
    big = "x" * 600_000  # no statistics: the estimate cannot refuse, the stream must
    conn = Conn([(-1,)], [(None,)], [("a", big), ("b", big), ("c", big)])
    corpus = setup(monkeypatch, conn, max_result_mb=1)
    with pytest.raises(RuntimeError, match=r"already received.*1 MB"):
        get_candidates(corpus, out=False)
    assert conn.closed


def test_zero_means_no_limit_and_no_estimate(monkeypatch):
    conn = Conn(rows(3))
    get_candidates(setup(monkeypatch, conn, max_result_mb=0), out=False)
    assert len(conn.executed) == 1


def test_keyword_search_has_no_size_guard(monkeypatch):
    conn = Conn(rows())  # a limit is set, yet no estimate query runs
    corpus = setup(monkeypatch, conn, max_result_mb=512)
    get_candidates(corpus, keywords=["needle"], out=False)
    assert len(conn.executed) == 1


def test_errors_are_scrubbed_of_the_url(monkeypatch):
    monkeypatch.setenv("HUNCHES_PG_URL", "postgres://u:hunter2@h/db")
    conn = Conn(Exception("could not connect: postgres://u:hunter2@h/db"))
    with pytest.raises(RuntimeError) as e:
        get_candidates(setup(monkeypatch, conn), out=False)
    assert "hunter2" not in str(e.value) and "***" in str(e.value)
