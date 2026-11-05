import http.client
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import pytest

from goldlabel import _label
from goldlabel.gold import Gold
from goldlabel.settings import settings
from goldlabel.taxonomy import Label, Taxonomy


def rows(*specs):
    """specs: (id, labels-or-None, split)."""
    return [
        {"id": i, "text": f"text {i}", "labels": labels, "sample": split}
        for i, labels, split in specs
    ]


def write_gold(path, rows_):
    path.write_text(json.dumps({"taxonomy": None, "rows": rows_}))


@pytest.fixture(autouse=True)
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "root", tmp_path)


def taxonomy(mode="multi"):
    return Taxonomy(
        mode=mode,
        labels=[Label(name="a", description="the a one"), Label(name="b")],
    )


@pytest.fixture
def gold_path(tmp_path):
    p = tmp_path / "gold.json"
    write_gold(
        p,
        rows(
            ("1", None, "dev"),
            ("2", None, "dev"),
            ("3", None, "dev"),
            ("t1", None, "test"),
        ),
    )
    return p


@pytest.fixture
def start(gold_path):
    handles = []

    def go(mode="multi", sample="dev", **kw):
        h = _label.serve(Gold()[sample], taxonomy(mode), **kw)
        handles.append(h)
        return h

    yield go
    for h in handles:
        h.stop()


class Client:
    def __init__(self, handle):
        u = urlparse(handle.url)
        self.host, self.port = u.hostname, u.port
        self.token = u.query.removeprefix("token=")

    def call(self, method, path, body=None, *, token="ok", host=None):
        if token == "ok":
            token = self.token
        conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        q = f"?token={token}" if token is not None else ""
        headers = {"Host": host} if host else {}
        data = None
        if body is not None:
            data = json.dumps(body)
            headers["Content-Type"] = "application/json"
        conn.request(method, path + q, data, headers)
        r = conn.getresponse()
        raw = r.read().decode()
        conn.close()
        try:
            return r.status, json.loads(raw), r
        except ValueError:
            return r.status, raw, r

    def state(self):
        status, body, _ = self.call("GET", "/api/state")
        assert status == 200
        return body

    def label(self, id_, labels):
        return self.call("POST", "/api/label", {"id": id_, "labels": labels})[:2]


def on_disk(path):
    return json.loads(path.read_text())["rows"]


# --- binding and access ------------------------------------------------------------------------


def test_binds_loopback_only(start):
    h = start()
    assert h.server.server_address[0] == "127.0.0.1"
    assert h.url.startswith(f"http://127.0.0.1:{h.port}/")
    assert h.port != 0


def test_403_without_or_with_wrong_token(start):
    c = Client(start())
    assert c.call("GET", "/api/state", token=None)[0] == 403
    assert c.call("GET", "/api/state", token="wrong")[0] == 403
    assert (
        c.call("POST", "/api/label", {"id": "1", "labels": ["a"]}, token="x")[0] == 403
    )
    assert c.call("GET", "/", token=None)[0] == 403
    assert c.call("GET", "/api/state")[0] == 200


def test_token_in_header_is_accepted(start):
    h = start()
    c = Client(h)
    conn = http.client.HTTPConnection(c.host, c.port, timeout=5)
    conn.request("GET", "/api/state", headers={"X-Goldlabel-Token": c.token})
    assert conn.getresponse().status == 200


def test_403_for_foreign_host(start):
    c = Client(start())
    assert c.call("GET", "/api/state", host="evil.example:80")[0] == 403
    assert c.call("GET", "/api/state", host=f"evil.example:{c.port}")[0] == 403
    assert c.call("GET", "/api/state", host="127.0.0.1")[0] == 403  # no port
    assert c.call("GET", "/api/state", host=f"localhost:{c.port}")[0] == 200
    assert c.call("GET", "/api/state", host=f"127.0.0.1:{c.port}")[0] == 200


def test_no_cors_or_cookie_headers(start):
    c = Client(start())
    _, _, r = c.call("GET", "/api/state")
    names = {k.lower() for k, _ in r.getheaders()}
    assert not {n for n in names if n.startswith("access-control") or n == "set-cookie"}


def test_index_page_is_html(start):
    status, body, _ = Client(start()).call("GET", "/")
    assert status == 200 and "<title>" in body


def test_unknown_path_is_404(start):
    assert Client(start()).call("GET", "/nope")[0] == 404


# --- state -------------------------------------------------------------------------------------


def test_state_shows_first_pending_row_and_counts(start):
    s = Client(start()).state()
    assert s["item"] == {"id": "1", "text": "text 1", "labels": None, "note": None}
    assert s["position"] == 1
    assert (s["done"], s["total"]) == (0, 3)  # the pass: the dev sample's pending rows
    assert s["sample"] == "dev"
    assert s["mode"] == "multi"
    assert s["labels"] == [
        {"name": "a", "description": "the a one"},
        {"name": "b", "description": ""},
        {
            "name": "off_topic",
            "description": "the item matches none of the labels above",
        },
    ]
    assert s["counts"] == {"a": 0, "b": 0, "off_topic": 0}
    assert s["finished"] is False


def test_a_sample_restricts_rows(start):
    s = Client(start(sample="test")).state()
    assert s["item"]["id"] == "t1" and s["sample"] == "test"
    assert (s["done"], s["total"]) == (0, 1)


def test_only_a_sample_can_be_served(gold_path):
    with pytest.raises(_label.GoldError, match=r'gold\.draw_sample\("dev"\)'):
        _label.serve(Gold(), taxonomy())  # ty: ignore[invalid-argument-type]
    with pytest.raises(_label.GoldError):
        _label.serve(Gold().all, taxonomy())  # ty: ignore[invalid-argument-type]


def test_already_labelled_rows_are_not_in_the_pass(tmp_path):
    p = tmp_path / "gold.json"
    write_gold(
        p,
        rows(
            ("1", ["a"], "dev"),
            ("2", ["a", "b"], "dev"),
            ("3", None, "dev"),
            ("4", [], "dev"),
        ),
    )
    h = _label.serve(Gold()["dev"], taxonomy())
    try:
        s = Client(h).state()
        assert s["item"]["id"] == "3"
        assert s["position"] == 1
        assert (s["done"], s["total"]) == (0, 2)  # rows 3 and 4 ([] is pending)
        assert s["counts"] == {"a": 0, "b": 0, "off_topic": 0}
    finally:
        h.stop()


# --- labelling ---------------------------------------------------------------------------------


def test_single_mode_rejects_two_labels_or_none(start, gold_path):
    c = Client(start("single"))
    before = gold_path.read_bytes()
    status, body = c.label("1", ["a", "b"])
    assert status == 400 and "exactly one" in body["error"]
    status, body = c.label("1", [])
    assert status == 400 and "at least one" in body["error"]
    assert gold_path.read_bytes() == before


def test_multi_accepts_several(start, gold_path):
    c = Client(start("multi"))
    status, _ = c.label("1", ["a", "b"])
    assert status == 200
    assert on_disk(gold_path)[0]["labels"] == ["a", "b"]


def test_off_topic_is_exclusive_and_unknown_label_refused(start, gold_path):
    c = Client(start("multi"))
    before = gold_path.read_bytes()
    status, body = c.label("1", ["off_topic", "a"])
    assert status == 400 and "off_topic" in body["error"]
    status, body = c.label("1", ["zzz"])
    assert status == 400 and "unknown labels" in body["error"]
    assert gold_path.read_bytes() == before
    assert c.label("1", ["off_topic"])[0] == 200


def test_bad_requests(start):
    c = Client(start())
    assert c.label("nope", ["a"])[0] == 404
    assert c.call("POST", "/api/label", {"labels": ["a"]})[0] == 400
    assert c.call("POST", "/api/label", {"id": "1", "labels": "a"})[0] == 400
    assert c.call("POST", "/api/label", [1])[0] == 400
    conn = http.client.HTTPConnection(c.host, c.port, timeout=5)
    conn.request("POST", f"/api/label?token={c.token}", "{not json")
    assert conn.getresponse().status == 400


def test_label_writes_and_stamps_and_leaves_other_rows_identical(start, gold_path):
    c = Client(start())
    lines = on_disk(gold_path)
    status, s = c.label("2", ["b"])
    assert status == 200
    new = on_disk(gold_path)
    assert new[0] == lines[0] and new[2:] == lines[2:]  # other rows identical
    row = new[1]
    assert row["labels"] == ["b"]
    assert row["labelled_by"] == "goldlabel-ui"
    datetime.fromisoformat(row["labelled_at"])
    assert (row["id"], row["text"], row["sample"]) == ("2", "text 2", "dev")
    assert s["counts"]["b"] == 1
    assert not list(gold_path.parent.glob("*.tmp"))


def test_label_advances_in_file_order_then_finishes(start):
    c = Client(start())
    assert c.label("1", ["a"])[1]["item"]["id"] == "2"
    s = c.label("2", ["a"])[1]
    assert s["item"]["id"] == "3" and (s["done"], s["total"]) == (2, 3)
    s = c.label("3", ["b"])[1]
    assert s["finished"] is True and s["item"] is None
    assert (s["done"], s["total"]) == (3, 3)
    assert s["counts"] == {"a": 2, "b": 1, "off_topic": 0}


def test_extra_keys_survive_labelling(tmp_path):
    p = tmp_path / "gold.json"
    row = {"id": "1", "text": "t", "labels": None, "sample": "dev", "src": "x"}
    p.write_text(json.dumps({"taxonomy": None, "rows": [row]}))
    h = _label.serve(Gold()["dev"], taxonomy())
    try:
        Client(h).label("1", ["a"])
    finally:
        h.stop()
    assert on_disk(p)[0]["src"] == "x"


def test_resume_after_stop(start, gold_path):
    h = start()
    c = Client(h)
    c.label("1", ["a"])
    h.stop()
    h2 = start()
    s = Client(h2).state()
    assert s["item"]["id"] == "2" and (s["done"], s["total"]) == (0, 2)  # a new pass
    assert on_disk(gold_path)[0]["labels"] == ["a"]


def test_back_then_relabel_changes_stored_label(start, gold_path):
    c = Client(start())
    c.label("1", ["a"])
    c.label("2", ["a"])
    status, s, _ = c.call("POST", "/api/back")
    assert status == 200 and s["item"] == {
        "id": "2",
        "text": "text 2",
        "labels": ["a"],
        "note": None,
    }
    status, s = c.label("2", ["b"])
    assert on_disk(gold_path)[1]["labels"] == ["b"]
    assert s["item"]["id"] == "3"
    assert c.call("POST", "/api/back")[1]["item"]["id"] == "2"
    assert c.call("POST", "/api/back")[1]["item"]["id"] == "1"


def test_back_at_start_stays(start):
    c = Client(start())
    s = c.call("POST", "/api/back")[1]
    assert s["item"]["id"] == "1"


def test_back_from_finished_returns_last_row(start):
    c = Client(start(sample="test"))
    assert c.label("t1", ["a"])[1]["finished"] is True
    s = c.call("POST", "/api/back")[1]
    assert s["item"]["id"] == "t1" and s["finished"] is False


def test_skip_leaves_pending_and_moves_on(start, gold_path):
    c = Client(start())
    before = gold_path.read_bytes()
    s = c.call("POST", "/api/skip")[1]
    assert s["item"]["id"] == "2" and s["done"] == 0
    assert gold_path.read_bytes() == before
    c.label("2", ["a"])
    s = c.label("3", ["a"])[1]
    # the skipped row is offered again at the end
    assert s["item"]["id"] == "1" and s["finished"] is False


def test_skip_with_one_pending_row_stays(start):
    c = Client(start(sample="test"))
    assert c.call("POST", "/api/skip")[1]["item"]["id"] == "t1"


# --- done, locks -------------------------------------------------------------------------------


def test_done_stops_server_and_removes_lock(start, gold_path):
    h = start()
    lock = gold_path.with_name("gold.json.lock")
    assert lock.exists()
    c = Client(h)
    status, _, _ = c.call("POST", "/api/done")
    assert status == 200
    h.wait()
    assert not lock.exists()
    with pytest.raises(OSError):
        http.client.HTTPConnection(c.host, c.port, timeout=2).request("GET", "/")


def test_stop_releases_lock_and_is_idempotent(start, gold_path):
    h = start()
    h.stop()
    h.stop()
    assert not gold_path.with_name("gold.json.lock").exists()


def test_lock_holds_pid_and_start_time(start, gold_path):
    start()
    lock = json.loads(gold_path.with_name("gold.json.lock").read_text())
    assert lock["pid"] == os.getpid()
    datetime.fromisoformat(lock["started"])


def test_second_server_on_same_file_is_refused(start):
    start()
    with pytest.raises(RuntimeError, match="already being labelled"):
        start()


def test_stale_lock_is_replaced(start, gold_path):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    lock = gold_path.with_name("gold.json.lock")
    lock.write_text(
        json.dumps({"pid": dead.pid, "started": "2020-01-01T00:00:00+00:00"})
    )
    start()
    assert json.loads(lock.read_text())["pid"] == os.getpid()


def test_garbage_lock_counts_as_stale(start, gold_path):
    gold_path.with_name("gold.json.lock").write_text("not json")
    assert Client(start()).state()["total"] == 3


def test_failed_start_leaves_no_lock(gold_path):
    with pytest.raises(ValueError):
        _label.serve(Gold(), taxonomy())  # ty: ignore[invalid-argument-type]
    assert not gold_path.with_name("gold.json.lock").exists()


def test_wait_returns_after_stop(start):
    h = start()
    h.stop()
    h.wait()


# --- gold rule -----------------------------------------------------------------------------------


def walk(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield k
            yield from walk(v)
    elif isinstance(x, list):
        for v in x:
            yield from walk(v)


def test_no_response_carries_a_prediction(start):
    c = Client(start())
    bodies = [c.state(), c.label("1", ["a"])[1], c.call("POST", "/api/back")[1]]
    bodies.append(c.call("POST", "/api/skip")[1])
    keys = {k.lower() for b in bodies for k in walk(b)}
    assert not {k for k in keys if "predict" in k or "reasoning" in k or "model" in k}


def test_server_module_never_touches_a_model():
    src = Path(_label.__file__).read_text()
    assert "classifier" not in src and "pydantic_ai" not in src


def test_nothing_public_beyond_serve():
    public = {
        n
        for n, v in vars(_label).items()
        if not n.startswith("_")
        and getattr(v, "__module__", None) == "goldlabel._label"
    }
    assert public == {"serve", "label", "Handle"}


# --- notes (013) ----------------------------------------------------------------------------


def label_with(c, id_, labels, **extra):
    return c.call("POST", "/api/label", {"id": id_, "labels": labels, **extra})[:2]


def test_a_note_is_stored_trimmed_and_the_state_carries_it(start, gold_path):
    c = Client(start())
    status, _ = label_with(c, "1", ["a"], note="  two policies in one sentence \n")
    assert status == 200
    saved = on_disk(gold_path)[0]
    assert saved["note"] == "two policies in one sentence"
    assert saved["labelled_by"] == "goldlabel-ui"
    c.call("POST", "/api/back")
    assert c.state()["item"]["note"] == "two policies in one sentence"


def test_an_unlabelled_row_has_a_null_note_in_the_state(start):
    assert Client(start()).state()["item"]["note"] is None


def test_an_empty_note_removes_the_key_and_a_missing_note_keeps_it(start, gold_path):
    c = Client(start())
    label_with(c, "1", ["a"], note="keep me")
    label_with(c, "1", ["b"])  # an older client sends no note
    assert on_disk(gold_path)[0]["note"] == "keep me"
    label_with(c, "1", ["b"], note="   ")
    assert "note" not in on_disk(gold_path)[0]


def test_a_note_that_is_not_a_string_is_refused_and_nothing_is_written(
    start, gold_path
):
    c = Client(start())
    before = gold_path.read_text()
    status, body = label_with(c, "1", ["a"], note=5)
    assert status == 400 and "note" in body["error"]
    assert gold_path.read_text() == before


# --- the pass (014) -----------------------------------------------------------------------------


@pytest.fixture
def fifty_and_fifty(tmp_path):
    """50 labelled dev rows d0..d49 and 50 pending test rows t0..t49."""
    p = tmp_path / "gold.json"
    write_gold(
        p,
        rows(*[(f"d{i}", ["a"], "dev") for i in range(50)])
        + rows(*[(f"t{i}", None, "test") for i in range(50)]),
    )
    return p


def serve(name, **kw):
    return _label.serve(Gold()[name], taxonomy(), **kw)


def test_the_pass_is_the_samples_pending_rows_and_never_another_sample(
    fifty_and_fifty,
):
    h = serve("test")
    try:
        c = Client(h)
        s = c.state()
        assert (s["total"], s["done"], s["sample"]) == (50, 0, "test")
        served = []
        while s["item"] is not None:
            served.append(s["item"]["id"])
            s = c.label(s["item"]["id"], ["b"])[1]
        assert served == [f"t{i}" for i in range(50)]
        assert (s["done"], s["total"], s["finished"]) == (50, 50, True)
    finally:
        h.stop()


def test_a_new_pass_holds_only_what_is_still_pending(fifty_and_fifty):
    h = serve("test")
    try:
        c = Client(h)
        for i in range(20):
            c.label(f"t{i}", ["b"])
    finally:
        h.stop()
    h = serve("test")
    try:
        s = Client(h).state()
        assert (s["total"], s["done"], s["item"]["id"]) == (30, 0, "t20")
    finally:
        h.stop()


def test_force_open_ui_passes_every_row_of_the_sample(fifty_and_fifty):
    h = serve("dev", force_open_ui=True)
    try:
        s = Client(h).state()
        assert (s["total"], s["done"], s["item"]["id"]) == (50, 50, "d0")
    finally:
        h.stop()


def test_back_returns_to_a_row_labelled_in_this_pass(fifty_and_fifty):
    h = serve("test")
    try:
        c = Client(h)
        c.label("t0", ["a"])
        s = c.call("POST", "/api/back")[1]
        assert s["item"]["id"] == "t0" and s["item"]["labels"] == ["a"]
        assert (s["total"], s["done"]) == (50, 1)
    finally:
        h.stop()


def test_a_row_outside_the_pass_cannot_be_labelled(fifty_and_fifty):
    before = fifty_and_fifty.read_bytes()
    h = serve("test")
    try:
        status, _ = Client(h).label("d0", ["b"])
        assert status == 404
    finally:
        h.stop()
    assert fifty_and_fifty.read_bytes() == before


def test_a_review_pass_walks_every_row_in_file_order(fifty_and_fifty):
    h = serve("dev", force_open_ui=True)
    try:
        c = Client(h)
        s = c.label("d0", ["b"])[1]
        assert (s["item"]["id"], s["position"]) == ("d1", 2)
        s = c.call("POST", "/api/skip")[1]
        assert s["item"]["id"] == "d2"
        for i in range(2, 49):
            s = c.label(f"d{i}", ["a"])[1]
        assert s["item"]["id"] == "d49"
        s = c.label("d49", ["a"])[1]
        assert s["finished"] is True and s["item"] is None
    finally:
        h.stop()
