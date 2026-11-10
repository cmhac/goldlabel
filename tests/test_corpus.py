import dataclasses

import polars as pl
import pytest

from goldlabel.search import PgCorpus, S3Corpus, Table, describe


def test_pg_defaults_are_the_old_pg_defaults():
    # hand-written from files.PG_DEFAULTS and the Config fields without a default
    c = PgCorpus("public.docs")
    assert (c.id_column, c.text_column, c.vector_column) == ("id", "text", "embedding")
    assert (c.text_table, c.text_id_column) == (None, None)
    assert c.url_env == "GOLDLABEL_PG_URL"
    assert (c.search, c.auth) == ("exact", "url")
    assert (c.statement_timeout_s, c.aws_region, c.aws_profile) == (None, None, None)
    assert c.max_result_mb == 512


def test_s3_fields():
    assert S3Corpus("b", "i").region is None
    assert S3Corpus("b", "i", region="eu-west-1").region == "eu-west-1"


@pytest.mark.parametrize(
    "make",
    [
        lambda: PgCorpus(""),
        lambda: PgCorpus("t", search="fast"),
        lambda: PgCorpus("t", auth="password"),
        lambda: PgCorpus("t", url_env=""),
        lambda: PgCorpus("t", max_result_mb=-1),
        lambda: PgCorpus("t", statement_timeout_s=-5),
        lambda: S3Corpus("", "i"),
        lambda: S3Corpus("b", ""),
    ],
)
def test_validation(make):
    with pytest.raises(ValueError):
        make()


def test_pg_zero_means_no_limit_and_no_timeout():
    c = PgCorpus("t", max_result_mb=0, statement_timeout_s=0)
    assert (c.max_result_mb, c.statement_timeout_s) == (0, 0)


def test_the_error_names_the_field():
    with pytest.raises(ValueError, match="table is required"):
        PgCorpus("")
    with pytest.raises(ValueError, match="search must be"):
        PgCorpus("t", search="fast")


@pytest.mark.parametrize("corpus", [S3Corpus("b", "i"), PgCorpus("t")])
def test_frozen(corpus):
    field = dataclasses.fields(corpus)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(corpus, field, "x")
    assert corpus == dataclasses.replace(corpus)  # a value object
    assert hash(corpus) == hash(dataclasses.replace(corpus))


def test_only_pgvector_has_a_check():
    assert hasattr(PgCorpus("t"), "check")
    assert not hasattr(S3Corpus("b", "i"), "check")


def test_the_url_is_never_a_field():
    for corpus in (PgCorpus("t"),):
        assert not any(
            "url" in f.name and f.name != "url_env" for f in dataclasses.fields(corpus)
        )


def test_describe_a_table_file_gives_the_file_name_only_never_the_folder():
    t = Table("/home/someone/private/corpus.jsonl", id_column="id")
    assert describe(t) == (
        "the table file corpus.jsonl (text column text, id column id)",
        None,
    )


def test_describe_an_in_memory_table_and_its_filter():
    rows = [{"id": "a", "body": "x"}]
    assert describe(Table(rows, text_column="body")) == (
        "an in-memory table (list of rows) (text column body, ids by position)",
        None,
    )
    expr = pl.col("year") >= 2024
    source, filter_ = describe(
        Table(pl.DataFrame(rows), text_column="body", where=expr)
    )
    assert (
        source == "an in-memory table (DataFrame) (text column body, ids by position)"
    )
    assert filter_ == str(expr)  # polars' own text of the expression
    assert "year" in filter_


def test_describe_an_s3_index_with_and_without_region_and_filter():
    assert describe(S3Corpus("my-bucket", "posts")) == (
        "the S3 Vectors index posts in bucket my-bucket",
        None,
    )
    assert describe(
        S3Corpus(
            "my-bucket", "posts", region="us-east-1", where={"section": "politics"}
        )
    ) == (
        "the S3 Vectors index posts in bucket my-bucket (us-east-1)",
        '{"section": "politics"}',
    )


def test_describe_a_postgres_table_with_and_without_a_text_table():
    assert describe(PgCorpus("public.docs", where="year >= 2024")) == (
        "the Postgres table public.docs (exact search)",
        "year >= 2024",
    )
    two = PgCorpus("public.docs", text_table="public.texts", search="index")
    assert describe(two) == (
        "the Postgres table public.docs with texts in public.texts (index search)",
        None,
    )


def test_describe_a_postgres_corpus_never_leaks_a_connection_setting(monkeypatch):
    monkeypatch.setenv("MY_DB_URL", "postgresql://user:s3cret@host/db")
    c = PgCorpus(
        "public.docs", url_env="MY_DB_URL", aws_profile="secret-profile", auth="rds_iam"
    )
    source, filter_ = describe(c)
    for leaked in ("s3cret", "postgresql://", "MY_DB_URL", "secret-profile", "rds_iam"):
        assert leaked not in source
    assert filter_ is None
