import pytest
from pydantic import ValidationError

from hunches import files
from hunches.files import Config
from hunches.taxonomy import Label, Taxonomy


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def test_root_and_ensure_root(tmp_path):
    assert files.root() == files.Path(".hunches")
    files.ensure_root()
    files.ensure_root()
    assert (tmp_path / ".hunches").is_dir()


def test_config_round_trip():
    config = Config(
        backend="s3",
        s3_bucket="b",
        s3_index='i"x',
        embedding_model="openai:text-embedding-3-small",
        classifier_model="openai:gpt-5-mini",
        s3_region="eu-west-1",
        target_metric="macro_f1",
        target_score=0.85,
    )
    files.ensure_root()
    files.write_config(config)
    assert files.read_config() == config
    assert config.classifier_model == "openai:gpt-5-mini"
    assert Config(classifier_model="c").target_score == 0.90


def test_old_model_keys_load_and_are_not_written_back():
    files.write_text(
        "config.toml",
        'corpus_dir = "c"\nembedding_model = "m"\n'
        'smart_model = "anthropic:big"\ncheap_model = "anthropic:small"\n',
    )
    config = files.read_config()
    assert config.classifier_model == "anthropic:small"
    files.write_config(config)
    text = (files.root() / "config.toml").read_text()
    assert "assistant" not in text and "smart_model" not in text
    assert "cheap_model" not in text and "s3_region" not in text


def test_new_key_wins_over_old_key():
    files.write_text(
        "config.toml",
        'embedding_model = "m"\nclassifier_model = "new"\ncheap_model = "old"\n',
    )
    assert files.read_config().classifier_model == "new"


def test_jsonl_write_append_read():
    assert files.read_jsonl("x.jsonl") == []
    files.write_jsonl("x.jsonl", [{"id": "a", "text": "héllo"}])
    files.append_jsonl("x.jsonl", {"id": "b", "text": "w"})
    assert files.read_jsonl("x.jsonl") == [
        {"id": "a", "text": "héllo"},
        {"id": "b", "text": "w"},
    ]


def test_append_jsonl_flushes_each_line():
    files.append_jsonl("x.jsonl", {"id": "a"})
    assert (files.root() / "x.jsonl").read_text() == '{"id": "a"}\n'


def test_text_files_round_trip():
    assert files.read_text("brief.md") is None
    for name in ("seeds.csv", "brief.md", "prompt.md"):
        files.write_text(name, f"content of {name}\n")
        assert files.read_text(name) == f"content of {name}\n"


def test_taxonomy_round_trip_through_the_files_wrappers():
    tax = Taxonomy(
        mode="multi", labels=[Label(name="a", description="A: thing"), Label(name="b")]
    )
    files.write_text("placeholder", "")
    files.write_taxonomy(tax)
    assert files.read_taxonomy() == tax


def test_models_have_no_default_so_system_settings_is_the_only_source():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Config()  # ty: ignore[missing-argument]


def test_local_and_s3_configs_write_no_pg_fields():
    files.ensure_root()
    files.write_config(Config(classifier_model="c"))
    local = files.Path(".hunches/config.toml").read_text()
    assert (
        local
        == 'backend = "local"\nembedding_model = ""\nclassifier_model = "c"\ntarget_metric = "accuracy"\ntarget_score = 0.9\n'
    )
    files.write_config(
        Config(
            backend="s3",
            s3_bucket="b",
            s3_index="i",
            classifier_model="c",
        )
    )
    assert "pg_" not in files.Path(".hunches/config.toml").read_text()


def test_old_configs_without_pg_fields_load():
    files.ensure_root()
    files.Path(".hunches/config.toml").write_text(
        'backend = "s3"\ns3_bucket = "b"\ns3_index = "i"\nassistant_model = "a"\n'
        'classifier_model = "c"\n'
    )
    config = files.read_config()
    assert config.backend == "s3" and config.pg_table is None
    assert config.pg_search is None and config.pg_auth is None


def test_pgvector_config_round_trips_and_omits_unset_fields():
    config = Config(
        backend="pgvector",
        pg_table="public.docs",
        pg_statement_timeout_s=0,
        pg_search="index",
        pg_auth="rds_iam",
        pg_aws_region="eu-west-1",
        embedding_model="openai:text-embedding-3-small",
        classifier_model="c",
    )
    files.ensure_root()
    files.write_config(config)
    text = files.Path(".hunches/config.toml").read_text()
    assert 'backend = "pgvector"' in text and 'pg_table = "public.docs"' in text
    assert "pg_statement_timeout_s = 0" in text  # 0 is a value, not unset
    for unset in ("pg_id_column", "pg_url_var", "pg_aws_profile", "s3_bucket"):
        assert unset not in text
    assert files.read_config() == config


def test_pg_defaults_apply_when_read_not_when_stored():
    config = Config(backend="pgvector", pg_table="t", classifier_model="c")
    assert config.pg_id_column is None
    got = {
        name: files.pg_setting(config, name)
        for name in (
            "pg_id_column",
            "pg_text_column",
            "pg_vector_column",
            "pg_url_var",
            "pg_search",
            "pg_auth",
            "pg_statement_timeout_s",
            "pg_aws_region",
            "pg_aws_profile",
        )
    }
    assert got == {
        "pg_id_column": "id",
        "pg_text_column": "text",
        "pg_vector_column": "embedding",
        "pg_url_var": "HUNCHES_PG_URL",
        "pg_search": "exact",
        "pg_auth": "url",
        "pg_statement_timeout_s": None,
        "pg_aws_region": None,
        "pg_aws_profile": None,
    }
    set_ = Config(
        backend="pgvector",
        pg_table="t",
        pg_id_column="pk",
        pg_statement_timeout_s=0,
        classifier_model="c",
    )
    assert files.pg_setting(set_, "pg_id_column") == "pk"
    assert files.pg_setting(set_, "pg_statement_timeout_s") == 0


@pytest.mark.parametrize(
    "field,value",
    [("pg_search", "fast"), ("pg_auth", "password"), ("backend", "mysql")],
)
def test_invalid_pg_choices_are_rejected(field, value):
    with pytest.raises(ValidationError):
        Config(**{field: value}, classifier_model="c")
