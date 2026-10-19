"""Unit tests for steamtools.db.store — Steam calls mocked, Mongo backed by mongomock."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest

from steamtools.db.models import App
from steamtools.db.store import StoDB


@pytest.fixture()
def db(mongo):
    return StoDB()


def _seed(*apps: tuple[int, str]) -> None:
    now = datetime.now(UTC)
    for appid, name in apps:
        App(appid=appid, name=name, last_seen_at=now).save()


class TestSyncAppList:
    def test_full_refresh_inserts_all_apps(self, db):
        apps = [{"appid": 1, "name": "A"}, {"appid": 2, "name": "B"}]
        with patch("steamtools.db.store._steam_app_list", return_value=apps):
            n = db.sync_app_list()
        assert n == 2
        assert App.objects.count() == 2

    def test_upsert_updates_existing_name_without_duplicating(self, db):
        _seed((1, "Old"))
        with patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "New"}]):
            db.sync_app_list()
        assert App.objects.count() == 1
        assert App.objects.get(appid=1).name == "New"

    def test_upsert_refreshes_last_seen_at(self, db):
        App(appid=1, name="A", last_seen_at=datetime(2020, 1, 1, tzinfo=UTC)).save()
        with patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "A"}]):
            db.sync_app_list()
        assert App.objects.get(appid=1).last_seen_at.year > 2020

    def test_empty_catalog_returns_zero_and_writes_nothing(self, db):
        with patch("steamtools.db.store._steam_app_list", return_value=[]):
            n = db.sync_app_list()
        assert n == 0
        assert App.objects.count() == 0

    def test_count_pages_from_highest_stored_appid(self, db):
        _seed((10, "A"), (50, "B"))
        with patch("steamtools.db.store._steam_app_list_page", return_value={"apps": [{"appid": 60, "name": "C"}]}) as page:
            n = db.sync_app_list(count=25)
        assert n == 1
        page.assert_called_once_with(last_appid=50, max_results=25)
        assert App.objects.count() == 3

    def test_count_with_empty_collection_starts_from_zero(self, db):
        with patch("steamtools.db.store._steam_app_list_page", return_value={"apps": []}) as page:
            db.sync_app_list(count=10)
        page.assert_called_once_with(last_appid=0, max_results=10)


class TestSearchApps:
    def test_matches_substring_case_insensitively_in_binary_name_order(self, db):
        _seed((1, "Half-Life"), (2, "Portal"), (3, "half dome"))
        assert [a["appid"] for a in db.search_apps("HALF")] == [1, 3]

    def test_results_ordered_by_name(self, db):
        _seed((1, "Zebra"), (2, "Apple"))
        assert [a["name"] for a in db.search_apps("e")] == ["Apple", "Zebra"]

    def test_regex_metacharacters_are_literal(self, db):
        _seed((1, "Game (2024)"), (2, "Game 2024"))
        assert [a["appid"] for a in db.search_apps("(2024)")] == [1]

    def test_no_match_returns_empty_list(self, db):
        _seed((1, "A"))
        assert db.search_apps("zzz") == []

    def test_result_shape(self, db):
        _seed((7, "Seven"))
        assert db.search_apps("Seven") == [{"appid": 7, "name": "Seven"}]


class TestStatus:
    def test_empty_collection(self, db):
        assert db.status() == {"total": 0, "last_fetched": None}

    def test_reports_total_and_newest_last_seen(self, db):
        App(appid=1, name="A", last_seen_at=datetime(2024, 1, 1, tzinfo=UTC)).save()
        App(appid=2, name="B", last_seen_at=datetime(2025, 6, 1, tzinfo=UTC)).save()
        s = db.status()
        assert s["total"] == 2
        assert s["last_fetched"].year == 2025
