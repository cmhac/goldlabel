import importlib
import re
import warnings
from typing import Any

import pytest
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage

from hunches.candidates import get_candidates
from hunches.search import PgCorpus, S3Corpus, Table
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


# --- server-side filtering -------------------------------------------------------------------------

NEEDLE_ROWS = [
    ("i4", "a needle here"),
    ("i11", "needle and Needle"),
    ("i20", "NEEDLE hay needle"),
]


def served(monkeypatch, answer, **fields):
    conn = Conn(answer)
    return conn, setup(monkeypatch, conn, **fields)


def test_plain_terms_become_one_ilike_statement(monkeypatch):
    conn, corpus = served(monkeypatch, NEEDLE_ROWS)
    get_candidates(corpus, keywords=["needle", "hay"], server_side=True, out=False)
    assert len(conn.executed) == 1
    sql, params, name, itersize = conn.executed[0]
    assert sql == (
        'SELECT "id", "text" FROM "public"."docs" '
        'WHERE "text" ILIKE ANY(%s::text[]) ORDER BY "id"'
    )
    assert params == (["%needle%", "%hay%"],)
    assert name is not None and itersize == search.PG_BATCH


def test_regex_strings_are_sent_unchanged_with_the_regex_operator(monkeypatch):
    conn, corpus = served(monkeypatch, NEEDLE_ROWS)
    get_candidates(
        corpus, keywords=["ne+dle", "(?i)HAY"], regex=True, server_side=True, out=False
    )
    sql, params, *_ = conn.executed[0]
    assert sql == (
        'SELECT "id", "text" FROM "public"."docs" '
        'WHERE "text" ~ ANY(%s::text[]) ORDER BY "id"'
    )
    assert params == (["ne+dle", "(?i)HAY"],)


def test_two_tables_filter_the_joined_text(monkeypatch):
    conn, corpus = served(
        monkeypatch, NEEDLE_ROWS, text_table="public.texts", text_id_column="doc_id"
    )
    get_candidates(corpus, keywords=["needle"], server_side=True, out=False)
    assert conn.executed[0][0] == (
        'SELECT t."id", x."text" FROM "public"."docs" t '
        'JOIN "public"."texts" x ON x."doc_id" = t."id" '
        'WHERE x."text" ILIKE ANY(%s::text[]) ORDER BY t."id"'
    )


def test_like_wildcards_and_the_backslash_in_a_term_are_escaped(monkeypatch):
    conn, corpus = served(monkeypatch, [])
    get_candidates(corpus, keywords=["a%b_c\\d"], server_side=True, out=False)
    assert conn.executed[0][1] == (["%a\\%b\\_c\\\\d%"],)  # %a\%b\_c\\d%


def test_no_term_text_ever_reaches_the_statement(monkeypatch):
    evil = "'; DROP TABLE docs; --"
    for regex in (False, True):
        conn, corpus = served(monkeypatch, [])
        get_candidates(
            corpus, keywords=[evil], regex=regex, server_side=True, out=False
        )
        sql, params, *_ = conn.executed[0]
        assert "DROP" not in sql and "--" not in sql
        assert any(evil in p for p in params[0])


@pytest.mark.parametrize(
    ("make", "message"),
    [
        (lambda: {"server_side": True}, "server_side.*keywords"),
        (
            lambda: {"keywords": [re.compile("a")], "server_side": True},
            r"re\.compile\('a'\)|'a'.*regex=True",
        ),
    ],
)
def test_server_side_refusals_happen_before_any_connection(monkeypatch, make, message):
    def no_connection(corpus):
        raise AssertionError("must not connect")

    monkeypatch.setattr(search, "pg_connect", no_connection)
    with pytest.raises(ValueError, match=message):
        get_candidates(PgCorpus("t"), out=False, **make())


@pytest.mark.parametrize("corpus", [Table([{"text": "x"}]), S3Corpus("b", "i")])
def test_only_a_postgres_corpus_can_filter_on_the_server(corpus):
    with pytest.raises(ValueError, match="PgCorpus"):
        get_candidates(corpus, keywords=["x"], server_side=True, out=False)


def test_a_server_answer_is_ranked_and_limited_like_the_python_side(monkeypatch):
    _, corpus = served(monkeypatch, NEEDLE_ROWS)
    got = get_candidates(corpus, keywords=["needle"], server_side=True, out=False)
    assert [(r["id"], r["terms_matched"], r["matches"]) for r in got.rows] == [
        ("i11", 1, 2),
        ("i20", 1, 2),
        ("i4", 1, 1),
    ]
    _, corpus = served(monkeypatch, NEEDLE_ROWS)
    limited = get_candidates(
        corpus, keywords=["needle"], server_side=True, limit=2, out=False
    )
    assert [r["id"] for r in limited.rows] == ["i11", "i20"]


def test_a_row_python_counts_as_zero_is_kept_last_with_one_warning(monkeypatch):
    _, corpus = served(monkeypatch, [("z", "unrelated"), ("a", "needle")])
    with pytest.warns(UserWarning, match="1 returned row") as caught:
        got = get_candidates(corpus, keywords=["needle"], server_side=True, out=False)
    assert len(caught) == 1
    assert [(r["id"], r["terms_matched"]) for r in got.rows] == [("a", 1), ("z", 0)]


def test_no_warning_when_python_agrees_with_the_server(monkeypatch):
    _, corpus = served(monkeypatch, NEEDLE_ROWS)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        get_candidates(corpus, keywords=["needle"], server_side=True, out=False)


def test_a_regex_python_cannot_compile_is_sent_and_named_in_the_warning(monkeypatch):
    conn, corpus = served(monkeypatch, [("a", "x{1,2}")])
    with pytest.warns(UserWarning, match=r"'\(\?<name>x'"):
        got = get_candidates(
            corpus, keywords=["(?<name>x"], regex=True, server_side=True, out=False
        )
    assert conn.executed[0][1] == (
        ["(?<name>x"],
    )  # the server was asked, Python was not
    assert got.rows[0]["terms_matched"] == 0


def test_a_server_regex_error_names_the_terms(monkeypatch):
    conn = Conn(Exception("invalid regular expression: parentheses () not balanced"))
    corpus = setup(monkeypatch, conn)
    with pytest.raises(RuntimeError, match=r"(?s)not balanced.*terms were \['\('\]"):
        get_candidates(corpus, keywords=["("], regex=True, server_side=True, out=False)


def test_server_side_runs_only_select(monkeypatch):
    conn, corpus = served(monkeypatch, NEEDLE_ROWS)
    get_candidates(corpus, keywords=["needle"], server_side=True, out=False)
    assert all(e[0].lstrip().upper().startswith("SELECT") for e in conn.executed)
