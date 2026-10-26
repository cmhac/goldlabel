import http.client
import json
import re
import threading
import zipfile
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

import pytest

import hunches
from hunches import _label
from hunches.gold import Gold
from hunches.taxonomy import Label, Taxonomy

ROOT = Path(__file__).resolve().parent.parent
WEB = ("index.html", "app.js", "app.css")


def taxonomy(mode="multi"):
    return Taxonomy(
        mode=mode, labels=[Label(name="a", description="the a one"), Label(name="b")]
    )


def write_gold(path, ids=("1", "2")):
    rows = [{"id": i, "text": f"text {i}", "labels": None, "split": "dev"} for i in ids]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


@pytest.fixture
def gold_path(tmp_path):
    return write_gold(tmp_path / "gold.jsonl")


def get(url, path, *, token=True, host=None):
    u = urlparse(url)
    token_value = u.query.removeprefix("token=")
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    q = f"?token={token_value}" if token else ""
    conn.request("GET", path + q, headers={"Host": host} if host else {})
    r = conn.getresponse()
    return r.status, r.read().decode(), r


def post(url, path, body=None):
    u = urlparse(url)
    conn = http.client.HTTPConnection(u.hostname, u.port, timeout=5)
    conn.request(
        "POST",
        path,
        json.dumps(body or {}),
        {"X-Hunches-Token": u.query.removeprefix("token=")},
    )
    r = conn.getresponse()
    return r.status, json.loads(r.read())


@pytest.fixture
def handle(gold_path):
    h = _label.serve(Gold(gold_path), taxonomy())
    yield h
    h.stop()


def packaged(name):
    return resources.files("hunches").joinpath("web", name).read_text(encoding="utf-8")


# --- the page -------------------------------------------------------------------------------


def test_index_has_color_scheme_meta_and_links_assets_with_the_token(handle):
    status, body, r = get(handle.url, "/")
    assert status == 200
    assert r.getheader("Content-Type").startswith("text/html")
    assert '<meta name="color-scheme" content="light dark">' in body
    token = handle.token
    assert f'href="app.css?token={token}"' in body
    assert f'src="app.js?token={token}"' in body
    assert "__TOKEN__" not in body


def test_assets_are_served_with_their_types_and_need_the_token(handle):
    for name, kind in (("app.css", "text/css"), ("app.js", "text/javascript")):
        status, body, r = get(handle.url, "/" + name)
        assert status == 200 and body.strip()
        assert r.getheader("Content-Type").startswith(kind)
        assert get(handle.url, "/" + name, token=False)[0] == 403
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
    assert posted == {"/api/state", "/api/label", "/api/back", "/api/skip", "/api/done"}
    assert "predict" not in (js + packaged("index.html")).lower()
    assert "X-Hunches-Token" in js


def test_page_is_mobile_first_and_has_the_controls():
    html = packaged("index.html")
    assert 'name="viewport" content="width=device-width, initial-scale=1"' in html
    for needle in ("Skip", "Done", "Back"):
        assert needle in html or needle in packaged("app.js")


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
        assert f"hunches/web/{name}" in names


# --- hn.label -------------------------------------------------------------------------------


def test_label_is_exported():
    assert hunches.label is _label.label
    assert "label" in hunches.__all__


def test_label_without_blocking_returns_a_working_handle(
    gold_path, monkeypatch, capsys
):
    opened = []
    monkeypatch.setattr("webbrowser.open", opened.append)
    h = hunches.label(Gold(gold_path), taxonomy(), open_browser=False, block=False)
    try:
        assert isinstance(h, _label.Handle)
        assert get(h.url, "/api/state")[0] == 200
        out = capsys.readouterr().out
        assert h.url in out and "Done" in out
        assert opened == []
    finally:
        h.stop()


def test_label_blocks_until_done_and_returns_the_labelled_rows(
    gold_path, monkeypatch, capsys
):
    urls = []
    monkeypatch.setattr("webbrowser.open", urls.append)
    result = []
    t = threading.Thread(
        target=lambda: result.append(hunches.label(Gold(gold_path), taxonomy())),
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
    post(url, "/api/done")
    t.join(5)
    assert not t.is_alive()
    (got,) = result
    assert [(r.id, r.labels) for r in got.rows] == [("1", ["a"]), ("2", ["a", "b"])]
    assert str(url) in capsys.readouterr().out
    assert not gold_path.with_name("gold.jsonl.lock").exists()


def test_label_reports_orphans_and_continues(tmp_path, monkeypatch, capsys):
    p = tmp_path / "g.jsonl"
    p.write_text(
        json.dumps({"id": "1", "text": "t", "labels": ["gone"], "split": "dev"})
        + "\n"
        + json.dumps({"id": "2", "text": "t", "labels": None, "split": "dev"})
        + "\n"
    )
    monkeypatch.setattr("webbrowser.open", lambda url: True)
    h = hunches.label(Gold(p), taxonomy(), open_browser=False, block=False)
    try:
        assert "1 labelled row" in capsys.readouterr().out
        assert get(h.url, "/api/state")[0] == 200
    finally:
        h.stop()


def test_label_stops_the_server_if_interrupted(gold_path, monkeypatch):
    monkeypatch.setattr(
        _label.Handle, "wait", lambda self: (_ for _ in ()).throw(KeyboardInterrupt)
    )
    with pytest.raises(KeyboardInterrupt):
        hunches.label(Gold(gold_path), taxonomy(), open_browser=False)
    assert not gold_path.with_name("gold.jsonl.lock").exists()
