"""Spec 006 task 02: project and store descriptions in the config and the assistant context."""

import tomllib

import pytest
from test_status import complete_project, config

from hunches import files
from hunches.files import Config
from hunches.screens import tune


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def base(**kw) -> Config:
    return Config(assistant_model="a", classifier_model="c", **kw)


def test_old_config_without_descriptions_rewrites_byte_for_byte():
    files.ensure_root()
    files.write_config(base())
    before = (files.root() / "config.toml").read_bytes()
    loaded = files.read_config()
    assert loaded.project_description is None and loaded.store_description is None
    files.write_config(loaded)
    assert (files.root() / "config.toml").read_bytes() == before
    assert b"description" not in before


def test_descriptions_round_trip_with_newlines_quotes_accents_and_an_emoji():
    project = 'Find "bad" news\nline two \\ backslash, café 😀'
    store = "Tweets\tin Español 😀"
    files.ensure_root()
    files.write_config(base(project_description=project, store_description=store))
    text = (files.root() / "config.toml").read_text()
    parsed = tomllib.loads(text)  # the file must be valid TOML
    assert parsed["project_description"] == project
    assert parsed["store_description"] == store
    loaded = files.read_config()
    assert (loaded.project_description, loaded.store_description) == (project, store)


def test_whitespace_only_description_is_stored_as_absent():
    config = base(project_description="  \n ", store_description="  x  ")
    assert config.project_description is None
    assert config.store_description == "x"
    files.ensure_root()
    files.write_config(config)
    assert "project_description" not in (files.root() / "config.toml").read_text()


def test_project_context_says_not_provided_when_absent():
    config()
    assert files.project_context() == "# Project\nnot provided\n\n# Store\nnot provided"


def test_project_context_carries_the_texts():
    files.ensure_root()
    files.write_config(
        base(project_description="find x\nbecause y", store_description="tweets")
    )
    assert files.project_context() == "# Project\nfind x\nbecause y\n\n# Store\ntweets"


def test_status_context_is_the_old_assistant_context_and_assistant_context_prepends_project():
    complete_project()
    status = files.status_context()
    assert status == f"{files.pipeline_status_text()}\n\n{files.gold_coverage_text()}"
    assert status.startswith("# Pipeline status\n")
    assert files.assistant_context() == f"{files.project_context()}\n\n{status}"
    assert files.assistant_context().startswith("# Project\nnot provided\n\n# Store\n")


def test_description_change_keeps_the_tuning_status_digest_but_status_change_moves_it():
    complete_project()
    told = tune.status_digest()
    files.write_config(
        files.read_config().model_copy(update={"project_description": "new text"})
    )
    assert tune.status_digest() == told
    files.write_text("prompt.md", "changed")
    assert tune.status_digest() != told
