import tomllib
from pathlib import Path

PROJECT = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())[
    "project"
]


def test_only_local_extra():
    assert list(PROJECT["optional-dependencies"]) == ["local"]
    assert PROJECT["optional-dependencies"]["local"] == [
        "pydantic-ai-slim[sentence-transformers]"
    ]


def test_backends_are_plain_dependencies():
    deps = PROJECT["dependencies"]
    assert "boto3" in deps
    assert "psycopg[binary]" in deps
