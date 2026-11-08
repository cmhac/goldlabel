import http.client
import json
import re
import threading
import zipfile
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

import pytest

import goldlabel
from goldlabel import _label
from goldlabel.gold import Gold, Sample
from goldlabel.settings import settings
from goldlabel.taxonomy import Label, Taxonomy

ROOT = Path(__file__).resolve().parent.parent
WEB = ("index.html", "app.js", "app.css")


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "root", tmp_path)


def taxonomy(mode="multi"):
    return Taxonomy(
        mode=mode, labels=[Label(name="a", description="the a one"), Label(name="b")]
    )


def write_gold(path, ids=("1", "2")):
    rows = [
        {"id": i, "text": f"text {i}", "labels": None, "sample": "dev"} for i in ids
    ]
    path.write_text(json.dumps({"taxonomy": None, "rows": rows}))
    return path


@pytest.fixture
def gold_path(tmp_path):
    return write_gold(tmp_path / "gold.json")


def get(url, path, *, host=None):
    u = urlparse(url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    conn.request("GET", path, headers={"Host": host} if host else {})
    r = conn.getresponse()
    return r.status, r.read().decode(), r


def post(url, path, body=None):
    u = urlparse(url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    body = {"pass": u.fragment.removeprefix("/pass/"), **(body or {})}
    conn.request("POST", path, json.dumps(body), {"X-Goldlabel": "1"})
    r = conn.getresponse()
    return r.status, json.loads(r.read())


@pytest.fixture
def handle(gold_path):
    h = _label.serve(Gold()["dev"], taxonomy())
    yield h
    h.stop()


def packaged(name):
    return (
        resources.files("goldlabel").joinpath("web", name).read_text(encoding="utf-8")
    )


# --- the page -------------------------------------------------------------------------------


def test_index_has_color_scheme_meta_and_links_assets_without_a_token(handle):
    status, body, r = get(handle.url, "/")
    assert status == 200
    assert r.getheader("Content-Type").startswith("text/html")
    assert '<meta name="color-scheme" content="light dark">' in body
    assert 'href="app.css"' in body and 'src="app.js"' in body
    assert "token" not in body.lower()


def test_assets_are_served_with_their_types_to_the_right_host_only(handle):
    for name, kind in (("app.css", "text/css"), ("app.js", "text/javascript")):
        status, body, r = get(handle.url, "/" + name)
        assert status == 200 and body.strip()
        assert r.getheader("Content-Type").startswith(kind)
        assert get(handle.url, "/" + name, host="evil.example:80")[0] == 403
    assert get(handle.url, "/index.html")[0] == 404  # only the three known paths


def test_nothing_else_is_served_from_the_package(handle):
    for path in ("/input.css", "/README.md", "/../gold.py", "/%2e%2e/gold.py"):
        assert get(handle.url, path)[0] == 404


def test_css_follows_the_system_scheme_by_media_query():
    css = packaged("app.css")
    assert "prefers-color-scheme:dark" in css.replace(" ", "")
    assert "dark" not in re.findall(r"\.dark\b[^{]*\{", css)  # no class-based variant


@pytest.mark.parametrize("name", WEB)
def test_no_external_urls_storage_or_scheme_scripts(name):
    text = packaged(name)
    assert not re.findall(r"https?://", text)
    assert "//cdn" not in text and "@import url" not in text
    for forbidden in (
        "localStorage",
        "sessionStorage",
        "matchMedia",
        "document.cookie",
    ):
        assert forbidden not in text
    assert not re.search(r"classList\.(add|toggle)\([^)]*dark", text)
    assert "data-theme" not in text


def test_js_posts_only_to_the_existing_routes_and_shows_no_prediction():
    js = packaged("app.js")
    posted = set(re.findall(r"/api/[a-z]+", js))
    assert posted == {
        "/api/pass",
        "/api/label",
        "/api/datasets",
        "/api/rows",
        "/api/row",
        "/api/evals",
    }
    # a prediction appears only in the evaluation review, beside the gold label, never while labelling
    review = js[
        js.index("function disagreementTable") : js.index("async function evalsSection")
    ]
    outside = js.replace(review, "")
    assert "predict" in review.lower()
    assert "predict" not in (outside + packaged("index.html")).lower()
    assert '"X-Goldlabel": "1"' in js and "token" not in js.lower()


def test_page_is_mobile_first_and_has_the_controls():
    html = packaged("index.html")
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    for needle in ("Skip", "Done", "Back"):
        assert needle in html or needle in packaged("app.js")


def test_page_has_the_split_layout_status_line_and_note_field():
    js, css = packaged("app.js"), packaged("app.css")
    assert "lg:grid-cols-" in js and "lg:sticky" in js  # text left, controls right
    assert "lg\\:grid-cols-" in css and "lg\\:sticky" in css  # and the CSS was rebuilt
    # the live region exists before its text changes, so screen readers announce it
    assert 'id="status" role="status"' in packaged("index.html")
    assert 'role: "alert"' in js and "role: " + '"status"' not in js
    assert '"textarea"' in js and 'for: "note"' in js  # a labelled note field
    assert "aria-pressed" in js and '"fieldset"' in js
    assert re.search(
        r'"/api/label",\s*\{[^}]*\bnote\b', js
    )  # the note travels with the label


def test_page_key_map_and_guards():
    js = packaged("app.js")
    assert "e.repeat" in js  # a held-down key must not label the next rows
    for key in ('"Escape"', '"s"', '"n"', '"ArrowLeft"', '"Enter"'):
        assert key in js
    assert "e.ctrlKey || e.metaKey" in js  # Ctrl/Cmd+Enter saves from the note
    assert "typing()" in js  # plain keys are paused while the note has focus


def test_web_files_are_in_the_wheel(tmp_path):
    import shutil
    import subprocess

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
    names = set(zipfile.ZipFile(wheel).namelist())
    for name in WEB:
        assert f"goldlabel/web/{name}" in names


# --- gl.label -------------------------------------------------------------------------------


def test_label_is_exported():
    assert goldlabel.label is _label.label
    assert "label" in goldlabel.__all__


def test_label_opens_the_page_and_returns_when_done(
    gold_path, press_done_on_open, capsys
):
    result = goldlabel.label(Gold()["dev"], taxonomy())
    (url,) = press_done_on_open
    assert url in capsys.readouterr().out
    assert isinstance(result, Sample) and result.names == ("dev",)
    assert [r.labels for r in result.rows] == [
        None,
        None,
    ]  # nothing labelled before Done


def test_label_blocks_until_done_and_returns_the_labelled_rows(
    gold_path, monkeypatch, capsys
):
    urls = []
    monkeypatch.setattr("webbrowser.open", urls.append)
    result = []
    t = threading.Thread(
        target=lambda: result.append(goldlabel.label(Gold()["dev"], taxonomy())),
        daemon=True,
    )
    t.start()
    for _ in range(200):
        if urls:
            break
        threading.Event().wait(0.02)
    assert len(urls) == 1
    url = urls[0]
    assert get(url, "/")[0] == 200
    assert post(url, "/api/label", {"id": "1", "labels": ["a"]})[0] == 200
    status, state = post(url, "/api/label", {"id": "2", "labels": ["a", "b"]})
    assert status == 200 and state["finished"] is True
    assert t.is_alive()  # still waiting for Done
    post(url, "/api/pass/" + urlparse(url).fragment.removeprefix("/pass/") + "/done")
    t.join(5)
    assert not t.is_alive()
    (got,) = result
    assert [(r.id, r.labels) for r in got.rows] == [("1", ["a"]), ("2", ["a", "b"])]
    assert str(url) in capsys.readouterr().out
    assert not gold_path.with_name("labelling.lock").exists()


def test_label_reports_orphans_and_continues(tmp_path, press_done_on_open, capsys):
    p = tmp_path / "gold.json"
    rows = [
        {"id": "1", "text": "t", "labels": ["gone"], "sample": "dev"},
        {"id": "2", "text": "t", "labels": None, "sample": "dev"},
    ]
    p.write_text(json.dumps({"taxonomy": None, "rows": rows}))
    goldlabel.label(Gold()["dev"], taxonomy())
    assert "1 labelled row" in capsys.readouterr().out
    assert len(press_done_on_open) == 1  # the page was still served


def test_label_stops_the_server_if_interrupted(gold_path, monkeypatch):
    monkeypatch.setattr(
        _label.Server, "wait", lambda self: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    with pytest.raises(KeyboardInterrupt):
        goldlabel.label(Gold()["dev"], taxonomy(), open_browser=False)
    assert not gold_path.with_name("labelling.lock").exists()


# --- gl.label opens the page only when something is pending (012) ------------------------------


def write_rows(path, rows):
    path.write_text(json.dumps({"taxonomy": None, "rows": rows}))
    return path


def row(id_, labels, split="dev"):
    return {"id": id_, "text": f"text {id_}", "labels": labels, "sample": split}


@pytest.fixture
def no_page(monkeypatch):
    """Fail the test if anything tries to start a server or open a browser."""

    def refuse(*a, **k):
        raise AssertionError("the labelling page must not open")

    monkeypatch.setattr(_label, "serve", refuse)
    monkeypatch.setattr("webbrowser.open", refuse)


def test_label_skips_the_page_when_every_row_is_labelled(tmp_path, no_page, capsys):
    p = write_rows(tmp_path / "gold.json", [row("1", ["a"]), row("2", ["b"])])
    result = goldlabel.label(Gold()["dev"], taxonomy())
    out = capsys.readouterr().out
    assert [(r.id, r.labels) for r in result.rows] == [("1", ["a"]), ("2", ["b"])]
    assert out.splitlines() == [
        (
            "All 2 rows in dev are labelled; nothing to label. "
            "Pass force_open_ui=True to review or relabel."
        )
    ]
    assert not p.with_name("labelling.lock").exists()


def test_label_skips_a_split_that_is_fully_labelled(tmp_path, no_page, capsys):
    write_rows(tmp_path / "gold.json", [row("1", ["a"]), row("t1", None, split="test")])
    result = goldlabel.label(Gold()["dev"], taxonomy())
    assert [r.id for r in result.rows] == ["1"]
    assert "All 1 rows in dev are labelled" in capsys.readouterr().out


def test_label_serves_a_sample_with_a_pending_row(tmp_path, press_done_on_open):
    write_rows(tmp_path / "gold.json", [row("1", ["a"]), row("t1", None, split="test")])
    result = goldlabel.label(Gold()["test"], taxonomy())
    assert len(press_done_on_open) == 1
    assert [r.id for r in result.rows] == ["t1"]


def test_label_says_so_when_the_sample_has_no_rows(tmp_path, no_page, capsys):
    write_rows(tmp_path / "gold.json", [row("1", ["a"])])
    result = goldlabel.label(Sample(Gold(), ("test",)), taxonomy())
    assert result.rows == []
    assert capsys.readouterr().out.splitlines() == [
        "No rows to label in test: draw some first (gold.draw_sample)."
    ]


def test_label_with_no_gold_file_says_so(tmp_path, no_page, capsys):
    assert goldlabel.label(Sample(Gold(), ("dev",)), taxonomy()).rows == []
    assert "No rows to label" in capsys.readouterr().out


def test_force_open_ui_serves_even_when_everything_is_labelled(
    tmp_path, press_done_on_open
):
    write_rows(tmp_path / "gold.json", [row("1", ["a"])])
    result = goldlabel.label(Gold()["dev"], taxonomy(), force_open_ui=True)
    assert len(press_done_on_open) == 1
    assert [r.id for r in result.rows] == ["1"]


def test_skip_still_reports_orphans(tmp_path, no_page, capsys):
    write_rows(tmp_path / "gold.json", [row("1", ["gone"])])
    goldlabel.label(Gold()["dev"], taxonomy())
    assert "1 labelled row" in capsys.readouterr().out


def test_label_has_no_block_parameter(gold_path):
    with pytest.raises(TypeError):
        goldlabel.label(Gold()["dev"], taxonomy(), block=False)  # ty: ignore[unknown-argument]


def test_label_takes_only_a_sample(tmp_path, no_page):
    write_rows(tmp_path / "gold.json", [row("1", ["a"])])
    for bad in (Gold(), Gold().all):
        with pytest.raises(goldlabel.GoldError, match=r'gold\.draw_sample\("dev"\)'):
            goldlabel.label(bad, taxonomy())  # ty: ignore[invalid-argument-type]
    with pytest.raises(TypeError):
        goldlabel.label(Gold()["dev"], taxonomy(), split="dev")  # ty: ignore[unknown-argument]


def test_the_page_names_the_sample():
    js = packaged("app.js")
    assert '" in " + state.sample' in js


# --- the browse views (015) -----------------------------------------------------------------


def test_the_page_routes_the_hash_and_remembers_the_scroll_of_each_route():
    js = packaged("app.js")
    assert "hashchange" in js and "location.hash" in js
    for route in (
        '"pass"',
        '"d"',
        '"s"',
    ):  # #/pass/<id>, #/d/<ds>[/s/<sample> | /r/<id>]
        assert route in js
    assert "new Map()" in js and "window.scrollY" in js and "window.scrollTo" in js


def test_the_page_lists_datasets_by_title_and_shows_a_bad_file_as_an_error():
    js = packaged("app.js")
    assert '"/api/datasets"' in js and "d.title" in js and "d.error" in js
    assert "'/api/rows?dataset='" in js.replace('"', "'") or "/api/rows?dataset=" in js
    # the dataset key in a route is the file stem the API returns, not the title
    assert "d.name" in js


def test_a_pass_that_is_gone_says_so_and_links_home():
    js = packaged("app.js")
    assert "this pass has ended" in js.lower() and 'href: "#/"' in js


def test_the_page_never_writes_html_from_data():
    for name in WEB:
        text = packaged(name)
        assert "innerHTML" not in text and "insertAdjacentHTML" not in text
        assert "document.write" not in text and "outerHTML" not in text


def test_the_css_was_rebuilt_for_the_browse_views():
    css = packaged("app.css")
    for cls in ("underline-offset-2", "text-blue-700", "border-collapse"):
        assert cls in css


# --- the row editor, jump to id, label pending (015) ----------------------------------------


def test_the_page_has_the_row_editor_route_and_the_row_api():
    js = packaged("app.js")
    assert '"r"' in js and "/api/row?dataset=" in js and "stored_taxonomy" in js
    assert "dataset: editing.dataset" in js.replace("  ", " ") or "dataset:" in js
    assert "history.back()" in js  # Back in the editor is the browser's Back


def test_jump_to_id_and_label_pending_are_on_the_dataset_and_sample_pages():
    js = packaged("app.js")
    assert "Jump to id" in js and 'for: "jump"' in js
    assert 'role: "alert"' in js  # "no row <id> in <dataset>" is announced
    assert "Label pending" in js and '"/api/pass"' in js
    assert "nothing pending" in js


def test_the_editor_names_labels_outside_the_taxonomy_and_a_missing_taxonomy():
    js = packaged("app.js")
    assert "not in this taxonomy" in js
    assert "No taxonomy is stored" in js


def test_done_returns_to_the_list_when_the_server_keeps_running():
    js = packaged("app.js")
    assert "closing" in js and '"#/"' in js


# --- the evaluation views (015) ---------------------------------------------------------------


def test_the_sample_page_lists_evaluations_with_stale_and_pass_fail_in_words():
    js = packaged("app.js")
    assert "/api/evals?dataset=" in js
    for word in ("STALE", "PASS", "FAIL", "no target"):
        assert word in js
    assert "a row was revised after this ran" in js


def test_the_disagreement_table_names_every_column_and_every_special_case():
    js = packaged("app.js")
    for word in (
        "Gold then",
        "Predicted",
        "Reasoning",
        "Note",
        "revised since",
        "no longer in the file",
    ):
        assert word in js
    assert "disagreements were not recorded by this version" in js
    assert "Not evaluated yet" in js
    assert "rowHref(" in js  # each disagreement opens its row


def test_the_page_has_no_way_to_run_an_evaluation():
    js = packaged("app.js")
    assert "/api/eval" not in js.replace("/api/evals", "")
    said = "Not evaluated yet. Evaluations are run from code (clf.evaluate), never from this page."
    assert said in js
    for word in ("evaluate", "classify", "estimate", "predict("):
        assert word not in js.replace(said, "")
    assert "<details" in js or '"details"' in js


# --- independent scrolling from 1024px (015) --------------------------------------------------

SCROLL = "lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto"


def test_both_cards_scroll_on_their_own_from_1024px_and_are_keyboard_reachable():
    js = packaged("app.js")
    cards = {
        "text": js[js.index("function textCard") : js.index("function options")],
        "controls": js[js.index("function panel") : js.index("function ended")],
    }
    assert f'const SCROLL = "{SCROLL}"' in js
    for name, body in cards.items():
        assert "SCROLL" in body, name
        assert 'tabindex: "0"' in body, (
            name
        )  # a scrolling area must be reachable by keyboard
        assert "FOCUS" in body, name  # and show where the focus is


def test_nothing_floats_or_scrolls_in_the_one_column_layout():
    js = packaged("app.js")
    classes = " ".join(re.findall(r'"([^"]*(?:sticky|max-h|overflow-y)[^"]*)"', js))
    for token in classes.split():
        if any(w in token for w in ("sticky", "max-h", "overflow-y", "top-4")):
            assert token.startswith("lg:"), token  # below lg the page scrolls as one
    assert "lg:hidden" in js and "one column" in js  # the page says so


def test_the_css_has_those_rules_inside_the_1024px_media_query():
    css = packaged("app.css")
    assert "64rem" in css  # Tailwind's lg
    for cls in (
        r"lg\:overflow-y-auto",
        r"lg\:sticky",
        r"lg\:max-h-\[calc\(100vh-2rem\)\]",
    ):
        assert cls in css
    assert "overflow-y:auto" in css and "max-height:calc(100vh - 2rem)" in css
    for m in re.finditer(r"\.lg\\:(?:sticky|overflow-y-auto)", css):
        before = css[: m.start()]
        assert before.rfind("@media") > before.rfind("}}") or "@media" in before[-300:]


def test_a_slow_reply_cannot_overwrite_a_newer_page_and_a_bad_log_keeps_the_rows():
    js = packaged("app.js")
    assert "++nav" in js and "mine !== nav" in js  # a reply for an old route is dropped
    section = js[
        js.index("async function evalsSection") : js.index("async function rowsView")
    ]
    assert (
        "catch" in section
    )  # an evaluation error is shown inside its box, not instead of the rows
