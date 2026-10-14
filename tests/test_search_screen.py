import asyncio
import json

import numpy as np
import pytest
from conftest import panel_title
from pydantic_ai import Embedder
from pydantic_ai.embeddings import EmbeddingResult, TestEmbeddingModel
from pydantic_ai.usage import RequestUsage
from textual.widgets import Button, Label, Select, Static

from hunches import candidates, files, search
from hunches.app import ConfirmScreen, HunchesApp, say
from hunches.screens.progress import LabelBar
from hunches.screens.search import SearchScreen


class StubEmbedder(Embedder):
    def __init__(self, vectors):
        super().__init__(TestEmbeddingModel("m"))
        self.vectors = vectors

    async def embed_query(self, query, *, settings=None):
        return EmbeddingResult(
            [self.vectors[query]],
            inputs=[query],
            input_type="query",
            model_name="m",
            provider_name="test",
            usage=RequestUsage(input_tokens=3),
        )


@pytest.fixture(autouse=True)
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    # cosine with [1, 0] is the first coordinate: 1.0, 0.8, 0.7, 0.62, 0.3
    vectors = [[1, 0], [0.8, 0.6], [0.7, 0.714], [0.62, 0.7846], [0.3, 0.954]]
    np.save(corpus / "vectors.npy", np.array(vectors, np.float32))
    items = [{"id": f"i{i}", "text": f"t{i}"} for i in range(5)]
    (corpus / "items.jsonl").write_text("".join(json.dumps(r) + "\n" for r in items))
    (corpus / "meta.json").write_text(json.dumps({"embedding_model": "m"}))
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir=str(corpus),
            embedding_model="m",
        )
    )
    files.write_text("seeds.csv", "seed\nalpha\n")
    files.write_state(files.State(seeds_approved=True))


async def open_search(pilot, app):
    await pilot.pause()
    app.goto_stage(2)
    await pilot.pause()
    assert isinstance(app.screen, SearchScreen)
    return app.screen


async def run(pilot, app, screen):
    await pilot.press("r")
    await app.workers.wait_for_complete()
    await pilot.pause()


def band_pairs(screen):
    """[(band name, count text)] from the bands Static: first and last word of each line, header skipped."""
    lines = str(screen.query_one("#bands", Static).content).splitlines()[1:]
    return [(line.split()[0], line.split()[-1]) for line in lines]


def centred(widget, area):
    """Widget's middle is within one cell across and one row down of the area's middle."""
    r, a = widget.region, area.region
    return (
        abs((r.x + r.width / 2) - (a.x + a.width / 2)) <= 1
        and abs((r.y + r.height / 2) - (a.y + a.height / 2)) <= 1
    )


def label(screen):
    return str(screen.query_one("#run", Button).label)


def status(screen):
    return str(screen.query_one("#status", Label).render())


def write_candidates(n, seed="alpha", sim=0.7):
    files.write_jsonl(
        "candidates.jsonl",
        [
            {"id": str(i), "text": "t", "max_similarity": sim, "best_seed": seed}
            for i in range(n)
        ],
    )


async def test_band_bars_match_counts():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        # similarities 1.0 (0.75+), 0.8 (0.75+), 0.7 (0.7-0.725), 0.62 (0.6-0.625)
        assert band_pairs(screen) == [
            ("0.6–0.625", "1"),
            ("0.625–0.65", "0"),
            ("0.65–0.675", "0"),
            ("0.675–0.7", "0"),
            ("0.7–0.725", "1"),
            ("0.725–0.75", "0"),
            ("0.75+", "2"),
        ]
        text = str(screen.query_one("#bands", Static).content)
        assert "At or above" not in text and "Total" not in text
        assert text.splitlines()[0].split() == ["Similarity", "Candidates"]
        # the largest band (count 2) has the longest bar; empty bands have none
        bars = [line.count("█") for line in text.splitlines()[1:]]
        assert bars[6] == max(bars) > bars[0] == bars[4] > 0 == bars[1]
        assert panel_title(screen.query_one("#bands-panel")) == (
            "Candidates by similarity",
            "4 candidates",
        )
        top = str(screen.query_one("#seeds", Static).content).split()
        assert (top[0], top[1], top[-1]) == ("1", "4", "alpha")
        assert not screen.query_one("#warning").display


async def test_capped_warning_with_stubbed_s3(monkeypatch):
    class FakeS3:
        def query_vectors(self, **kw):
            v = {"key": "a", "distance": 0.1, "metadata": {"text": "text a"}}
            return {"vectors": [v, {**v, "key": "b"}]}

    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            backend="s3",
            s3_bucket="b",
            s3_index="i",
            embedding_model="m",
        )
    )
    monkeypatch.setattr("boto3.client", lambda name, **kw: FakeS3())
    monkeypatch.setattr(search, "S3_TOP_K", 2)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        assert str(screen.query_one("#warning", Label).render()) == (
            "WARNING: S3 returned its cap of 2 hits for at least one seed; "
            "only the 2 highest-scoring hits are kept."
        )
        assert panel_title(screen.query_one("#bands-panel"))[1] == "2 candidates"


def test_cap_warning_formats_thousands():
    assert SearchScreen.cap_warning("s3", 10_000) == (
        "WARNING: S3 returned its cap of 10,000 hits for at least one seed; "
        "only the 10,000 highest-scoring hits are kept."
    )
    assert SearchScreen.cap_warning("pgvector", 10_000) == (
        "WARNING: pgvector returned its cap of 10,000 hits for at least one seed; "
        "only the 10,000 highest-scoring hits are kept."
    )


async def test_embedding_model_mismatch_is_shown():
    files.write_config(
        files.Config(
            assistant_model="anthropic:claude-sonnet-5-5",
            classifier_model="anthropic:claude-haiku-4-5",
            corpus_dir="corpus",
            embedding_model="other-model",
        )
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        error = str(screen.query_one("#error", Label).render())
        assert "mismatch" in error and "embedding_model" in error
        assert screen.query_one("#error").has_class("error")
        assert "\nFix:" in error
        assert screen.has_class("-first") and not screen.query_one("#results").display
        assert screen.query_one("#error").region.y > screen.query_one("#run").region.y
        assert app.is_running


async def test_never_run_shows_only_the_centred_run_block():
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        assert label(screen) == "Run search  r"
        button = screen.query_one("#run", Button)
        assert button.variant == "primary" and not button.disabled
        assert button.size.height == 1
        assert not status(screen)
        assert screen.has_class("-first")
        assert not screen.query_one("#results").display
        assert centred(button, screen.query_one("#main"))
        assert not screen.query_one("#progress").display
        assert not screen.query_one("#pool").display
        for id_ in ("#warning", "#error"):
            assert not screen.query_one(id_).display
        assert not app.screen.query("#done")


async def test_not_approved_disables_button_and_ignores_r():
    files.write_state(files.State())
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        assert screen.query_one("#run", Button).disabled
        assert status(screen) == "Seeds are not approved yet."
        assert screen.query_one("#status").has_class("warn")
        assert not screen.query_one("#results").display
        run_button, note = screen.query_one("#run"), screen.query_one("#status")
        assert note.region.y == run_button.region.y + run_button.region.height + 1
        assert (
            abs(
                (note.region.x + note.region.width / 2)
                - (run_button.region.x + run_button.region.width / 2)
            )
            <= 1
        )
        await pilot.press("r")
        await pilot.pause()
        assert not screen.searching
        assert isinstance(app.screen, SearchScreen)


async def test_running_shows_progress_bar_and_disables_button():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        embedder = StubEmbedder({"alpha": [1, 0]})
        seen = []
        original = screen.on_progress

        def spy(done, total, seed):
            original(done, total, seed)
            bar = screen.query_one("#progress", LabelBar)
            seen.append((bar.total, bar.value, bar.label, label(screen)))

        screen.on_progress = spy
        screen.embedder = embedder
        files.write_text("seeds.csv", "seed\nalpha\n")
        screen.action_run()  # synchronous: the worker has not run yet
        button = screen.query_one("#run", Button)
        assert button.disabled and label(screen) == "Searching…"
        bar = screen.query_one("#progress", LabelBar)
        assert bar.display and (bar.total, bar.value, bar.label) == (1, 0, "0/1")
        assert bar.align == "left"
        assert not status(screen)
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert seen == [(1, 1, "1/1  alpha", "Searching…")]
        assert not bar.display
        assert not button.disabled and label(screen) == "Rerun search  r"
        assert not screen.has_class("-first") and screen.query_one("#results").display
        assert not screen.query_one("#results").has_class("-inactive")


async def test_rerun_with_unchanged_seeds_asks_first():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        assert label(screen) == "Rerun search  r"
        assert not status(screen)
        before = files.read_text("candidates.meta.json")
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, ConfirmScreen)
        assert app.screen.question == (
            "You've already run the searches, and haven't changed the seed "
            "candidates. Depending on the size of the corpus, this can take a long "
            "time. Are you sure you want to rerun searches?"
        )
        await pilot.click("#no")  # cancel: nothing runs
        await pilot.pause()
        assert not screen.searching
        assert files.read_text("candidates.meta.json") == before
        await pilot.press("r")
        await pilot.pause()
        await pilot.press("enter")  # confirm
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert files.read_text("candidates.meta.json") != before
        assert isinstance(app.screen, SearchScreen)


async def test_changed_seeds_run_without_confirmation():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0], "beta": [0, 1]})
        await run(pilot, app, screen)
        files.write_text("seeds.csv", "seed\nalpha\nbeta\n")
        screen.refresh_state()
        assert label(screen) == "Run search  r"
        assert status(screen) == "Seeds changed, rerun needed"
        assert screen.query_one("#status").has_class("warn")
        await pilot.press("r")
        await pilot.pause()
        assert isinstance(app.screen, SearchScreen)  # no ConfirmScreen
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert label(screen) == "Rerun search  r"
        assert not status(screen)


async def test_old_project_without_meta_counts_as_unchanged():
    write_candidates(3)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        assert label(screen) == "Rerun search  r"
        assert not status(screen)
        assert not screen.query_one("#results").has_class("-inactive")


async def test_counts_use_thousands_separators():
    write_candidates(1204)
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        assert band_pairs(screen)[4] == ("0.7–0.725", "1,204")
        assert panel_title(screen.query_one("#bands-panel"))[1] == "1,204 candidates"
        assert "1,204" in str(screen.query_one("#seeds", Static).content)


async def test_grids_follow_the_panel_width():
    write_candidates(10)
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        width = screen.query_one("#bands").size.width
        lines = str(screen.query_one("#bands", Static).content).splitlines()
        assert {len(line) for line in lines} == {width}
        await pilot.resize_terminal(140, 36)
        await pilot.pause()
        wider = screen.query_one("#bands").size.width
        assert wider > width
        lines = str(screen.query_one("#bands", Static).content).splitlines()
        assert {len(line) for line in lines} == {wider}
        assert max(line.count("█") for line in lines) == 40


async def test_blank_row_between_the_panels():
    write_candidates(10)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        bands, seeds = (
            screen.query_one("#bands-panel"),
            screen.query_one("#seeds-panel"),
        )
        assert seeds.region.y == bands.region.y + bands.region.height + 1


async def test_first_run_shows_progress_centred_then_results():
    gate = asyncio.Event()

    class Slow(StubEmbedder):
        async def embed_query(self, query, *, settings=None):
            await gate.wait()
            return await super().embed_query(query, settings=settings)

    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = Slow({"alpha": [1, 0]})
        screen.action_run()
        await pilot.pause()
        assert screen.has_class("-first") and not screen.query_one("#results").display
        bar = screen.query_one("#progress", LabelBar)
        assert bar.display and bar.label == "0/1"
        assert label(screen) == "Searching…" and screen.query_one("#run").disabled
        assert centred(screen.query_one("#top"), screen.query_one("#main"))
        gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not screen.has_class("-first")
        assert screen.query_one("#results").display
        assert screen.query_one("#top").display and screen.query_one("#run").display
        assert band_pairs(screen)[-1] == ("0.75+", "2")


async def test_failed_and_stopped_first_runs_keep_the_centred_block():
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({})  # no vector for the seed: the run fails
        await run(pilot, app, screen)
        error = screen.query_one("#error", Label)
        assert error.display and "Search failed" in str(error.render())
        assert screen.has_class("-first") and label(screen) == "Run search  r"
        assert error.region.y > screen.query_one("#run").region.y
        assert error.styles.text_align == "center"
        assert not screen.query_one("#results").display
        say(error, "")
        say(screen.query_one("#warning", Label), "Search stopped.")
        await pilot.pause()
        warning = screen.query_one("#warning", Label)
        assert warning.display and warning.styles.text_align == "center"
        assert warning.region.y > screen.query_one("#run").region.y


async def test_opening_a_project_with_candidates_goes_straight_to_results():
    write_candidates(5)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        assert not screen.has_class("-first") and screen.query_one("#results").display
        assert screen.query_one("#run").display


async def test_stale_seeds_still_show_results_and_the_note():
    write_candidates(5)
    files.write_text("candidates.meta.json", '{"seeds_digest": "x"}')
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        assert status(screen) == "Seeds changed, rerun needed"
        assert screen.query_one("#results").display
        assert not screen.has_class("-first")


async def test_rerun_dims_the_results():
    write_candidates(5)
    files.write_text("candidates.meta.json", '{"seeds_digest": "x"}')
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        screen.start()
        assert screen.query_one("#results").has_class("-inactive")
        assert not screen.has_class("-first") and screen.query_one("#progress").display
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not screen.query_one("#results").has_class("-inactive")


async def test_top_seeds_threshold_select():
    rows = [
        {"id": str(i), "text": "t", "max_similarity": s, "best_seed": b}
        for i, (s, b) in enumerate(
            [(0.61, "A"), (0.62, "A"), (0.63, "A"), (0.7, "B"), (0.8, "B")]
        )
    ]
    files.write_jsonl("candidates.jsonl", rows)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        select = screen.query_one("#threshold", Select)
        assert select.value == candidates.FLOOR
        assert [v for _, v in select._options] == candidates.BANDS
        assert [str(p) for p, _ in select._options] == [
            f"{b:g}" for b in candidates.BANDS
        ]
        lines = str(screen.query_one("#seeds", Static).content).splitlines()
        assert [(ln.split()[0], ln.split()[1], ln.split()[-1]) for ln in lines] == [
            ("1", "3", "A"),
            ("2", "2", "B"),
        ]
        select.value = 0.7
        await pilot.pause()
        lines = str(screen.query_one("#seeds", Static).content).splitlines()
        assert [(ln.split()[0], ln.split()[1], ln.split()[-1]) for ln in lines] == [
            ("1", "2", "B")
        ]
        assert (
            "similarity at or above" in panel_title(screen.query_one("#seeds-panel"))[1]
        )


async def test_pool_warning_banner():
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        pool = screen.query_one("#pool")
        assert not pool.display  # no results
        write_candidates(99)
        screen.refresh_state()
        assert pool.display and pool.has_class("banner") and pool.has_class("-stale")
        assert str(pool.render()) == (
            "Only 99 candidates found. Labelling needs at least 100: 50 dev and 50 test."
        )
        write_candidates(100)
        screen.refresh_state()
        assert not pool.display
        write_candidates(3)
        screen.refresh_state()
        assert pool.display
        # hidden while a search is running
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        screen.start()
        assert not pool.display
        await app.workers.wait_for_complete()
        await pilot.pause()
        # the stub corpus yields 4 candidates: shown again with that number
        assert pool.display and "Only 4 candidates found." in str(pool.render())


def gold_rows(split, ids):
    return [
        files.GoldRow(id=i, text=f"row {i}", labels=["a"], split=split) for i in ids
    ]


async def test_search_counts_gold_rows_that_left_the_pool():
    files.write_jsonl(
        "candidates.jsonl",
        [
            {
                "id": f"i{i}",
                "text": f"t{i}",
                "max_similarity": 0.7,
                "best_seed": "alpha",
            }
            for i in range(5)
        ],
    )
    files.write_gold(gold_rows("dev", ["i0", "i1", "gone1", "gone2", "gone3"]))
    app = HunchesApp()
    async with app.run_test() as pilot:
        await open_search(pilot, app)
        note = app.screen.query_one("#gold-orphans", Static)
        assert note.display
        assert str(note.render()) == (
            "3 of your 5 dev items are no longer in the candidate pool. "
            "Review them on the Gold screen (stage 4)."
        )


async def test_search_adds_a_sentence_for_the_test_split_and_stays_quiet_without_orphans():
    files.write_jsonl(
        "candidates.jsonl",
        [
            {
                "id": f"i{i}",
                "text": f"t{i}",
                "max_similarity": 0.7,
                "best_seed": "alpha",
            }
            for i in range(5)
        ],
    )
    files.write_gold(
        gold_rows("dev", ["i0", "gone1"]) + gold_rows("test", ["i1", "i2", "gone2"])
    )
    app = HunchesApp()
    async with app.run_test() as pilot:
        await open_search(pilot, app)
        note = app.screen.query_one("#gold-orphans", Static)
        assert str(note.render()) == (
            "1 of your 2 dev items are no longer in the candidate pool. "
            "Review them on the Gold screen (stage 4). "
            "1 of your 3 test items are no longer in the pool."
        )
        files.write_gold(gold_rows("dev", ["i0"]) + gold_rows("test", ["i1", "gone"]))
        assert isinstance(app.screen, SearchScreen)
        app.screen.refresh_state()
        assert str(note.render()) == (
            "1 of your 2 test items are no longer in the candidate pool. "
            "Review them on the Gold screen (stage 6)."
        )
        files.write_gold(gold_rows("dev", ["i0"]))
        assert isinstance(app.screen, SearchScreen)
        app.screen.refresh_state()
        assert not note.display


# ---- pgvector (task 05 search_pg_exact is stubbed; nothing touches a database)


def use_pgvector(mode=None):
    config = files.read_config()
    files.write_config(
        config.model_copy(
            update={"backend": "pgvector", "pg_table": "t", "pg_search": mode}
        )
    )


def hit(i, sim):
    return (f"i{i}", f"t{i}", sim)


async def test_cap_warning_names_pgvector(monkeypatch):
    use_pgvector()
    monkeypatch.setattr(
        candidates,
        "search_pg_exact",
        lambda vectors, floor, progress=None, stop=None: ([[hit(0, 0.9)]], True),
    )
    app = HunchesApp()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        assert str(screen.query_one("#warning", Label).render()) == (
            "WARNING: pgvector returned its cap of 10,000 hits for at least one seed; "
            "only the 10,000 highest-scoring hits are kept."
        )


APPROXIMATE = (
    "WARNING: APPROXIMATE pgvector search; the index may hide hits above the floor. "
    "Switch to exact in Project settings for a complete pool."
)


@pytest.mark.parametrize(
    ("mode", "shown"), [("index", True), ("exact", False), (None, False)]
)
async def test_approximate_warning_only_for_index_mode(mode, shown):
    use_pgvector(mode)
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        banner = screen.query_one("#approximate", Static)
        assert banner.display is shown
        if shown:
            assert str(banner.content) == APPROXIMATE


async def test_approximate_warning_is_absent_for_local_and_stays_after_a_run(
    monkeypatch,
):
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        assert not screen.query_one("#approximate").display
    use_pgvector("index")
    monkeypatch.setattr(candidates, "search", lambda vector, floor: ([], False))
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        assert screen.query_one("#approximate").display


def gated_search(monkeypatch, gate, outcome):
    """search_pg_exact stub: reports 1,234 rows, waits for `gate`, then returns `outcome`."""

    def stub(vectors, floor, progress=None, stop=None):
        assert progress
        progress(1234, 0, "")
        while not gate.wait(0.01):
            if stop and stop.stopped:
                raise search.SearchCancelled
        return outcome, False

    monkeypatch.setattr(candidates, "search_pg_exact", stub)


async def test_unknown_total_shows_elapsed_and_rows_at_80x24(monkeypatch):
    import threading

    use_pgvector()
    gate = threading.Event()
    gated_search(monkeypatch, gate, [[hit(0, 0.9)]])
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        screen.action_run()
        await pilot.pause(0.6)
        bar = screen.query_one("#progress", LabelBar)
        assert bar.display and bar.total == 0
        assert bar.label.startswith("0s  1,234 rows") or bar.label.startswith(
            "1s  1,234 rows"
        )
        assert str(bar.render().plain).startswith(bar.label)
        assert screen.query_one("#stop", Button).display
        assert bar.region.width > 0 and screen.region.contains_region(bar.region)
        gate.set()
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not bar.display and not screen.query_one("#stop", Button).display


async def test_stop_ends_the_run_and_clears_searching(monkeypatch):
    import threading

    use_pgvector()
    gated_search(monkeypatch, threading.Event(), [])
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        screen.action_run()
        await pilot.pause(0.3)
        assert screen.searching
        stop = screen.query_one("#stop", Button)
        assert str(stop.label) == "Stop  x"
        await pilot.press("x")
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not screen.searching and not stop.display
        assert not screen.query_one("#run", Button).disabled
        assert str(screen.query_one("#warning", Label).render()) == "Search stopped."
        assert not screen.query_one("#error").display
        assert files.read_text("candidates.jsonl") is None


async def test_stop_button_click_stops_too(monkeypatch):
    import threading

    use_pgvector()
    gated_search(monkeypatch, threading.Event(), [])
    app = HunchesApp()
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        screen.action_run()
        await pilot.pause(0.3)
        await pilot.click("#stop", offset=(2, 0))
        await app.workers.wait_for_complete()
        await pilot.pause()
        assert not screen.searching


async def test_connection_error_in_the_error_line_has_no_password(monkeypatch):
    import sys
    import types

    url = "postgresql://alice:hunter2pw@db.example.com:5432/mydb"
    monkeypatch.setenv("HUNCHES_PG_URL", url)
    fake = types.ModuleType("psycopg")

    def connect(*a, **k):
        raise OSError(f"could not connect to {url}: password hunter2pw refused")

    fake.connect = connect  # ty: ignore[unresolved-attribute]
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    use_pgvector()
    app = HunchesApp()
    async with app.run_test(size=(80, 24)) as pilot:
        screen = await open_search(pilot, app)
        screen.embedder = StubEmbedder({"alpha": [1, 0]})
        await run(pilot, app, screen)
        error = screen.query_one("#error", Label)
        text = str(error.render())
        assert error.display and text.startswith(
            "Search failed: could not connect to ***"
        )
        assert "hunter2pw" not in text and "alice" not in text
        assert not screen.searching
