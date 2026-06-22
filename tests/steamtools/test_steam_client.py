"""Tests for steamtools.steam_client — all HTTP calls are mocked."""

from unittest.mock import MagicMock

import pytest
import requests

import steamtools.steam_client as sc


def _resp(status: int = 200, data: dict | None = None) -> MagicMock:
    mock = MagicMock()
    mock.status_code = status
    mock.json.return_value = data or {}
    if status >= 400:
        mock.raise_for_status.side_effect = requests.HTTPError(f"{status}")
    else:
        mock.raise_for_status.return_value = None
    return mock


# ── get_app_list_page ─────────────────────────────────────────────────────────


def test_get_app_list_page_no_key(monkeypatch):
    monkeypatch.setattr(sc, "STEAM_API_KEY", None)
    with pytest.raises(RuntimeError, match="STEAM_API_KEY"):
        sc.get_app_list_page()


def test_get_app_list_page_success(monkeypatch, mocker):
    monkeypatch.setattr(sc, "STEAM_API_KEY", "key")
    payload = {"response": {"apps": [{"appid": 1, "name": "A"}], "have_more_results": False}}
    mocker.patch.object(sc._session, "get", return_value=_resp(200, payload))
    result = sc.get_app_list_page()
    assert result["apps"] == [{"appid": 1, "name": "A"}]
    assert result["have_more_results"] is False


def test_get_app_list_page_defaults_when_keys_missing(monkeypatch, mocker):
    monkeypatch.setattr(sc, "STEAM_API_KEY", "key")
    payload = {"response": {}}
    mocker.patch.object(sc._session, "get", return_value=_resp(200, payload))
    result = sc.get_app_list_page(last_appid=5)
    assert result["apps"] == []
    assert result["have_more_results"] is False
    assert result["last_appid"] == 5  # falls back to the passed value


# ── get_app_list ──────────────────────────────────────────────────────────────


def test_get_app_list_paginates(monkeypatch, mocker):
    monkeypatch.setattr(sc, "STEAM_API_KEY", "key")
    page1 = {"response": {"apps": [{"appid": 1, "name": "A"}], "have_more_results": True, "last_appid": 1}}
    page2 = {"response": {"apps": [{"appid": 2, "name": "B"}], "have_more_results": False}}
    mocker.patch.object(sc._session, "get", side_effect=[_resp(200, page1), _resp(200, page2)])
    result = sc.get_app_list()
    assert len(result) == 2
    assert result[1]["appid"] == 2


# ── get_app_details ───────────────────────────────────────────────────────────


def _details_payload(appid: int, data: dict) -> dict:
    return {str(appid): {"success": True, "data": data}}


def test_get_app_details_success(mocker):
    data = {"type": "game", "name": "Test"}
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _details_payload(10, data)))
    result = sc.get_app_details(10)
    assert result == data


def test_get_app_details_missing_appid(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(200, {}))
    assert sc.get_app_details(10) is None


def test_get_app_details_success_false(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(200, {"10": {"success": False}}))
    assert sc.get_app_details(10) is None


def test_get_app_details_429_then_success(mocker):
    data = {"type": "game", "name": "Test"}
    mocker.patch.object(
        sc._session,
        "get",
        side_effect=[_resp(429), _resp(200, _details_payload(10, data))],
    )
    result = sc.get_app_details(10)
    assert result == data


def test_get_app_details_all_429_raises(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(429))
    with pytest.raises(RuntimeError, match="rate-limited"):
        sc.get_app_details(10, max_retries=2)


# ── get_reviews_page ──────────────────────────────────────────────────────────


def _reviews_payload(reviews=None, cursor="next", total=10):
    return {
        "reviews": reviews or [],
        "cursor": cursor,
        "query_summary": {"total_reviews": total},
    }


def test_get_reviews_page_success(mocker):
    review = {
        "recommendationid": "r1",
        "voted_up": True,
        "votes_up": 5,
        "votes_funny": 0,
        "weighted_vote_score": "0.9",
        "steam_purchase": True,
        "received_for_free": False,
        "written_during_early_access": False,
        "author": {"playtime_forever": 120, "playtime_last_two_weeks": 10},
        "review": "Great game!",
        "timestamp_created": 1700000000,
    }
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _reviews_payload([review])))
    result = sc.get_reviews_page(10)
    assert len(result["reviews"]) == 1
    assert result["reviews"][0]["review"] == "Great game!"
    assert result["total_reviews"] == 10


def test_get_reviews_page_null_author(mocker):
    review = {
        "recommendationid": "r1",
        "voted_up": True,
        "votes_up": 0,
        "votes_funny": 0,
        "weighted_vote_score": "0.5",
        "steam_purchase": False,
        "received_for_free": False,
        "written_during_early_access": False,
        "author": None,
        "review": "OK",
        "timestamp_created": 0,
    }
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _reviews_payload([review])))
    result = sc.get_reviews_page(10)
    assert result["reviews"][0]["author_playtime_forever"] is None


def test_get_reviews_page_empty(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _reviews_payload([], cursor="")))
    result = sc.get_reviews_page(10)
    assert result["reviews"] == []


def test_get_reviews_page_429_then_success(mocker):
    mocker.patch.object(
        sc._session,
        "get",
        side_effect=[_resp(429), _resp(200, _reviews_payload())],
    )
    result = sc.get_reviews_page(10)
    assert result["total_reviews"] == 10


def test_get_reviews_page_all_429_raises(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(429))
    with pytest.raises(RuntimeError, match="rate-limited"):
        sc.get_reviews_page(10, max_retries=2)


# ── get_review_counts ─────────────────────────────────────────────────────────


def _counts_payload(success=True, summary=None):
    base = {"success": success}
    if summary is not None:
        base["query_summary"] = summary
    return base


_SUMMARY = {
    "total_reviews": 100,
    "total_positive": 80,
    "total_negative": 20,
    "review_score": 8,
    "review_score_desc": "Very Positive",
}


def test_get_review_counts_success(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _counts_payload(summary=_SUMMARY)))
    result = sc.get_review_counts(10)
    assert result is not None
    assert result["total_reviews"] == 100


def test_get_review_counts_not_success(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _counts_payload(success=False)))
    assert sc.get_review_counts(10) is None


def test_get_review_counts_no_summary(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(200, _counts_payload(success=True)))
    assert sc.get_review_counts(10) is None


def test_get_review_counts_429_then_success(mocker):
    mocker.patch.object(
        sc._session,
        "get",
        side_effect=[_resp(429), _resp(200, _counts_payload(summary=_SUMMARY))],
    )
    result = sc.get_review_counts(10)
    assert result["total_reviews"] == 100


def test_get_review_counts_all_429_raises(mocker):
    mocker.patch.object(sc._session, "get", return_value=_resp(429))
    with pytest.raises(RuntimeError, match="rate-limited"):
        sc.get_review_counts(10, max_retries=2)
