"""The labelling server: the one place (besides `Gold.import_rows`) where gold labels are written.

A label is written only because a person's HTTP request says so, stamped `labelled_by: "goldlabel-ui"`.
Nothing here calls a model or returns a prediction. The server decides which item is next, so the
page stays thin. The page is `web/index.html` + `app.js` + `app.css` from the package; the three are served only with
the token and Host checks like everything else, and the HTML carries the token in its asset URLs.
"""

import atexit
import json
import os
import secrets
import sys
import threading
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlparse

from goldlabel._gold_rule import GOLD_RULE_SHORT, GoldError, GoldRuntimeError
from goldlabel.gold import GoldSet, Sample
from goldlabel.taxonomy import OFF_TOPIC, Taxonomy, validate_labels

OFF_TOPIC_DESCRIPTION = "the item matches none of the labels above"
MAX_BODY = 1_000_000
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


def _acquire(lock) -> None:
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
                    f"{lock.with_suffix('')} is already being labelled (pid {pid}, started "
                    f"{started}); finish or stop that session first"
                ) from None
            lock.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w") as f:
            json.dump({"pid": os.getpid(), "started": datetime.now(UTC).isoformat()}, f)
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


class Handle:
    """One labelling pass: `ids` are the rows it pages, fixed when it starts."""

    def __init__(self, sample: Sample, taxonomy: Taxonomy, ids: set[str], review=False):
        self.sample, self.gold, self.taxonomy = sample, sample.gold, taxonomy
        self.ids, self.review = ids, review
        self.token = secrets.token_urlsafe(32)
        self.lock = self.gold.path.with_name(self.gold.path.name + ".lock")
        self._mutex = threading.Lock()
        self._stopping = False
        self._stopped = threading.Event()  # set once the lock is released
        self._history: list[str] = []
        self.current: str | None = None
        self.server: ThreadingHTTPServer

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/?token={self.token}"

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

    # --- state; the caller holds self._mutex ------------------------------------------------

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

    def _state(self) -> dict:
        rows = self._scope()
        by_id = {r.id: r for r in rows}
        row = by_id.get(self.current) if self.current else None
        done = sum(1 for r in rows if r.labels)
        position = [r.id for r in rows].index(row.id) + 1 if row else len(rows)
        descriptions = [
            (label.name, label.description) for label in self.taxonomy.labels
        ]
        descriptions.append((OFF_TOPIC, OFF_TOPIC_DESCRIPTION))
        return {
            "sample": " + ".join(self.sample.names),
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
            "labels": [{"name": n, "description": d} for n, d in descriptions],
            "mode": self.taxonomy.mode,
            "counts": GoldSet(rows).counts(self.taxonomy),
            "finished": row is None,
        }

    def _move(self, rows, after) -> None:
        if self.current is not None:
            self._history.append(self.current)
        self.current = self._after(rows, after)

    def state(self) -> dict:
        with self._mutex:
            return self._state()

    def label(self, id_: str, labels: list[str], note: str | None = None) -> dict:
        validate_labels(labels, self.taxonomy)
        with self._mutex:
            all_rows = self.gold._read()
            target = next(
                (r for r in all_rows if r.id == id_ and r.id in self.ids), None
            )
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
            return self._state()

    def back(self) -> dict:
        with self._mutex:
            if self._history:
                self.current = self._history.pop()
            return self._state()

    def skip(self) -> dict:
        with self._mutex:
            if self.current is not None:
                self._move(self._scope(), self.current)
            return self._state()


class _Request(BaseHTTPRequestHandler):
    session: Handle  # set on a subclass made per server in `serve`

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

    def _allowed(self, handle: Handle) -> bool:
        # The Host check stops DNS rebinding; the token stops any other local process or page.
        if self.headers.get("Host") not in (
            f"127.0.0.1:{handle.port}",
            f"localhost:{handle.port}",
        ):
            return False
        given = (
            self.headers.get("X-Goldlabel-Token")
            or (parse_qs(urlparse(self.path).query).get("token", [""])[0])
        )
        return secrets.compare_digest(given.encode(), handle.token.encode())

    def _body(self) -> dict | None:
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n)) if 0 < n <= MAX_BODY else {}
        except ValueError:
            return None
        return body if isinstance(body, dict) else None

    def do_GET(self):
        handle = self.session
        if not self._allowed(handle):
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        if path in PAGES:
            name, kind = PAGES[path]
            page = resources.files("goldlabel").joinpath("web", name).read_text("utf-8")
            return self._send(200, page.replace("__TOKEN__", handle.token), kind)
        if path == "/api/state":
            return self._send(200, handle.state())
        self._send(404, {"error": "not found"})

    def do_POST(self):
        handle = self.session
        if not self._allowed(handle):
            return self._send(403, {"error": "forbidden"})
        path = urlparse(self.path).path
        body = self._body()
        if body is None:
            return self._send(400, {"error": "the body must be a JSON object"})
        if path == "/api/label":
            id_, labels, note = body.get("id"), body.get("labels"), body.get("note")
            if (
                not isinstance(id_, str)
                or not (
                    isinstance(labels, list) and all(isinstance(x, str) for x in labels)
                )
                or not isinstance(note, str | None)
            ):
                return self._send(
                    400, {"error": "send {id: str, labels: [str], note?: str}"}
                )
            try:
                return self._send(200, handle.label(id_, labels, note))
            except KeyError:
                return self._send(404, {"error": f"no row {id_!r} in this pass"})
            except ValueError as e:
                return self._send(400, {"error": getattr(e, "text", str(e))})
        if path == "/api/back":
            return self._send(200, handle.back())
        if path == "/api/skip":
            return self._send(200, handle.skip())
        if path == "/api/done":
            self._send(200, handle.state())
            threading.Thread(target=handle.stop, daemon=True).start()
            return
        self._send(404, {"error": "not found"})


def serve(
    sample: Sample, taxonomy: Taxonomy, *, force_open_ui=False, port=None
) -> Handle:
    """Start the labelling server on 127.0.0.1 and return at once. The pass is the rows of `sample`
    that are pending now (every row with `force_open_ui=True`); it starts at the first of them."""
    _need_sample(sample)
    ids = {r.id for r in sample.rows if force_open_ui or not r.labels}
    handle = Handle(sample, taxonomy, ids, review=force_open_ui)
    _acquire(handle.lock)
    try:
        handle.current = handle._after(handle._scope(), "")
        request = type("Request", (_Request,), {"session": handle})
        handle.server = ThreadingHTTPServer(("127.0.0.1", port or 0), request)
        threading.Thread(target=handle.server.serve_forever, daemon=True).start()
    except BaseException:
        _release(handle.lock)
        raise
    atexit.register(handle.stop)
    return handle


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
