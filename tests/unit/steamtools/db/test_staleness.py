"""Unit tests for steamtools.db.staleness."""

from datetime import UTC, datetime, timedelta

from steamtools.db.staleness import needs_refresh_details, needs_refresh_review_summary


def test_none_is_stale():
    assert needs_refresh_details(None) is True


def test_empty_dict_is_stale():
    assert needs_refresh_details({}) is True


def test_missing_fetched_at_is_stale():
    assert needs_refresh_details({"appid": 1, "name": "Test"}) is True


def test_old_row_is_stale():
    old = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    assert needs_refresh_details({"fetched_at": old}) is True


def test_fresh_row_is_not_stale():
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert needs_refresh_details({"fetched_at": recent}) is False


def test_boundary_just_under_30_days_not_stale():
    just_under = (datetime.now(UTC) - timedelta(days=29, hours=23)).isoformat()
    assert needs_refresh_details({"fetched_at": just_under}) is False


def test_boundary_just_over_30_days_is_stale():
    just_over = (datetime.now(UTC) - timedelta(days=30, hours=1)).isoformat()
    assert needs_refresh_details({"fetched_at": just_over}) is True


def test_naive_datetime_treated_as_utc_stale():
    # Naive datetimes (no tz) are treated as UTC; an old naive date should be stale.
    old_naive = (datetime.now() - timedelta(days=31)).isoformat()
    assert needs_refresh_details({"fetched_at": old_naive}) is True


def test_naive_fresh_datetime_not_stale():
    recent_naive = (datetime.now() - timedelta(days=1)).isoformat()
    assert needs_refresh_details({"fetched_at": recent_naive}) is False


class TestNeedsRefreshReviewSummary:
    def test_none_is_stale(self):
        assert needs_refresh_review_summary(None) is True

    def test_empty_dict_is_stale(self):
        assert needs_refresh_review_summary({}) is True

    def test_missing_fetched_at_is_stale(self):
        assert needs_refresh_review_summary({"appid": 1}) is True

    def test_fresh_row_is_not_stale(self):
        recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        assert needs_refresh_review_summary({"fetched_at": recent}) is False

    def test_old_row_is_stale(self):
        old = (datetime.now(UTC) - timedelta(days=8)).isoformat()
        assert needs_refresh_review_summary({"fetched_at": old}) is True

    def test_boundary_just_under_7_days_not_stale(self):
        just_under = (datetime.now(UTC) - timedelta(days=6, hours=23)).isoformat()
        assert needs_refresh_review_summary({"fetched_at": just_under}) is False

    def test_boundary_just_over_7_days_is_stale(self):
        just_over = (datetime.now(UTC) - timedelta(days=7, hours=1)).isoformat()
        assert needs_refresh_review_summary({"fetched_at": just_over}) is True
