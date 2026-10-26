from hunches.models import price_label


def test_price_label_plain_model():
    assert (
        price_label("anthropic:claude-haiku-4-5")
        == "$1.00 in / $5.00 out per 1M tokens"
    )


def test_price_label_matches_by_prefix_rule():
    # the snapshot has no claude-sonnet-5-5 id; the claude-sonnet-5* rule covers it
    assert (
        price_label("anthropic:claude-sonnet-5-5")
        == "$2.00 in / $10.00 out per 1M tokens"
    )


def test_price_label_tiered_names_the_threshold_in_words():
    assert price_label("openai:gpt-6-sol") == (
        "$2.00 in / $10.00 out per 1M tokens (higher above 272K prompt tokens)"
    )


def test_price_label_embedding_has_input_price_only():
    assert price_label("openai:text-embedding-3-small") == "$0.02 in per 1M tokens"


def test_price_label_unknown_is_never_zero():
    assert price_label("openai:no-such-model") == "no price: cost will show ?"
    assert price_label("nonsense") == "no price: cost will show ?"


def test_recommended_models_exist_in_pydantic_ai_known_lists():
    # doubles as the "re-verify the recommended IDs" check from spec 002
    from hunches.models import known_models
    from hunches.system import RECOMMENDED

    known = known_models()
    for rec in RECOMMENDED.values():
        assert rec["assistant"] in known
        assert rec["classifier"] in known


def test_embedding_list_holds_openai_small():
    from hunches.models import known_models

    assert "openai:text-embedding-3-small" in known_models(embedding=True)


def test_snapshot_date_is_the_library_timestamp():
    from genai_prices import data_snapshot

    from hunches.models import snapshot_date

    stamp = data_snapshot.get_snapshot().timestamp
    assert snapshot_date() == f"{stamp.year:04d}-{stamp.month:02d}-{stamp.day:02d}"
