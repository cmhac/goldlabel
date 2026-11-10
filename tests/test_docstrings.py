"""Every public callable of goldlabel explains itself to a person with no agent.

The docstring standard (ruff enforces most of it through `D`, `DOC201` and `DOC501`): one summary
line, a blank line, then `Args:` (meaning, allowed values, units), `Returns:`, `Raises:` (only what
is raised on purpose), and a plain sentence for each effect: files written and where, live model
calls and cost, a page opened, "returns a new X; the original is unchanged". Plain words, no spec
numbers, no agent jargon. Ruff cannot ask for an `Args:` section that is missing altogether (it
only checks one that exists), so this test does.
"""

import inspect

import goldlabel as gl


def _public():
    """Yield `(name, callable, docstring)` for what `goldlabel.__all__` exports and its public members."""
    for name in gl.__all__:
        obj = getattr(gl, name)
        if inspect.isclass(obj):
            yield name, obj, obj.__doc__
            for member, value in vars(obj).items():
                if member.startswith("_"):
                    continue
                # a classmethod or staticmethod is stored as a wrapper that is not callable
                func = (
                    value.fget
                    if isinstance(value, property)
                    else getattr(value, "__func__", value)
                )
                if callable(func):
                    yield f"{name}.{member}", func, func.__doc__
        elif callable(obj):
            yield name, obj, obj.__doc__


def test_every_public_callable_has_a_docstring():
    missing = [name for name, _, doc in _public() if not doc]
    assert not missing, f"no docstring: {missing}"


def test_every_public_callable_with_arguments_has_an_args_section():
    missing = []
    for name, func, doc in _public():
        if inspect.isclass(func):
            continue  # a class documents its constructor arguments in its own docstring
        params = [
            p for p in inspect.signature(func).parameters if p not in ("self", "cls")
        ]
        if params and "Args:" not in (doc or ""):
            missing.append(name)
    assert not missing, f"no Args: section: {missing}"
