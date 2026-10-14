from hunches.screens.search import band_rows, seed_rows


def plain(rows):
    return [r.plain for r in rows]


def test_band_rows_at_60_columns():
    # label 11, gap 2, bar column 60-26=34, gap 2, count 11 right-aligned
    counts = [1, 0, 0, 0, 1, 0, 1204]
    rows = plain(band_rows(counts, 60))
    assert rows == [
        "Similarity" + " " * 39 + " Candidates",
        "0.6–0.625  " + "  " + "█" * 1 + " " * 33 + "  " + " " * 10 + "1",
        "0.625–0.65 " + "  " + " " * 34 + "  " + " " * 10 + "0",
        "0.65–0.675 " + "  " + " " * 34 + "  " + " " * 10 + "0",
        "0.675–0.7  " + "  " + " " * 34 + "  " + " " * 10 + "0",
        "0.7–0.725  " + "  " + "█" * 1 + " " * 33 + "  " + " " * 10 + "1",
        "0.725–0.75 " + "  " + " " * 34 + "  " + " " * 10 + "0",
        "0.75+      " + "  " + "█" * 34 + "  " + " " * 6 + "1,204",
    ]
    assert {len(r) for r in rows} == {60}


def test_band_rows_bar_is_capped_at_40_cells():
    rows = plain(band_rows([0, 0, 0, 0, 0, 5, 10], 120))
    assert rows[7] == "0.75+      " + "  " + "█" * 40 + " " * 54 + "  " + " " * 9 + "10"
    assert rows[6].count("█") == 20
    assert {len(r) for r in rows} == {120}


def test_band_rows_styles():
    rows = band_rows([0, 3, 0, 0, 0, 0, 0], 60, primary="#112233")
    zero, three = rows[1], rows[2]
    styles = lambda row: {str(s.style) for s in row.spans}
    assert "bold" in styles(three) and "#112233" in styles(three)
    assert "bold" not in styles(zero) and "dim" in styles(zero)
    assert "dim" in styles(rows[0])


def test_seed_rows_at_50_columns():
    top = [("alpha", 1204), ("a very long seed phrase indeed", 6), ("b", 0)]
    # rank 3, gap, count 7, gap, bar column 14, gap, seed fills 50-27=23
    rows = plain(seed_rows(top, 50))
    assert rows == [
        "  1" + " " + "  1,204" + " " + "█" * 12 + "  " + " " + "alpha",
        "  2"
        + " "
        + "      6"
        + " "
        + "█" * 1
        + " " * 11
        + "  "
        + " "
        + "a very long seed phras…",
        "  3" + " " + "      0" + " " + " " * 12 + "  " + " " + "b",
    ]
    assert len(rows[1]) == 50


def test_seed_rows_at_120_columns_do_not_truncate_and_first_bar_is_accent():
    rows = seed_rows([("a very long seed phrase indeed", 6)], 120, accent="#aabbcc")
    assert rows[0].plain.endswith("a very long seed phrase indeed")
    assert "#aabbcc" in {str(s.style) for s in rows[0].spans}
