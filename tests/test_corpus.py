import dataclasses

import pytest

from hunches.search import LocalCorpus, PgCorpus, S3Corpus


def test_pg_defaults_are_the_old_pg_defaults():
    # hand-written from files.PG_DEFAULTS and the Config fields without a default
    c = PgCorpus("public.docs")
    assert (c.id_column, c.text_column, c.vector_column) == ("id", "text", "embedding")
    assert (c.text_table, c.text_id_column) == (None, None)
    assert c.url_env == "HUNCHES_PG_URL"
    assert (c.search, c.auth) == ("exact", "url")
    assert (c.statement_timeout_s, c.aws_region, c.aws_profile) == (None, None, None)
    assert c.max_result_mb == 512


def test_s3_and_local_fields():
    assert S3Corpus("b", "i").region is None
    assert S3Corpus("b", "i", region="eu-west-1").region == "eu-west-1"
    assert LocalCorpus("some/dir").dir == "some/dir"


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


@pytest.mark.parametrize(
    "corpus", [LocalCorpus("d"), S3Corpus("b", "i"), PgCorpus("t")]
)
def test_frozen(corpus):
    field = dataclasses.fields(corpus)[0].name
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(corpus, field, "x")
    assert corpus == dataclasses.replace(corpus)  # a value object
    assert hash(corpus) == hash(dataclasses.replace(corpus))


def test_only_pgvector_has_a_check():
    assert hasattr(PgCorpus("t"), "check")
    assert not hasattr(LocalCorpus("d"), "check")
    assert not hasattr(S3Corpus("b", "i"), "check")


def test_the_url_is_never_a_field():
    for corpus in (PgCorpus("t"),):
        assert not any(
            "url" in f.name and f.name != "url_env" for f in dataclasses.fields(corpus)
        )
