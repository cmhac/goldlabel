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
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse

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


def _acquire(lock: Path, port: int) -> None:
    lock.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                info = json.loads(lock.read_text())
                pid, started = int(info["pid"]), info.get("started")
            except (OSError, ValueError, KeyError, TypeError):
                pid, started = None, None  # unreadable: stale
            if pid is not None and _alive(pid):
                raise GoldRuntimeError(
                    f"{lock.parent} is already being labelled (pid {pid}, started "
                    f"{started}); finish or stop that session first"
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
        all_rows = self.gold._read()
        target = next((r for r in all_rows if r.id == id_ and r.id in self.ids), None)
        if target is None:
            raise KeyError(id_)
        stamp = {
            "labels": labels,
            "labelled_by": "goldlabel-ui",
            "labelled_at": datetime.now(UTC).isoformat(),
        }
        # shortcut: no note length limit beyond MAX_BODY, add one if gold files grow huge notes.
        if note is not None:  # None: an older client, keep the row's note
            stamp["note"] = note.strip() or None
        self.gold._write(
            [r.model_copy(update=stamp) if r is target else r for r in all_rows]
        )
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
            if g._doc().get("taxonomy") != taxonomy:
                Taxonomy.model_validate(taxonomy)
                g._write(g._read(), taxonomy=taxonomy)

    def new_pass(self, stem: str, names: list[str], force: bool = False) -> str:
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
        if len(parts) == 4 and parts[:3] == ["", "api", "pass"]:
            try:
                return self._send(200, server.state(parts[3]))
            except KeyError:
                return self._send(404, {"error": "this pass has ended"})
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
                self._send(200, state)
                if parts[4] == "done" and server.stop_on_done:
                    threading.Thread(target=server.stop, daemon=True).start()
                return
        except KeyError:
            return self._send(404, {"error": "this pass has ended"})
        self._send(404, {"error": "not found"})

    def _label(self, server: Server, body: dict) -> None:
        pass_id, id_ = body.get("pass"), body.get("id")
        labels, note = body.get("labels"), body.get("note")
        if (
            not isinstance(pass_id, str)
            or not isinstance(id_, str)
            or not (
                isinstance(labels, list) and all(isinstance(x, str) for x in labels)
            )
            or not isinstance(note, str | None)
        ):
            return self._send(
                400, {"error": "send {pass: str, id: str, labels: [str], note?: str}"}
            )
        try:
            return self._send(200, server.label(pass_id, id_, labels, note))
        except KeyError as e:
            if e.args == (id_,):
                return self._send(404, {"error": f"no row {id_!r} in this pass"})
            raise
        except ValueError as e:
            return self._send(400, {"error": getattr(e, "text", str(e))})

    def _new_pass(self, server: Server, body: dict) -> None:
        dataset, samples, force = (
            body.get("dataset"),
            body.get("samples"),
            body.get("force"),
        )
        if (
            not isinstance(dataset, str)
            or not (
                isinstance(samples, list)
                and samples
                and all(isinstance(x, str) for x in samples)
            )
            or not isinstance(force, bool | None)
        ):
            return self._send(
                400, {"error": "send {dataset: str, samples: [str], force?: bool}"}
            )
        try:
            return self._send(
                200, {"pass": server.new_pass(dataset, samples, bool(force))}
            )
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
        server.store_taxonomy(path.stem, taxonomy.model_dump())
        server.pass_id = server.new_pass(path.stem, list(sample.names), force_open_ui)
    except BaseException:
        server.stop()
        raise
    return server


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
