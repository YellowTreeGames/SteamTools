"""Staleness / refresh-policy rules for app_details and review counts."""

from datetime import UTC, datetime

_MONTHLY_DAYS = 30
_YEARLY_DAYS = 365


def _age_days(fetched_at: str) -> float:
    dt = datetime.fromisoformat(fetched_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return (datetime.now(UTC) - dt).total_seconds() / 86400


def _parse_release_date(date_str: str) -> datetime | None:
    """Parse Steam release date strings into a UTC datetime.

    Steam uses many formats ("Jan 1, 2020", "1 Jan, 2020", "2020-01-01") and
    sometimes just a year ("2021", "Q1 2021", "Coming 2022").  Falls back to
    Jan 1 of the extracted year when no full date is parseable.
    """
    if not date_str:
        return None
    for fmt in ("%b %d, %Y", "%d %b, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    for token in date_str.split():
        if token.isdigit() and len(token) == 4:
            try:
                return datetime(int(token), 1, 1, tzinfo=UTC)
            except ValueError:
                pass
    return None


def needs_refresh_details(row: dict | None) -> bool:
    """App details are stale after 30 days."""
    if not row or not row.get("fetched_at"):
        return True
    return _age_days(row["fetched_at"]) > _MONTHLY_DAYS


def needs_refresh_reviews(review_row: dict | None, details_row: dict | None) -> bool:
    """Review count refresh policy:
    - Missing → always refresh.
    - Unreleased (coming_soon=1 or no release_date) → monthly.
    - Released < 1 year ago → monthly.
    - Released >= 1 year ago → yearly.
    """
    if not review_row or not review_row.get("fetched_at"):
        return True

    age = _age_days(review_row["fetched_at"])

    if not details_row or details_row.get("coming_soon") or not details_row.get("release_date"):
        return age > _MONTHLY_DAYS

    release_dt = _parse_release_date(details_row["release_date"])
    if release_dt is None:
        return age > _MONTHLY_DAYS

    game_age = (datetime.now(UTC) - release_dt).total_seconds() / 86400
    return age > (_MONTHLY_DAYS if game_age < _YEARLY_DAYS else _YEARLY_DAYS)
