import keyring
import pytest
from keyring.backend import KeyringBackend
from keyring.errors import PasswordDeleteError
from pydantic_ai import models


class MemoryKeyring(KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self):
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) not in self.store:
            raise PasswordDeleteError("not found")
        del self.store[(service, username)]


@pytest.fixture(autouse=True)
def isolated_system(tmp_path, monkeypatch):
    """No test may reach the real ~/.config or the real keyring."""
    monkeypatch.setenv("HUNCHES_HOME", str(tmp_path / "hunches-home"))
    previous = keyring.get_keyring()
    keyring.set_keyring(MemoryKeyring())
    yield
    keyring.set_keyring(previous)


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


@pytest.fixture
def no_keyring():
    """The `fail` backend keyring picks on headless systems: every call raises NoKeyringError."""
    from keyring.backends.fail import Keyring as FailKeyring

    keyring.set_keyring(FailKeyring())
