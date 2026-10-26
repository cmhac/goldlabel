import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

import hunches
from hunches import _label
from hunches.gold import Gold
from hunches.taxonomy import Label, Taxonomy

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "specs" / "006-library" / "spec.md"
RULE = ROOT / "src" / "hunches" / "gold_rule.md"
SHORT = getattr(hunches, "GOLD_RULE_SHORT", "<missing>")
HTML_RULE_MARKER = "Hard rule"


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)


def taxonomy():
    return Taxonomy(mode="multi", labels=[Label(name="a"), Label(name="b")])


def gold_file(tmp_path, ids=("1", "2")):
    p = tmp_path / "g.jsonl"
    p.write_text(
        "".join(
            json.dumps({"id": i, "text": f"t{i}", "labels": None, "split": "dev"})
            + "\n"
            for i in ids
        )
    )
    return p


def cands(n):
    from hunches.candidates import Candidates

    return Candidates(
        [
            {"id": f"c{i}", "text": f"cand {i}", "score": 0.5, "seeds": ["s"]}
            for i in range(n)
        ]
    )


def spec_blockquotes():
    """The Short and Full blockquotes of the spec, `>` stripped, parsed from the spec itself."""
    lines = SPEC.read_text().splitlines()

    def quote_after(marker):
        start = next(i for i, ln in enumerate(lines) if ln.startswith(marker))
        i = start + 1
        while not lines[i].startswith(">"):
            i += 1
        out = []
        while i < len(lines) and lines[i].startswith(">"):
            out.append(lines[i][1:].lstrip())
            i += 1
        return "\n".join(out)

    return quote_after("**Short**"), quote_after("**Full:**")


def rule_file_sections():
    text = RULE.read_text()
    head, _, rest = text.partition("## Short")
    short, _, full = rest.partition("## Full")
    assert head.strip() == ""
    return short.strip(), full.strip()


# --- the text -------------------------------------------------------------------------------


def test_texts_are_exported_and_shaped():
    assert "GOLD_RULE_SHORT" in hunches.__all__ and "GOLD_RULE_FULL" in hunches.__all__
    assert SHORT and len(SHORT) < 400
    full = hunches.GOLD_RULE_FULL
    for phrase in ("not negotiable", "refuse", "import"):
        assert phrase in full


def test_file_has_exactly_two_sections_and_matches_the_spec_blockquotes():
    assert RULE.read_text().count("\n## ") + RULE.read_text().startswith("## ") == 2
    spec_short, spec_full = spec_blockquotes()
    file_short, file_full = rule_file_sections()
    assert spec_short.startswith(
        "**Hard rule: never write, edit"
    )  # parsed the right one
    assert spec_full.startswith("**Hard rule of the hunches library.")
    assert file_short == spec_short
    assert file_full == spec_full
    assert hunches.GOLD_RULE_SHORT == spec_short
    assert hunches.GOLD_RULE_FULL == spec_full


def test_rule_file_is_in_the_wheel(tmp_path):
    if shutil.which("uv") is None:
        pytest.skip("uv is not installed")
    done = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path), str(ROOT)],
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        pytest.skip(f"uv build needs the network for its build backend: {done.stderr}")
    wheel = next(tmp_path.glob("*.whl"))
    assert "hunches/gold_rule.md" in zipfile.ZipFile(wheel).namelist()


# --- where it is printed ----------------------------------------------------------------------


def test_repr_of_gold_lists_path_counts_sources_and_ends_with_the_rule(tmp_path):
    p = tmp_path / "g.jsonl"
    rows = [
        {
            "id": "1",
            "text": "t",
            "labels": ["a"],
            "split": "dev",
            "labelled_by": "hunches-ui",
        },
        {
            "id": "2",
            "text": "t",
            "labels": ["b"],
            "split": "test",
            "labelled_by": "imported",
        },
        {"id": "3", "text": "t", "labels": None, "split": "dev"},
    ]
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    out = repr(Gold(p))
    assert str(p) in out
    assert "dev 1" in out and "test 1" in out and "pending 1" in out
    assert "hunches-ui 1, imported 1, unstamped 0" in out
    assert out.endswith(SHORT)
    assert out.splitlines()[-1] == SHORT


def test_repr_of_a_goldset_ends_with_the_rule(tmp_path):
    g = Gold(gold_file(tmp_path))
    assert repr(g.dev).splitlines()[-1] == SHORT
    assert repr(g.pending).splitlines()[0].startswith("GoldSet pending: 2 rows")


def test_draw_return_repr_has_the_rule(tmp_path):
    g = Gold(tmp_path / "new.jsonl")
    assert repr(g.draw(cands(3), n=2)).splitlines()[-1] == SHORT


def test_html_reprs_do_not_carry_the_rule(tmp_path):
    g = Gold(gold_file(tmp_path))
    assert HTML_RULE_MARKER not in g._repr_html_()
    assert HTML_RULE_MARKER not in g.pending._repr_html_()


def test_label_prints_the_rule(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("webbrowser.open", lambda url: None)
    h = hunches.label(
        Gold(gold_file(tmp_path)), taxonomy(), open_browser=False, block=False
    )
    try:
        assert SHORT in capsys.readouterr().out
    finally:
        h.stop()


# --- errors ---------------------------------------------------------------------------------


def test_import_rows_duplicate_id_error_carries_the_rule(tmp_path):
    g = Gold(gold_file(tmp_path))
    with pytest.raises(ValueError) as e:
        g.import_rows([{"id": "1", "text": "t", "labels": ["a"]}], "dev")
    assert str(e.value) == "id '1' is already in " + str(g.path) + "\n\n" + SHORT
    assert isinstance(e.value, hunches.GoldError)


def test_error_types_stay_compatible(tmp_path):
    g = Gold(gold_file(tmp_path))
    with pytest.raises(TypeError) as t:
        g.remove("1")
    assert isinstance(t.value, hunches.GoldError) and SHORT in str(t.value)
    with pytest.raises(ValueError) as v:
        g.draw(cands(1), split="x")
    assert str(v.value).endswith("\n\n" + SHORT)
    bad = tmp_path / "bad.jsonl"
    bad.write_text("nope\n")
    with pytest.raises(ValueError, match="bad.jsonl:1: not a gold row") as r:
        len(Gold(bad).all)
    assert SHORT in str(r.value)


def test_label_lock_and_split_errors_carry_the_rule(tmp_path):
    g = Gold(gold_file(tmp_path))
    with pytest.raises(ValueError) as e:
        _label.serve(g, taxonomy(), split="x")
    assert SHORT in str(e.value)
    h = _label.serve(g, taxonomy())
    try:
        with pytest.raises(RuntimeError, match="already being labelled") as e:
            _label.serve(g, taxonomy())
        assert isinstance(e.value, hunches.GoldError) and SHORT in str(e.value)
    finally:
        h.stop()


def test_http_error_bodies_do_not_carry_the_rule(tmp_path):
    import http.client
    from urllib.parse import urlparse

    h = _label.serve(Gold(gold_file(tmp_path)), taxonomy())
    try:
        u = urlparse(h.url)
        c = http.client.HTTPConnection("127.0.0.1", u.port)
        c.request(
            "POST",
            "/api/label",
            json.dumps({"id": "1", "labels": ["zzz"]}),
            {"X-Hunches-Token": u.query.split("=")[1]},
        )
        r = c.getresponse()
        body = r.read().decode()
        assert r.status == 400 and "zzz" in body
        assert "Hard rule" not in body
    finally:
        h.stop()
