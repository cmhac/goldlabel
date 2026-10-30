import pytest
from pydantic_ai import models


@pytest.fixture(autouse=True)
def reset_settings(monkeypatch):
    """`settings.root` is process-wide state: every test starts from the default."""
    from pathlib import Path

    from goldlabel.settings import settings

    monkeypatch.delenv("GOLDLABEL_DIR", raising=False)
    settings.root = Path(".goldlabel")
    yield
    settings.root = Path(".goldlabel")


class _ModelRequestsBlocked:
    """Falsy stand-in for `ALLOW_MODEL_REQUESTS` that remembers it was consulted.

    Code under test may swallow run errors into a message, so a blocked request alone would not
    fail the test; the fixture below fails it at teardown instead.
    """

    def __init__(self):
        self.hits = 0

    def __bool__(self):
        self.hits += 1
        return False


@pytest.fixture(autouse=True)
def no_real_models(monkeypatch):
    """No test may reach a real LLM: unusable keys, and any un-stubbed model request fails the test."""
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "AWS_ACCESS_KEY_ID"):
        monkeypatch.setenv(key, "test-invalid")
    blocked = _ModelRequestsBlocked()
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", blocked)
    yield
    assert not blocked.hits, (
        "test made an un-stubbed (real) model request; use TestModel/FunctionModel"
    )
