"""Tests for steamtools.db.staleness."""

from datetime import UTC, datetime, timedelta

import pytest

from steamtools.db.staleness import (
    _age_days,
    _parse_release_date,
    needs_refresh_details,
    needs_refresh_reviews,
)

_NOW = datetime.now(UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _days_ago(n: float) -> str:
    return _iso(_NOW - timedelta(days=n))


# ── _age_days ─────────────────────────────────────────────────────────────────


def test_age_days_timezone_aware():
    assert abs(_age_days(_days_ago(10)) - 10) < 0.01


def test_age_days_timezone_naive():
    naive = (_NOW - timedelta(days=5)).replace(tzinfo=None).isoformat()
    assert abs(_age_days(naive) - 5) < 0.01


# ── _parse_release_date ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "date_str,expected_year",
    [
        ("Jan 01, 2020", 2020),
        ("01 Jan, 2020", 2020),
        ("January 01, 2020", 2020),
        ("2020-01-01", 2020),
        ("Q1 2021", 2021),
        ("Coming 2022", 2022),
    ],
)
def test_parse_release_date_valid(date_str, expected_year):
    result = _parse_release_date(date_str)
    assert result is not None
    assert result.year == expected_year


def test_parse_release_date_empty_string():
    assert _parse_release_date("") is None


def test_parse_release_date_completely_unparseable():
    assert _parse_release_date("some garbage text") is None


def test_parse_release_date_year_zero_triggers_value_error():
    # "0000" is 4 digits but datetime(0, ...) raises ValueError → falls through to None
    assert _parse_release_date("0000") is None


# ── needs_refresh_details ─────────────────────────────────────────────────────


def test_needs_refresh_details_none_row():
    assert needs_refresh_details(None) is True


def test_needs_refresh_details_empty_dict():
    assert needs_refresh_details({}) is True


def test_needs_refresh_details_null_fetched_at():
    assert needs_refresh_details({"fetched_at": None}) is True


def test_needs_refresh_details_fresh():
    assert needs_refresh_details({"fetched_at": _days_ago(5)}) is False


def test_needs_refresh_details_stale():
    assert needs_refresh_details({"fetched_at": _days_ago(31)}) is True


# ── needs_refresh_reviews ─────────────────────────────────────────────────────


def test_needs_refresh_reviews_no_review_row():
    assert needs_refresh_reviews(None, None) is True


def test_needs_refresh_reviews_null_fetched_at():
    assert needs_refresh_reviews({"fetched_at": None}, None) is True


def test_needs_refresh_reviews_fresh_no_details():
    assert needs_refresh_reviews({"fetched_at": _days_ago(5)}, None) is False


def test_needs_refresh_reviews_stale_no_details():
    assert needs_refresh_reviews({"fetched_at": _days_ago(35)}, None) is True


def test_needs_refresh_reviews_coming_soon():
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(5)},
            {"coming_soon": 1, "release_date": None},
        )
        is False
    )


def test_needs_refresh_reviews_no_release_date():
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(5)},
            {"coming_soon": 0, "release_date": None},
        )
        is False
    )


def test_needs_refresh_reviews_unparseable_release_date():
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(5)},
            {"coming_soon": 0, "release_date": "garbage"},
        )
        is False
    )


def test_needs_refresh_reviews_recent_game_fresh():
    recent = (_NOW - timedelta(days=180)).strftime("%Y-%m-%d")
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(5)},
            {"coming_soon": 0, "release_date": recent},
        )
        is False
    )


def test_needs_refresh_reviews_recent_game_stale():
    recent = (_NOW - timedelta(days=180)).strftime("%Y-%m-%d")
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(35)},
            {"coming_soon": 0, "release_date": recent},
        )
        is True
    )


def test_needs_refresh_reviews_old_game_yearly_fresh():
    old = (_NOW - timedelta(days=400)).strftime("%Y-%m-%d")
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(200)},
            {"coming_soon": 0, "release_date": old},
        )
        is False
    )


def test_needs_refresh_reviews_old_game_yearly_stale():
    old = (_NOW - timedelta(days=400)).strftime("%Y-%m-%d")
    assert (
        needs_refresh_reviews(
            {"fetched_at": _days_ago(366)},
            {"coming_soon": 0, "release_date": old},
        )
        is True
    )
