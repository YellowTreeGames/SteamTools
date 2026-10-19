"""StoDB — central database API for SteamTools.

All callers (CLI, MCP) go through this class rather than touching the documents directly.
"""

from datetime import UTC, datetime

from pymongo import UpdateOne

from steamtools.db.connection import connect_db
from steamtools.db.models import App
from steamtools.steam_client import get_app_list as _steam_app_list
from steamtools.steam_client import get_app_list_page as _steam_app_list_page


class StoDB:
    def __init__(self) -> None:
        connect_db()

    def search_apps(self, query: str) -> list[dict]:
        """Case-insensitive name substring search, ordered by name."""
        return [{"appid": a.appid, "name": a.name} for a in App.objects(name__icontains=query).order_by("name")]

    def status(self) -> dict:
        """Returns {"total": int, "last_fetched": datetime | None}."""
        newest = App.objects.order_by("-last_seen_at").first()
        return {"total": App.objects.count(), "last_fetched": newest.last_seen_at if newest else None}

    def sync_app_list(self, count: int | None = None) -> int:
        """Upsert the apps collection from Steam's GetAppList endpoint.

        count=None does a full catalog refresh; count=N fetches one page of
        that size starting from the highest appid we already have.
        Returns the number of apps upserted.
        """
        if count is None:
            apps = _steam_app_list()
        else:
            latest = App.objects.order_by("-appid").first()
            apps = _steam_app_list_page(last_appid=latest.appid if latest else 0, max_results=count)["apps"]

        now = datetime.now(UTC)
        if apps:
            App._get_collection().bulk_write(
                [UpdateOne({"_id": a["appid"]}, {"$set": {"name": a["name"], "last_seen_at": now}}, upsert=True) for a in apps],
                ordered=False,
            )
        return len(apps)
