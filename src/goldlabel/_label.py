"""The labelling server: the one place (besides `Gold.import_rows`) where gold labels are written.

A label is written only because a person's HTTP request says so, stamped `labelled_by: "goldlabel-ui"`.
Nothing here calls a model or returns a prediction. One `Server` per storage folder serves every pass:
a `Pass` is one walk over some rows of a sample, and the server decides which row is next, so the
page stays thin. The page is `web/index.html` + `app.js` + `app.css` from the package. There is no
access token: the server listens on 127.0.0.1 only, refuses a foreign Host, and refuses a write that
lacks the `X-Goldlabel` header (a web page from another site cannot send it without a permission check
the server never answers).
"""

import atexit
import json
import os
import re
import secrets
import sys
import threading
import time
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from goldlabel._gold_rule import GOLD_RULE_SHORT, GoldError, GoldRuntimeError
from goldlabel.gold import Gold, GoldSet, Sample
from goldlabel.taxonomy import OFF_TOPIC, Label, Taxonomy, validate_labels

OFF_TOPIC_DESCRIPTION = "the item matches none of the labels above"
MAX_BODY = 1_000_000
LOCK = "labelling.lock"
PAGES = {  # the only static paths: URL path -> (file in goldlabel/web, content type)
    "/": ("index.html", "text/html"),
    "/app.js": ("app.js", "text/javascript"),
    "/app.css": ("app.css", "text/css"),
}


def _alive(pid: int) -> bool:
    if sys.platform == "win32":  # os.kill(pid, 0) would terminate the process there
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
        return bool(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it exists, it is somebody else's
        return True
    return True


def _answers(port: int) -> bool:
    """Does a labelling server answer on this port?"""
    try:
        urlopen(f"http://127.0.0.1:{port}/api/datasets", timeout=2).read()
    except (OSError, ValueError):
        return False
    return True


def _held(lock: Path) -> tuple[int, str | None] | None:
    """(pid, started) of a live server holding `lock`: its process exists and its port answers."""
    try:
        info = json.loads(lock.read_text())
        pid, port, started = int(info["pid"]), int(info["port"]), info.get("started")
    except (OSError, ValueError, KeyError, TypeError):
        return None  # missing or unreadable: stale
    return (pid, started) if _alive(pid) and _answers(port) else None


def _live(folder: Path) -> int | None:
    """The port of the live labelling server of `folder`, if there is one."""
    if _held(folder / LOCK) is None:
        return None
    return int(json.loads((folder / LOCK).read_text())["port"])


def _acquire(lock: Path, port: int) -> None:
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            held = _held(lock)
            if held is not None:
                raise GoldRuntimeError(
                    f"{lock.parent} is already being labelled (pid {held[0]}, started "
                    f"{held[1]}); finish or stop that session first"
                ) from None
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w") as f:
            json.dump(
                {
                    "pid": os.getpid(),
                    "port": port,
                    "started": datetime.now(UTC).isoformat(),
                },
                f,
            )
        return
    raise GoldRuntimeError(f"could not take the lock {lock}")


def _release(lock) -> None:
    try:
        if json.loads(lock.read_text()).get("pid") == os.getpid():
            lock.unlink(missing_ok=True)
    except (OSError, ValueError, AttributeError):
        pass


NOT_A_SAMPLE = 'label a Sample, not {kind}: dev = gold.draw_sample("dev"), then gl.label(dev, taxonomy)'


def _need_sample(sample) -> None:
    if not isinstance(sample, Sample):
        raise GoldError(NOT_A_SAMPLE.format(kind=type(sample).__name__))


def _stems(folder: Path) -> list[str]:
    """The gold datasets of a storage folder, as file stems: `gold`, `gold-<name>`."""
    files = folder.glob("gold*.json") if folder.is_dir() else []
    return sorted(
        f.stem for f in files if re.fullmatch(r"gold(-[a-z0-9_-]+)?\.json", f.name)
    )


def _title(stem: str) -> str:
    return "default" if stem == "gold" else stem.removeprefix("gold-")


def _taxonomy(gold: Gold) -> Taxonomy:
    """The taxonomy stored in the gold file; with none, the labels already used in its rows."""
    stored = gold._doc().get("taxonomy")
    if stored:
        return Taxonomy.model_validate(stored)
    rows = gold._read()
    used = sorted({x for r in rows for x in r.labels or []} - {OFF_TOPIC})
    multi = any(len(r.labels or []) > 1 for r in rows)
    return Taxonomy(
        mode="multi" if multi else "single", labels=[Label(name=n) for n in used]
    )


def _save(gold: Gold, id_: str, labels: list[str], note: str | None, only=None):
    """Write a person's labels (and note) for row `id_`; the only place a label is written.

    A row that already had labels keeps the values from before the change in its `revisions`
    list, in the same rewrite of the file; a first label, or a save that changes nothing,
    adds no entry. `only` limits which ids may be saved (a pass's ids). KeyError: no such row.
    """
    rows = gold._read()
    target = next(
        (r for r in rows if r.id == id_ and (only is None or id_ in only)), None
    )
    if target is None:
        raise KeyError(id_)
    # shortcut: no note length limit beyond MAX_BODY, add one if gold files grow huge notes.
    new_note = (
        target.note if note is None else (note.strip() or None)
    )  # None: keep the note
    if target.labels and set(labels) == set(target.labels) and new_note == target.note:
        return target
    now = datetime.now(UTC).isoformat()
    update = {
        "labels": labels,
        "labelled_by": "goldlabel-ui",
        "labelled_at": now,
        "note": new_note,
    }
    if target.labels:
        before = {
            "at": now,
            "labels": target.labels,
            "note": target.note,
            "labelled_by": target.labelled_by,
        }
        update["revisions"] = [*(target.revisions or []), before]
    saved = target.model_copy(update=update)
    gold._write([saved if r is target else r for r in rows])
    return saved


class Pass:
    """One labelling pass: `ids` are the rows it pages, fixed when it starts."""

    def __init__(self, gold: Gold, names: tuple[str, ...], ids: set[str], review: bool):
        self.gold, self.names, self.ids, self.review = gold, names, ids, review
        self.current: str | None = None
        self.ended = False
        self._history: list[str] = []
        self.current = self._after(self._scope(), "")

    def _scope(self):
        return [r for r in self.gold._read() if r.id in self.ids]

    def _after(self, rows, id_):
        """The next pending row after `id_` in file order, else the first pending one. A review
        pass (`force_open_ui`) walks every row once, in file order, then finishes."""
        ids = [r.id for r in rows]
        start = ids.index(id_) + 1 if id_ in ids else 0
        if self.review:
            return ids[start] if start < len(ids) else None
        for r in rows[start:] + rows[:start]:
            if not r.labels:
                return r.id
        return None

    def pending(self) -> int:
        return sum(1 for r in self._scope() if not r.labels)

    def state(self, taxonomy: Taxonomy) -> dict:
        rows = self._scope()
        by_id = {r.id: r for r in rows}
        row = by_id.get(self.current) if self.current else None
        done = sum(1 for r in rows if r.labels)
        position = [r.id for r in rows].index(row.id) + 1 if row else len(rows)
        descriptions = [(label.name, label.description) for label in taxonomy.labels]
        descriptions.append((OFF_TOPIC, OFF_TOPIC_DESCRIPTION))
        return {
            "sample": " + ".join(self.names),
            "item": {
                "id": row.id,
                "text": row.text,
                "labels": row.labels or None,
                "note": row.note,
            }
            if row
            else None,
            "position": position,
            "done": done,
            "total": len(rows),
            "pending": len(rows) - done,
            "ended": self.ended,
            "labels": [{"name": n, "description": d} for n, d in descriptions],
            "mode": taxonomy.mode,
            "counts": GoldSet(rows).counts(taxonomy),
            "finished": row is None,
        }

    def _move(self, rows, after) -> None:
        if self.current is not None:
            self._history.append(self.current)
        self.current = self._after(rows, after)

    def label(
        self, id_: str, labels: list[str], note: str | None, taxonomy: Taxonomy
    ) -> dict:
        validate_labels(labels, taxonomy)
        _save(self.gold, id_, labels, note, only=self.ids)
        self._move(self._scope(), id_)
        return self.state(taxonomy)

    def back(self, taxonomy: Taxonomy) -> dict:
        if self._history:
            self.current = self._history.pop()
        return self.state(taxonomy)

    def skip(self, taxonomy: Taxonomy) -> dict:
        if self.current is not None:
            self._move(self._scope(), self.current)
        return self.state(taxonomy)


class Server:
    """The one labelling server of a storage folder: binds 127.0.0.1, owns the folder lock."""

    def __init__(self, folder: Path, *, stop_on_done: bool = True, port=None):
        self.folder, self.stop_on_done = Path(folder), stop_on_done
        self.passes: dict[str, Pass] = {}
        self.pass_id = ""  # the first pass `serve` made, for `url`
        self.lock = self.folder / LOCK
        self._mutex = threading.Lock()
        self._stopping = False
        self._stopped = threading.Event()  # set once the lock is released
        request = type("Request", (_Request,), {"session": self})
        self.server = ThreadingHTTPServer(("127.0.0.1", port or 0), request)
        try:
            _acquire(self.lock, self.port)
        except BaseException:
            self.server.server_close()
            raise
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        atexit.register(self.stop)

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/#/pass/{self.pass_id}"

    def wait(self) -> None:
        self._stopped.wait()

    def stop(self) -> None:
        with self._mutex:
            if self._stopping:
                return
            self._stopping = True
        atexit.unregister(self.stop)
        self.server.shutdown()
        self.server.server_close()
        _release(self.lock)
        self._stopped.set()

    # --- state; every method takes the mutex ---------------------------------------------------

    def gold(self, stem: str) -> Gold:
        """The dataset whose file is `<stem>.json` in this folder (`gold` or `gold-<name>`)."""
        if not re.fullmatch(r"gold(-[a-z0-9_-]+)?", stem):
            raise KeyError(stem)
        g = Gold(name=None if stem == "gold" else stem.removeprefix("gold-"))
        # a notebook may change settings.root after this server started, so pin the folder
        g.path = self.folder / g.path.name
        if not g.path.exists():
            raise KeyError(stem)
        return g

    def store_taxonomy(self, stem: str, taxonomy: dict) -> None:
        with self._mutex:
            g = self.gold(stem)
            Taxonomy.model_validate(taxonomy)
            if g._doc().get("taxonomy") != taxonomy:
                g._write(g._read(), taxonomy=taxonomy)

    def new_pass(
        self, stem: str, names: list[str], force: bool = False, taxonomy=None
    ) -> str:
        if taxonomy is not None:
            self.store_taxonomy(stem, taxonomy)
        with self._mutex:
            g = self.gold(stem)
            rows = [r for r in g._read() if r.sample in names]
            if not set(names) <= {r.sample for r in g._read()}:
                raise KeyError(names)
            ids = {r.id for r in rows if force or not r.labels}
            pass_id = secrets.token_urlsafe(6)
            self.passes[pass_id] = Pass(g, tuple(names), ids, review=force)
            return pass_id

    def _pass(self, pass_id: str) -> Pass:
        if pass_id not in self.passes:
            raise KeyError(pass_id)
        return self.passes[pass_id]

    def state(self, pass_id: str) -> dict:
        with self._mutex:
            p = self._pass(pass_id)
            return p.state(_taxonomy(p.gold))

    def label(self, pass_id, id_, labels, note) -> dict:
        with self._mutex:
            p = self._pass(pass_id)
            return p.label(id_, labels, note, _taxonomy(p.gold))

    def back(self, pass_id: str) -> dict:
        with self._mutex:
            p = self._pass(pass_id)
            return p.back(_taxonomy(p.gold))

    def skip(self, pass_id: str) -> dict:
        with self._mutex:
            p = self._pass(pass_id)
            return p.skip(_taxonomy(p.gold))

    def done(self, pass_id: str) -> dict:
        with self._mutex:
            p = self._pass(pass_id)
            p.ended = True
            return p.state(_taxonomy(p.gold))

    def datasets(self) -> list[dict]:
        """Every gold file of the folder (`gold.json`, `gold-<name>.json`) with its samples."""
        out = []
        with self._mutex:
            for stem in _stems(self.folder):
                entry = {"name": stem, "title": _title(stem)}
                try:
                    g = self.gold(stem)
                    samples: dict[str, list] = {}
                    for r in g._read():
                        samples.setdefault(r.sample, []).append(r)
                    entry["taxonomy"] = bool(g._doc().get("taxonomy"))
                    entry["samples"] = [
                        {
                            "name": n,
                            "rows": len(rs),
                            "labelled": sum(1 for r in rs if r.labels),
                            "pending": sum(1 for r in rs if not r.labels),
                        }
                        for n, rs in samples.items()
                    ]
                except GoldError as e:
                    entry = {**entry, "error": getattr(e, "text", str(e))}
                out.append(entry)
        return out

    def rows(self, stem: str, sample: str) -> list[dict]:
        with self._mutex:
            rows = [r for r in self.gold(stem)._read() if r.sample == sample]
            if not rows:
                raise KeyError(sample)
            return [
                {
                    "id": r.id,
                    "labels": r.labels or None,
                    "note": bool(r.note),
                    "revised": bool(r.revisions),
                }
                for r in rows
            ]

    def row(self, stem: str, id_: str) -> dict:
        with self._mutex:
            return self._row(self.gold(stem), id_)

    def _row(self, g: Gold, id_: str) -> dict:
        r = next((r for r in g._read() if r.id == id_), None)
        if r is None:
            raise KeyError(id_)
        taxonomy = _taxonomy(g)
        options = [(x.name, x.description) for x in taxonomy.labels]
        options.append((OFF_TOPIC, OFF_TOPIC_DESCRIPTION))
        return {
            "id": r.id,
            "text": r.text,
            "sample": r.sample,
            "labels": r.labels or None,
            "note": r.note,
            "labelled_by": r.labelled_by,
            "revisions": r.revisions or [],
            "options": [{"name": n, "description": d} for n, d in options],
            "mode": taxonomy.mode,
            "stored_taxonomy": bool(g._doc().get("taxonomy")),
        }

    def revise(self, stem: str, id_: str, labels: list[str], note: str | None) -> dict:
        """A person's label or revision for any row of a dataset, with or without a pass."""
        with self._mutex:
            g = self.gold(stem)
            validate_labels(labels, _taxonomy(g))
            _save(g, id_, labels, note)
            return self._row(g, id_)


class _Request(BaseHTTPRequestHandler):
    session: Server  # set on a subclass made per server

    def log_message(self, format, *args):  # keep the notebook output clean
        pass

    def _send(self, status: int, body, content_type="application/json") -> None:
        data = (
            json.dumps(body) if content_type == "application/json" else body
        ).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _allowed(self, server: Server, write: bool) -> bool:
        # The Host check stops DNS rebinding; the custom header on writes stops other web pages.
        if self.headers.get("Host") not in (
            f"127.0.0.1:{server.port}",
            f"localhost:{server.port}",
        ):
            return False
        return not write or self.headers.get("X-Goldlabel") == "1"

    def _body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if 0 < n <= MAX_BODY else {}
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def do_GET(self):
        server = self.session
        if not self._allowed(server, write=False):
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        if path in PAGES:
            name, kind = PAGES[path]
            page = resources.files("goldlabel").joinpath("web", name).read_text("utf-8")
            return self._send(200, page, kind)
        parts = path.split("/")
        query = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
        try:
            if path == "/api/datasets":
                return self._send(200, server.datasets())
            if path in ("/api/rows", "/api/row"):
                need = {
                    "/api/rows": ("dataset", "sample"),
                    "/api/row": ("dataset", "id"),
                }
                if not set(need[path]) <= set(query):
                    return self._send(
                        400, {"error": f"send {' and '.join(need[path])}"}
                    )
                call = server.rows if path == "/api/rows" else server.row
                return self._send(200, call(*(query[k] for k in need[path])))
            if len(parts) == 4 and parts[:3] == ["", "api", "pass"]:
                return self._send(200, server.state(parts[3]))
        except KeyError:
            gone = (
                "this pass has ended" if path.startswith("/api/pass/") else "not found"
            )
            return self._send(404, {"error": gone})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        server = self.session
        if not self._allowed(server, write=True):
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        body = self._body()
        if body is None:
            return self._send(400, {"error": "the body must be a JSON object"})
        parts = path.split("/")
        try:
            if path == "/api/label":
                return self._label(server, body)
            if path == "/api/pass":
                return self._new_pass(server, body)
            if (
                len(parts) == 5
                and parts[:3] == ["", "api", "pass"]
                and parts[4] in ("back", "skip", "done")
            ):
                state = getattr(server, parts[4])(parts[3])
                if (
                    parts[4] == "done"
                ):  # the page leaves for the dataset list if we stay up
                    state = {**state, "closing": server.stop_on_done}
                self._send(200, state)
                if parts[4] == "done" and server.stop_on_done:
                    threading.Thread(target=server.stop, daemon=True).start()
                return
        except KeyError:
            return self._send(404, {"error": "this pass has ended"})
        self._send(404, {"error": "not found"})

    def _label(self, server: Server, body: dict) -> None:
        pass_id, dataset, id_ = body.get("pass"), body.get("dataset"), body.get("id")
        labels, note = body.get("labels"), body.get("note")
        if (
            not isinstance(id_, str)
            or not (isinstance(pass_id, str) or isinstance(dataset, str))
            or not (
                isinstance(labels, list) and all(isinstance(x, str) for x in labels)
            )
            or not isinstance(note, str | None)
        ):
            return self._send(
                400,
                {
                    "error": "send {pass or dataset: str, id: str, labels: [str], note?: str}"
                },
            )
        try:
            if isinstance(pass_id, str):
                return self._send(200, server.label(pass_id, id_, labels, note))
            if isinstance(dataset, str):
                return self._send(200, server.revise(dataset, id_, labels, note))
        except KeyError as e:
            if isinstance(pass_id, str) and e.args != (id_,):
                raise  # an unknown pass
            where = "this pass" if isinstance(pass_id, str) else f"dataset {dataset!r}"
            return self._send(404, {"error": f"no row {id_!r} in {where}"})
        except ValueError as e:
            return self._send(400, {"error": getattr(e, "text", str(e))})

    def _new_pass(self, server: Server, body: dict) -> None:
        dataset, samples = body.get("dataset"), body.get("samples")
        force, taxonomy = body.get("force"), body.get("taxonomy")
        if (
            not isinstance(dataset, str)
            or not (
                isinstance(samples, list)
                and samples
                and all(isinstance(x, str) for x in samples)
            )
            or not isinstance(force, bool | None)
            or not isinstance(taxonomy, dict | None)
        ):
            return self._send(
                400,
                {
                    "error": "send {dataset, samples: [str], force?: bool, taxonomy?: object}"
                },
            )
        try:
            return self._send(
                200, {"pass": server.new_pass(dataset, samples, bool(force), taxonomy)}
            )
        except ValueError as e:
            return self._send(400, {"error": getattr(e, "text", str(e))})
        except KeyError:
            return self._send(
                404, {"error": f"no dataset {dataset!r} with samples {samples}"}
            )


def serve(
    sample: Sample,
    taxonomy: Taxonomy,
    *,
    force_open_ui=False,
    port=None,
    stop_on_done=True,
) -> Server:
    """Start the labelling server on 127.0.0.1 and return at once. The first pass is the rows of
    `sample` that are pending now (every row with `force_open_ui=True`); it starts at the first."""
    _need_sample(sample)
    path = sample.gold.path
    server = Server(path.parent, stop_on_done=stop_on_done, port=port)
    try:
        server.pass_id = server.new_pass(
            path.stem, list(sample.names), force_open_ui, taxonomy.model_dump()
        )
    except BaseException:
        server.stop()
        raise
    return server


def _ask(port: int, path: str, body: dict | None = None) -> dict:
    """One request to the live server of this machine; its error text becomes a GoldRuntimeError."""
    req = Request(
        f"http://127.0.0.1:{port}{path}",
        None if body is None else json.dumps(body).encode(),
        {"X-Goldlabel": "1", "Content-Type": "application/json"},
    )
    try:
        return json.loads(urlopen(req, timeout=10).read())
    except HTTPError as e:
        text = json.loads(e.read()).get("error", e.reason)
        raise GoldRuntimeError(
            f"the running labelling page refused the request: {text}"
        ) from None


def _join(
    port: int, sample: Sample, taxonomy: Taxonomy, force: bool, open_it: bool
) -> None:
    """Hand a pass to the labelling server that is already running, then wait for its rows."""
    body = {
        "dataset": sample.gold.path.stem,
        "samples": list(sample.names),
        "force": force,
        "taxonomy": taxonomy.model_dump(),  # the server, the one writer, stores it
    }
    pass_id = _ask(port, "/api/pass", body)["pass"]
    url = f"http://127.0.0.1:{port}/#/pass/{pass_id}"
    print(
        f"A labelling page is already running; this pass is there: {url}\n"
        "Label in that page, then press Done (or label every row).\n"
        f"{GOLD_RULE_SHORT}"
    )
    if open_it:
        webbrowser.open(url)
    if force:
        return  # a review pass has nothing pending to wait for
    try:
        while True:
            state = _ask(port, f"/api/pass/{pass_id}")
            if state["pending"] == 0 or state["ended"]:
                return
            time.sleep(1)
    except (OSError, GoldRuntimeError):
        print("The labelling page stopped; returning what is labelled so far.")


def label(
    sample: Sample,
    taxonomy: Taxonomy,
    *,
    force_open_ui: bool = False,
    open_browser: bool = True,
    port: int | None = None,
) -> Sample:
    """Open the labelling page on the rows of `sample` that are pending and wait for **Done**;
    returns the Sample. Every click is saved at once. If none is pending it prints one line and
    returns at once, unless `force_open_ui=True` (to review or relabel every row of the sample)."""
    _need_sample(sample)
    gold, name = sample.gold, " + ".join(sample.names)
    orphans = len(gold.orphaned(taxonomy))
    if orphans:
        print(
            f"{orphans} labelled row(s) in {gold.path} use labels that are not in this "
            "taxonomy; continuing."
        )
    scope = sample.rows
    if not scope or (not force_open_ui and all(r.labels for r in scope)):
        print(
            f"All {len(scope)} rows in {name} are labelled; nothing to label. "
            "Pass force_open_ui=True to review or relabel."
            if scope
            else f"No rows to label in {name}: draw some first (gold.draw_sample)."
        )
        return sample
    live = _live(sample.gold.path.parent)
    if live is not None:
        _join(live, sample, taxonomy, force_open_ui, open_browser)
        return sample
    handle = serve(sample, taxonomy, force_open_ui=force_open_ui, port=port)
    try:
        print(
            f"Labelling page: {handle.url}\n"
            "Label the rows in your browser, then press Done on the page.\n"
            f"{GOLD_RULE_SHORT}"
        )
        if open_browser:
            webbrowser.open(handle.url)
        handle.wait()
    except BaseException:
        handle.stop()
        raise
    return sample


def run_forever(folder: Path, name: str | None = None, port: int | None = None) -> int:
    """`goldlabel label`: serve every dataset of `folder` until interrupted; the exit code."""
    stems = _stems(folder)
    if not stems:
        print(
            f"No gold dataset in {folder}. Make one in a notebook with gl.Gold(candidates) "
            "and gold.draw_sample(...)."
        )
        return 1
    stem = "gold" if name is None else f"gold-{name}"
    if name is not None and stem not in stems:
        print(
            f"No gold dataset {name!r} in {folder}. Datasets there: "
            + ", ".join(_title(x) for x in stems)
        )
        return 1
    live = _live(folder)
    if live is not None:
        url = f"http://127.0.0.1:{live}/" + (f"#/d/{stem}" if name is not None else "")
        print(f"A labelling page is already running for {folder}: {url}")
        webbrowser.open(url)
        return 0
    try:
        server = Server(folder, stop_on_done=False, port=port)
    except (OSError, GoldRuntimeError) as e:
        print(f"Cannot start the labelling page (port {port or 'any'}): {e}")
        return 1
    url = f"http://127.0.0.1:{server.port}/" + (
        f"#/d/{stem}" if name is not None else ""
    )
    try:
        print(
            f"Labelling page: {url}\nFolder: {folder}\n"
            f"Label in your browser; press Ctrl-C here to stop.\n{GOLD_RULE_SHORT}"
        )
        webbrowser.open(url)
        server.wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0
