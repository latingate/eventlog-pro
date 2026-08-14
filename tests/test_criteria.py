"""The filter layer, on its own — no database, no backend.

Every semantic the README promises about arguments is settled here; the
per-backend tests then check that each store honours them.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from eventlog_pro.criteria import (
    DEFAULT_QUERY_LIMIT,
    Criteria,
    build_criteria,
    normalize_order_by,
    sort_events,
)
from eventlog_pro.event import Event
from eventlog_pro.exceptions import ConfigurationError

# --- order_by ---------------------------------------------------------------


def test_a_bare_field_name_sorts_ascending():
    assert normalize_order_by("category") == (("category", "ASC"),)


def test_a_leading_minus_means_descending():
    assert normalize_order_by("-created_at") == (("created_at", "DESC"),)


def test_a_single_pair_is_one_term_not_two_fields():
    assert normalize_order_by(("category", "ASC")) == (("category", "ASC"),)


def test_a_two_field_tuple_is_two_terms():
    # ("category", "app") is not a direction, so it must read as two fields.
    assert normalize_order_by(("category", "app")) == (
        ("category", "ASC"),
        ("app", "ASC"),
    )


def test_a_sequence_may_mix_spellings_and_keeps_its_order():
    assert normalize_order_by(["category", ("created_at", "desc"), "-id"]) == (
        ("category", "ASC"),
        ("created_at", "DESC"),
        ("id", "DESC"),
    )


def test_direction_is_case_insensitive():
    assert normalize_order_by([("app", "asc")]) == (("app", "ASC"),)


def test_a_single_element_set_is_accepted():
    assert normalize_order_by({("app", "DESC")}) == (("app", "DESC"),)


def test_a_multi_element_set_is_rejected_because_it_has_no_order():
    with pytest.raises(ConfigurationError, match="set"):
        normalize_order_by({("category", "ASC"), ("created_at", "DESC")})


def test_an_unknown_sort_field_is_rejected():
    with pytest.raises(ConfigurationError, match="nope"):
        normalize_order_by("nope")


def test_a_bad_direction_is_rejected():
    with pytest.raises(ConfigurationError):
        normalize_order_by([("app", "sideways")])


def test_naming_the_same_field_twice_is_rejected():
    with pytest.raises(ConfigurationError, match="more than once"):
        normalize_order_by(["app", "-app"])


def test_giving_the_direction_twice_is_rejected():
    with pytest.raises(ConfigurationError, match="twice"):
        normalize_order_by([("-app", "DESC")])


# --- timestamps -------------------------------------------------------------


def test_a_date_created_at_covers_the_whole_utc_day():
    criteria = build_criteria(created_at=date(2026, 8, 14))
    assert criteria.created_from == datetime(2026, 8, 14, tzinfo=timezone.utc)
    assert criteria.created_to == datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert criteria.created_to_op == "<"


def test_a_datetime_created_at_matches_that_instant():
    moment = datetime(2026, 8, 14, 12, 30, tzinfo=timezone.utc)
    criteria = build_criteria(created_at=moment)
    assert criteria.created_from == criteria.created_to == moment
    assert criteria.created_to_op == "<="


def test_a_naive_datetime_is_read_as_utc():
    criteria = build_criteria(from_created_at=datetime(2026, 8, 14, 9, 0))
    assert criteria.created_from == datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)


def test_an_aware_datetime_is_converted_to_utc():
    from datetime import timedelta

    plus_two = timezone(timedelta(hours=2))
    criteria = build_criteria(from_created_at=datetime(2026, 8, 14, 11, 0, tzinfo=plus_two))
    assert criteria.created_from == datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)


def test_a_date_upper_bound_includes_the_whole_day():
    criteria = build_criteria(to_created_at=date(2026, 8, 14))
    assert criteria.created_to == datetime(2026, 8, 15, tzinfo=timezone.utc)
    assert criteria.created_to_op == "<"


def test_a_datetime_upper_bound_is_inclusive():
    moment = datetime(2026, 8, 14, 23, 59, tzinfo=timezone.utc)
    criteria = build_criteria(to_created_at=moment)
    assert criteria.created_to == moment
    assert criteria.created_to_op == "<="


def test_created_at_cannot_be_combined_with_a_range():
    with pytest.raises(TypeError, match="cannot be combined"):
        build_criteria(created_at=date(2026, 8, 14), from_created_at=date(2026, 8, 1))


def test_a_backwards_range_is_rejected():
    with pytest.raises(ConfigurationError, match="after"):
        build_criteria(from_created_at=date(2026, 8, 14), to_created_at=date(2026, 8, 1))


# --- columns ----------------------------------------------------------------


def test_none_means_not_filtered_and_empty_string_is_a_real_filter():
    assert build_criteria().equals == ()
    assert build_criteria(app="").equals == (("app", ""),)


def test_an_over_long_char_filter_is_truncated_like_the_stored_value():
    criteria = build_criteria(app="x" * 150)
    assert criteria.equals == (("app", "x" * 100),)


def test_remarks_is_not_truncated_because_the_column_is_text():
    criteria = build_criteria(remarks="y" * 150)
    assert criteria.equals == (("remarks", "y" * 150),)


def test_id_must_be_an_int():
    with pytest.raises(TypeError, match="id must be an int"):
        build_criteria(id="7")


def test_data_is_a_substring_filter_not_an_equality_one():
    criteria = build_criteria(data="INV-1234")
    assert criteria.equals == ()
    assert criteria.contains == (("data", "INV-1234"),)


def test_a_dict_passed_to_data_fails_loudly():
    # The mistake a caller reasoning from `app=` would actually make.
    with pytest.raises(TypeError, match="substring match"):
        build_criteria(data={"invoice": "INV-1234"})


# --- limit and defaults -----------------------------------------------------


def test_a_read_is_capped_by_default_and_a_delete_is_not():
    assert build_criteria().limit == DEFAULT_QUERY_LIMIT == 100
    assert build_criteria(for_delete=True).limit is None


def test_limit_none_means_unbounded():
    assert build_criteria(limit=None).limit is None


def test_limit_must_be_at_least_one():
    with pytest.raises(ConfigurationError, match="at least 1"):
        build_criteria(limit=0)


def test_limit_must_be_an_int():
    with pytest.raises(TypeError, match="limit must be"):
        build_criteria(limit="10")


def test_reads_default_to_newest_first():
    assert build_criteria().order_by == (("created_at", "DESC"), ("id", "DESC"))


def test_limited_deletes_default_to_oldest_first():
    assert build_criteria(for_delete=True, limit=10).order_by == (
        ("created_at", "ASC"),
        ("id", "ASC"),
    )


def test_an_unlimited_delete_is_not_ordered_at_all():
    assert build_criteria(for_delete=True).order_by == ()


def test_an_explicit_order_by_wins_over_both_defaults():
    assert build_criteria(order_by="app").order_by == (("app", "ASC"),)


# --- has_filters ------------------------------------------------------------


def test_limit_and_order_by_alone_do_not_count_as_filters():
    assert not build_criteria(limit=10, order_by="app", for_delete=True).has_filters


@pytest.mark.parametrize(
    "kwargs",
    [
        {"app": "api"},
        {"app": ""},
        {"id": 1},
        {"data": "INV"},
        {"from_created_at": date(2026, 8, 14)},
        {"to_created_at": date(2026, 8, 14)},
        {"created_at": date(2026, 8, 14)},
    ],
)
def test_any_real_filter_counts(kwargs):
    assert build_criteria(for_delete=True, **kwargs).has_filters


# --- in-Python evaluation (memory:// and jsonl://) --------------------------


def _event(**kwargs):
    return Event(**{"app": "api", "category": "webhook", "event_code": "OK", **kwargs})


def test_matches_applies_equality_and_substring_together():
    event = _event(app="api", data={"invoice": "INV-1234"})
    assert build_criteria(app="api", data="INV-1234").matches(event)
    assert not build_criteria(app="other", data="INV-1234").matches(event)
    assert not build_criteria(app="api", data="INV-9").matches(event)


def test_matches_is_case_sensitive_like_sqlite_and_postgresql():
    event = _event(data={"invoice": "INV-1234"})
    assert not build_criteria(data="inv-1234").matches(event)


def test_matches_honours_the_created_at_bounds():
    event = _event(created_at=datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc))
    assert build_criteria(created_at=date(2026, 8, 14)).matches(event)
    assert not build_criteria(created_at=date(2026, 8, 15)).matches(event)
    assert build_criteria(to_created_at=date(2026, 8, 14)).matches(event)
    assert not build_criteria(to_created_at=date(2026, 8, 13)).matches(event)


def test_sort_events_keeps_mixed_directions_and_priority():
    a = _event(app="b", event_code="1", id=1)
    b = _event(app="a", event_code="2", id=2)
    c = _event(app="a", event_code="1", id=3)
    ordered = sort_events([a, b, c], (("app", "ASC"), ("event_code", "DESC")))
    assert [event.id for event in ordered] == [2, 3, 1]


def test_an_empty_criteria_matches_everything():
    assert Criteria().matches(_event())
