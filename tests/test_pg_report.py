"""The Check store summary (pg.report) and details (pg.details); hand-written expectations."""

from hunches.screens import pg


def result(**changes) -> dict:
    base = {
        "version": (0, 8, 0),
        "schema": "extensions",
        "encrypted": True,
        "type": "vector",
        "dimension": 1536,
        "rows": 30_576_342,
        "indexes": [("emb_idx", "hnsw", "vector_cosine_ops")],
        "sample": (7, "hello world"),
        "warnings": [],
        "notes": [],
        "errors": {},
    }
    return base | changes


OK = "[$success]✓ Connected[/]  [$text-muted]{}[/]"


def test_clean_success_is_one_line():
    assert pg.report(result()) == [
        OK.format("pgvector 0.8.0 · vector(1536) · ~30,576,342 rows")
    ]


def test_success_with_one_warning_puts_the_warning_first():
    got = pg.report(result(warnings=["no good [x]"]))
    assert got == [
        "[$warning]WARNING: no good \\[x][/]",
        OK.format("pgvector 0.8.0 · vector(1536) · ~30,576,342 rows"),
    ]


def test_error_has_no_connected_line():
    got = pg.report(
        result(errors={"column": 'relation "nope" does not exist'}, type=None)
    )
    assert got == ['[$error]ERROR: relation "nope" does not exist[/]']


def test_two_table_layout_warning_and_summary():
    w = "No row of the table has a matching row in the text table: check the id col."
    assert pg.report(result(warnings=[w], sample=None, rows=120)) == [
        f"[$warning]WARNING: {w}[/]",
        OK.format("pgvector 0.8.0 · vector(1536) · ~120 rows"),
    ]


def test_unknown_dimension_is_a_question_mark_and_missing_facts_are_omitted():
    assert pg.report(result(dimension=None, rows=None, version=None)) == [
        OK.format("vector(?)")
    ]
    assert pg.report(result(type=None, dimension=None, rows=None, version=None)) == [
        "[$success]✓ Connected[/]"
    ]


def test_details_is_the_old_report_without_errors_and_warnings():
    got = pg.details(
        result(
            notes=["No index: the search scans the whole table (~120 rows)."],
            warnings=["w"],
            encrypted=False,
        )
    )
    assert got == [
        "pgvector 0.8.0 in schema extensions, not encrypted",
        "column type vector, dimension 1536",
        "~30,576,342 rows (planner estimate)",
        "index emb_idx (hnsw, vector_cosine_ops)",
        "sample: 7 hello world",
        "No index: the search scans the whole table (~120 rows).",
    ]


def test_s3_check_index_summaries(monkeypatch):
    import boto3

    from hunches.screens.new_project import check_index

    class Client:
        def __init__(self, metric):
            self.metric = metric

        def get_index(self, **params):
            if self.metric == "boom":
                raise RuntimeError("no [creds]")
            return {"index": {"dimension": 1536, "distanceMetric": self.metric}}

    for metric, expected in [
        ("cosine", "[$success]✓ Connected[/]  [$text-muted]dimension 1536 · cosine[/]"),
        (
            "euclidean",
            (
                "[$warning]WARNING: distance metric is euclidean, not cosine[/]\n"
                "[$success]✓ Connected[/]  [$text-muted]dimension 1536 · euclidean[/]"
            ),
        ),
        ("boom", "[$error]ERROR: no \\[creds][/]"),
    ]:
        monkeypatch.setattr(boto3, "client", lambda *a, m=metric, **k: Client(m))
        assert check_index("b", "i", None) == expected
