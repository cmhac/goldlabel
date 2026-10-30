"""The gold rule text (`gold_rule.md`, package data) and the error type that carries it."""

from importlib import resources

_text = (
    resources.files("goldlabel").joinpath("gold_rule.md").read_text(encoding="utf-8")
)
_short, _, _full = _text.partition("## Full")
GOLD_RULE_SHORT = _short.removeprefix("## Short").strip()
GOLD_RULE_FULL = _full.strip()


class GoldError(ValueError):
    """An error about gold. `str()` is the message, two newlines and the Short gold rule;
    `.text` is the message alone (for the labelling page's HTTP errors, which omit the rule).

    The `TypeError` and `RuntimeError` cases raised from `gold.py`/`_label.py` use the two
    subclasses below, so `except TypeError` / `except RuntimeError` keep working.
    """

    def __init__(self, text: str):
        self.text = text
        super().__init__(f"{text}\n\n{GOLD_RULE_SHORT}")


class GoldTypeError(GoldError, TypeError):
    pass


class GoldRuntimeError(GoldError, RuntimeError):
    pass
