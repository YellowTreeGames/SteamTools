"""Staleness / refresh-policy rules for app_details and app_review_summary."""

from datetime import UTC, datetime

_MONTHLY_DAYS = 30
_WEEKLY_DAYS = 7


def _age_days(fetched_at: str) -> float:
    dt = datetime.fromisoformat(fetched_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 86400


def needs_refresh_details(row: dict | None) -> bool:
    """App details are stale after 30 days."""
    if not row or not row.get("fetched_at"):
        return True
    return _age_days(row["fetched_at"]) > _MONTHLY_DAYS


def needs_refresh_review_summary(row: dict | None) -> bool:
    """Review summary is stale after 7 days."""
    if not row or not row.get("fetched_at"):
        return True
    return _age_days(row["fetched_at"]) > _WEEKLY_DAYS
