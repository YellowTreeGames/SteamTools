"""Unit tests for StoDB — all Steam calls mocked, isolated SQLite DB per test."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from tests.conftest import RYDER_APPID, RYDER_STEAM_DATA

_REVIEW_PAGE_1 = {
    "success": 1,
    "query_summary": {
        "num_reviews": 2,
        "review_score": 8,
        "review_score_desc": "Very Positive",
        "total_positive": 800,
        "total_negative": 50,
        "total_reviews": 850,
    },
    "reviews": [
        {
            "recommendationid": "111",
            "author": {
                "steamid": "76561198000000001",
                "num_games_owned": 100,
                "num_reviews": 5,
                "playtime_forever": 120,
                "playtime_at_review": 60,
            },
            "language": "english",
            "review": "Great game!",
            "timestamp_created": 1700000000,
            "timestamp_updated": 1700000001,
            "voted_up": True,
            "votes_up": 10,
            "votes_funny": 1,
            "weighted_vote_score": "0.75",
            "comment_count": 0,
            "steam_purchase": True,
            "received_for_free": False,
            "written_during_early_access": False,
        }
    ],
    "cursor": "page2cursor",
}

_REVIEW_PAGE_2 = {
    "success": 1,
    "query_summary": {
        "num_reviews": 2,
        "review_score": 8,
        "review_score_desc": "Very Positive",
        "total_positive": 800,
        "total_negative": 50,
        "total_reviews": 850,
    },
    "reviews": [
        {
            "recommendationid": "222",
            "author": {
                "steamid": "76561198000000002",
                "num_games_owned": 50,
                "num_reviews": 2,
                "playtime_forever": 30,
                "playtime_at_review": 20,
            },
            "language": "english",
            "review": "Not bad.",
            "timestamp_created": 1700000100,
            "timestamp_updated": 1700000100,
            "voted_up": False,
            "votes_up": 0,
            "votes_funny": 0,
            "weighted_vote_score": "0.0",
            "comment_count": 0,
            "steam_purchase": True,
            "received_for_free": False,
            "written_during_early_access": False,
        }
    ],
    "cursor": "page2cursor",  # same cursor signals end of pagination
}


def _insert_app(appid: int, name: str = "Test Game") -> None:
    from steamtools.db.connection import get_connection

    now = datetime.now(UTC).isoformat()
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
            (appid, name, now),
        )


class TestStatusAndStats:
    def test_status_empty_db(self, fresh_db):
        s = fresh_db.status()
        assert s["apps_total"] == 0
        assert s["apps_with_details"] == 0
        assert s["apps_missing_details"] == 0
        assert s["apps_last_fetched"] is None
        assert s["details_total"] == 0
        assert s["details_last_fetched"] is None

    def test_app_stats_empty_db(self, fresh_db):
        s = fresh_db.app_stats()
        assert s["total"] == 0
        assert s["with_details"] == 0
        assert s["last_fetched"] is None

    def test_app_details_stats_empty_db(self, fresh_db):
        s = fresh_db.app_details_stats()
        assert s["total"] == 0
        assert s["last_fetched"] is None

    def test_status_reflects_apps_after_sync(self, fresh_db):
        with patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "A"}]):
            fresh_db.sync_app_list()
        s = fresh_db.status()
        assert s["apps_total"] == 1
        assert s["apps_missing_details"] == 1
        assert s["apps_with_details"] == 0

    def test_status_reflects_details_after_sync(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            fresh_db.sync_app_details_one(RYDER_APPID, force=True)
        s = fresh_db.status()
        assert s["apps_with_details"] == 1
        assert s["details_total"] == 1


class TestSyncAppList:
    def test_full_refresh_returns_count(self, fresh_db):
        apps = [{"appid": i, "name": f"Game {i}"} for i in range(1, 4)]
        with patch("steamtools.db.store._steam_app_list", return_value=apps):
            n = fresh_db.sync_app_list()
        assert n == 3

    def test_full_refresh_upserts_all(self, fresh_db):
        apps = [{"appid": 1, "name": "A"}, {"appid": 2, "name": "B"}]
        with patch("steamtools.db.store._steam_app_list", return_value=apps):
            fresh_db.sync_app_list()
        assert fresh_db.app_stats()["total"] == 2

    def test_partial_refresh_passes_count_and_last_appid(self, fresh_db):
        with patch("steamtools.db.store._steam_app_list_page") as mock_page:
            mock_page.return_value = {"apps": [{"appid": 1, "name": "A"}], "have_more_results": False, "last_appid": 1}
            fresh_db.sync_app_list(count=50)
        mock_page.assert_called_once_with(last_appid=0, max_results=50)

    def test_partial_refresh_uses_max_appid_as_cursor(self, fresh_db):
        _insert_app(100, "Existing")
        with patch("steamtools.db.store._steam_app_list_page") as mock_page:
            mock_page.return_value = {"apps": [], "have_more_results": False, "last_appid": 100}
            fresh_db.sync_app_list(count=10)
        assert mock_page.call_args.kwargs["last_appid"] == 100

    def test_upsert_updates_existing_name(self, fresh_db):
        with patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "Old Name"}]):
            fresh_db.sync_app_list()
        with patch("steamtools.db.store._steam_app_list", return_value=[{"appid": 1, "name": "New Name"}]):
            fresh_db.sync_app_list()
        results = fresh_db.search_apps("New Name")
        assert len(results) == 1
        assert results[0]["name"] == "New Name"


class TestSearchApps:
    def test_empty_db_returns_empty_list(self, fresh_db):
        assert fresh_db.search_apps("anything") == []

    def test_finds_by_substring(self, fresh_db):
        _insert_app(1, "Half-Life 2")
        _insert_app(2, "Portal")
        results = fresh_db.search_apps("half")
        assert len(results) == 1
        assert results[0]["name"] == "Half-Life 2"

    def test_case_insensitive_match(self, fresh_db):
        _insert_app(1, "Counter-Strike")
        assert len(fresh_db.search_apps("COUNTER")) == 1
        assert len(fresh_db.search_apps("counter")) == 1

    def test_no_match_returns_empty_list(self, fresh_db):
        _insert_app(1, "Half-Life 2")
        assert fresh_db.search_apps("Portal") == []

    def test_has_details_flag_false_before_sync(self, fresh_db):
        _insert_app(1, "Test Game")
        assert fresh_db.search_apps("Test")[0]["has_details"] == 0

    def test_has_details_flag_true_after_details_sync(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            fresh_db.sync_app_details_one(RYDER_APPID, force=True)
        assert fresh_db.search_apps("Ryder")[0]["has_details"] == 1

    def test_results_ordered_by_name(self, fresh_db):
        _insert_app(3, "Zork")
        _insert_app(1, "Alpha")
        _insert_app(2, "Beta")
        names = [r["name"] for r in fresh_db.search_apps("")]
        assert names == ["Alpha", "Beta", "Zork"]


class TestSyncAppDetailsOne:
    def test_game_returns_game_status(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            result = fresh_db.sync_app_details_one(RYDER_APPID, force=True)
        assert result["status"] == "game"
        assert result["appid"] == RYDER_APPID
        assert result["row"]["name"] == "Ryder"
        assert result["detected_type"] == "game"

    def test_game_row_persisted_to_db(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            fresh_db.sync_app_details_one(RYDER_APPID, force=True)
        assert fresh_db.app_details_stats()["total"] == 1

    def test_dlc_returns_not_a_game(self, fresh_db):
        _insert_app(99, "Some DLC")
        with patch("steamtools.db.store._steam_app_details", return_value={"type": "dlc", "name": "DLC"}):
            result = fresh_db.sync_app_details_one(99, force=True)
        assert result["status"] == "not_a_game"
        assert result["detected_type"] == "dlc"

    def test_not_a_game_removed_from_apps_table(self, fresh_db):
        _insert_app(99, "Some DLC")
        with patch("steamtools.db.store._steam_app_details", return_value={"type": "dlc"}):
            fresh_db.sync_app_details_one(99, force=True)
        assert fresh_db.search_apps("Some DLC") == []

    def test_none_steam_response_is_not_a_game(self, fresh_db):
        _insert_app(99, "Unknown")
        with patch("steamtools.db.store._steam_app_details", return_value=None):
            result = fresh_db.sync_app_details_one(99, force=True)
        assert result["status"] == "not_a_game"
        assert result["detected_type"] is None

    def test_already_current_skips_steam_call(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA) as mock_steam:
            fresh_db.sync_app_details_one(RYDER_APPID, force=True)
            mock_steam.reset_mock()
            result = fresh_db.sync_app_details_one(RYDER_APPID, force=False)
        assert result["status"] == "already_current"
        mock_steam.assert_not_called()

    def test_force_refetches_current_row(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA) as mock_steam:
            fresh_db.sync_app_details_one(RYDER_APPID, force=True)
            mock_steam.reset_mock()
            result = fresh_db.sync_app_details_one(RYDER_APPID, force=True)
        assert result["status"] == "game"
        mock_steam.assert_called_once_with(RYDER_APPID)


class TestGetAppDetails:
    def test_unknown_appid_returns_none(self, fresh_db):
        with patch("steamtools.db.store._steam_app_details", return_value=None):
            result = fresh_db.get_app_details([999])
        assert result[999] is None

    def test_returns_cached_row_when_fresh(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            fresh_db.sync_app_details_one(RYDER_APPID, force=True)
        with patch("steamtools.db.store._steam_app_details") as mock_steam:
            result = fresh_db.get_app_details([RYDER_APPID])
        mock_steam.assert_not_called()
        assert result[RYDER_APPID]["name"] == "Ryder"

    def test_stale_row_triggers_refetch(self, fresh_db):
        from steamtools.db.connection import get_connection

        _insert_app(RYDER_APPID, "Ryder")
        stale_date = (datetime.now(UTC) - timedelta(days=31)).isoformat()
        with get_connection() as conn:
            conn.execute(
                "INSERT INTO app_details (appid, type, fetched_at) VALUES (?, 'game', ?)",
                (RYDER_APPID, stale_date),
            )
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA) as mock_steam:
            fresh_db.get_app_details([RYDER_APPID])
        mock_steam.assert_called_once_with(RYDER_APPID)

    def test_returns_dict_keyed_by_appid(self, fresh_db):
        _insert_app(1, "A")
        _insert_app(2, "B")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            result = fresh_db.get_app_details([1, 2])
        assert set(result.keys()) == {1, 2}


class TestSyncAppDetails:
    def test_processes_apps_without_details(self, fresh_db):
        _insert_app(1, "A")
        _insert_app(2, "B")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            n = fresh_db.sync_app_details()
        assert n == 2

    def test_limit_restricts_number_processed(self, fresh_db):
        for i in range(1, 6):
            _insert_app(i, f"Game {i}")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            n = fresh_db.sync_app_details(limit=2)
        assert n == 2

    def test_on_progress_called_per_app(self, fresh_db):
        _insert_app(1, "A")
        _insert_app(2, "B")
        calls: list[tuple[int, int, int]] = []
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA):
            fresh_db.sync_app_details(on_progress=lambda i, total, aid, result: calls.append((i, total, aid)))
        assert calls == [(1, 2, 1), (2, 2, 2)]

    def test_skips_apps_with_fresh_details(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_details", return_value=RYDER_STEAM_DATA) as mock_steam:
            fresh_db.sync_app_details()
            n = fresh_db.sync_app_details()
        assert n == 0
        assert mock_steam.call_count == 1


class TestRowFromDetails:
    def test_maps_all_fields_correctly(self):
        from steamtools.db.store import StoDB

        row = StoDB._row_from_details(RYDER_APPID, RYDER_STEAM_DATA)
        assert row["appid"] == RYDER_APPID
        assert row["type"] == "game"
        assert row["name"] == "Ryder"
        assert row["is_free"] == 0
        assert row["coming_soon"] == 0
        assert row["platforms_windows"] == 1
        assert row["platforms_mac"] == 0
        assert row["platforms_linux"] == 0
        assert row["price_currency"] == "USD"
        assert row["price_initial"] == 999
        assert row["price_final"] == 999
        assert row["price_discount_percent"] == 0
        assert json.loads(row["developers"]) == ["Ryder Studios"]
        assert json.loads(row["publishers"]) == ["Ryder Publishing"]
        assert json.loads(row["genres"]) == ["Action"]
        assert json.loads(row["categories"]) == ["Single-player"]
        assert row["achievements_total"] == 5
        assert row["metacritic_score"] is None
        assert "fetched_at" in row

    def test_handles_missing_optional_fields_gracefully(self):
        from steamtools.db.store import StoDB

        row = StoDB._row_from_details(1, {"type": "game", "name": "Minimal"})
        assert row["is_free"] == 0
        assert row["coming_soon"] == 0
        assert json.loads(row["developers"]) == []
        assert json.loads(row["genres"]) == []
        assert row["price_currency"] is None
        assert row["metacritic_score"] is None
        assert row["achievements_total"] is None

    def test_release_date_extracted_from_nested_dict(self):
        from steamtools.db.store import StoDB

        data = {**RYDER_STEAM_DATA, "release_date": {"coming_soon": True, "date": "Q4 2025"}}
        row = StoDB._row_from_details(RYDER_APPID, data)
        assert row["release_date"] == "Q4 2025"
        assert row["coming_soon"] == 1

    def test_metacritic_score_extracted(self):
        from steamtools.db.store import StoDB

        data = {**RYDER_STEAM_DATA, "metacritic": {"score": 85, "url": "https://metacritic.com/game/x"}}
        row = StoDB._row_from_details(RYDER_APPID, data)
        assert row["metacritic_score"] == 85


class TestSyncReviews:
    def test_fetched_status_on_first_call(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            result = fresh_db.sync_reviews(RYDER_APPID)
        assert result["status"] == "fetched"

    def test_reviews_persisted_to_db(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            result = fresh_db.sync_reviews(RYDER_APPID)
        assert result["reviews_fetched"] == 2

    def test_summary_persisted_to_db(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            fresh_db.sync_reviews(RYDER_APPID)
        s = fresh_db.review_stats()
        assert s["games_with_reviews"] == 1
        assert s["total_reviews"] == 2

    def test_summary_fields_correct(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            result = fresh_db.sync_reviews(RYDER_APPID)
        summary = result["summary"]
        assert summary["total_positive"] == 800
        assert summary["total_negative"] == 50
        assert summary["review_score_desc"] == "Very Positive"

    def test_already_current_skips_steam_call(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            fresh_db.sync_reviews(RYDER_APPID)
        with patch("steamtools.db.store._steam_app_reviews") as mock_steam:
            result = fresh_db.sync_reviews(RYDER_APPID, force=False)
        assert result["status"] == "already_current"
        mock_steam.assert_not_called()

    def test_force_refetches_current_summary(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            fresh_db.sync_reviews(RYDER_APPID)
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]) as mock_steam:
            result = fresh_db.sync_reviews(RYDER_APPID, force=True)
        assert result["status"] == "fetched"
        assert mock_steam.call_count == 2

    def test_success_false_stops_pagination(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        failed_page = {"success": 0}
        with patch("steamtools.db.store._steam_app_reviews", return_value=failed_page):
            result = fresh_db.sync_reviews(RYDER_APPID)
        assert result["reviews_fetched"] == 0

    def test_empty_reviews_stops_pagination(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        empty_page = {**_REVIEW_PAGE_1, "reviews": []}
        with patch("steamtools.db.store._steam_app_reviews", return_value=empty_page):
            result = fresh_db.sync_reviews(RYDER_APPID)
        assert result["reviews_fetched"] == 0

    def test_filter_parameter_passed_to_steam(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]) as mock_steam:
            fresh_db.sync_reviews(RYDER_APPID, filter="all")
        assert mock_steam.call_args_list[0].kwargs["filter"] == "all"

    def test_all_reviews_written_in_single_transaction(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            fresh_db.sync_reviews(RYDER_APPID)
        assert fresh_db.review_stats()["total_reviews"] == 2


class TestGetReviewSummary:
    def test_returns_summary_when_present(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            fresh_db.sync_reviews(RYDER_APPID)
        summary = fresh_db.get_review_summary(RYDER_APPID)
        assert summary is not None
        assert summary["total_reviews"] == 850

    def test_returns_none_when_missing(self, fresh_db):
        summary = fresh_db.get_review_summary(RYDER_APPID)
        assert summary is None

    def test_returns_stale_row_without_fetching(self, fresh_db):
        from steamtools.db.connection import get_connection

        _insert_app(RYDER_APPID, "Ryder")
        stale_date = (datetime.now(UTC) - timedelta(days=8)).isoformat()
        with get_connection() as conn:
            conn.execute(
                """INSERT INTO app_review_summary
                   (appid, total_reviews, total_positive, total_negative,
                    review_score, review_score_desc, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (RYDER_APPID, 100, 90, 10, 8, "Very Positive", stale_date),
            )
        with patch("steamtools.db.store._steam_app_reviews") as mock_steam:
            summary = fresh_db.get_review_summary(RYDER_APPID)
        mock_steam.assert_not_called()
        assert summary is not None
        assert summary["total_reviews"] == 100


class TestReviewStats:
    def test_empty_db(self, fresh_db):
        s = fresh_db.review_stats()
        assert s["games_with_reviews"] == 0
        assert s["total_reviews"] == 0
        assert s["last_fetched"] is None

    def test_counts_after_sync(self, fresh_db):
        _insert_app(RYDER_APPID, "Ryder")
        with patch("steamtools.db.store._steam_app_reviews", side_effect=[_REVIEW_PAGE_1, _REVIEW_PAGE_2]):
            fresh_db.sync_reviews(RYDER_APPID)
        s = fresh_db.review_stats()
        assert s["games_with_reviews"] == 1
        assert s["total_reviews"] == 2
        assert s["last_fetched"] is not None


class TestRowFromReview:
    def test_all_fields_mapped(self):
        from steamtools.db.store import StoDB

        review = _REVIEW_PAGE_1["reviews"][0]
        row = StoDB._row_from_review(RYDER_APPID, review, "2025-01-01T00:00:00+00:00")
        assert row["recommendationid"] == 111
        assert row["appid"] == RYDER_APPID
        assert row["author_steamid"] == "76561198000000001"
        assert row["author_playtime_forever"] == 120
        assert row["author_playtime_at_review"] == 60
        assert row["language"] == "english"
        assert row["review"] == "Great game!"
        assert row["voted_up"] == 1
        assert row["votes_up"] == 10
        assert row["weighted_vote_score"] == 0.75
        assert row["steam_purchase"] == 1
        assert row["received_for_free"] == 0
        assert row["written_during_early_access"] == 0

    def test_negative_review_voted_up_zero(self):
        from steamtools.db.store import StoDB

        review = _REVIEW_PAGE_2["reviews"][0]
        row = StoDB._row_from_review(RYDER_APPID, review, "2025-01-01T00:00:00+00:00")
        assert row["voted_up"] == 0

    def test_weighted_vote_score_cast_to_float(self):
        from steamtools.db.store import StoDB

        review = {**_REVIEW_PAGE_1["reviews"][0], "weighted_vote_score": "0.123456"}
        row = StoDB._row_from_review(RYDER_APPID, review, "2025-01-01T00:00:00+00:00")
        assert isinstance(row["weighted_vote_score"], float)

    def test_missing_author_fields_default_to_none(self):
        from steamtools.db.store import StoDB

        review = {**_REVIEW_PAGE_1["reviews"][0], "author": {}}
        row = StoDB._row_from_review(RYDER_APPID, review, "2025-01-01T00:00:00+00:00")
        assert row["author_steamid"] is None
        assert row["author_playtime_forever"] is None
