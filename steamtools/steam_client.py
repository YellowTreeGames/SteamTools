"""Thin wrapper around the public Steam Web API / store endpoints used to seed our local DB."""

import time

import requests

from steamtools.config import STEAM_API_KEY

APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

_session = requests.Session()


def get_app_list_page(last_appid: int = 0, max_results: int = 50000) -> dict:
    """Fetches a single page of (appid, name) pairs Steam lists as a game.

    Steam retired the old free ISteamApps/GetAppList/v2 endpoint; the
    replacement (IStoreService/GetAppList/v1) requires an API key and is
    paginated via last_appid/have_more_results. include_games=true /
    everything else false filters out dlc/software/videos/hardware at the
    source - this project only wants games. appdetails-confirmed type is
    still re-checked downstream (processes/fetch_app_details.py), since
    this flag isn't a perfect proxy for appdetails' own type field.

    Returns {"apps": [...], "have_more_results": bool, "last_appid": int},
    where last_appid is the cursor to pass back in for the next page.
    """
    if not STEAM_API_KEY:
        raise RuntimeError("STEAM_API_KEY is not set. Copy .env.example to .env and fill it in.")

    params = {
        "key": STEAM_API_KEY,
        "max_results": max_results,
        "last_appid": last_appid,
        "include_games": "true",
        "include_dlc": "false",
        "include_software": "false",
        "include_videos": "false",
        "include_hardware": "false",
    }
    resp = _session.get(APP_LIST_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()["response"]
    return {
        "apps": data.get("apps", []),
        "have_more_results": bool(data.get("have_more_results")),
        "last_appid": data.get("last_appid", last_appid),
    }


def get_app_list() -> list[dict]:
    """Returns every (appid, name) pair Steam lists as a game.

    Loops get_app_list_page from appid 0 until exhausted - a full catalog
    refresh.
    """
    apps = []
    last_appid = 0
    while True:
        page = get_app_list_page(last_appid=last_appid)
        apps.extend(page["apps"])
        if not page["have_more_results"]:
            break
        last_appid = page["last_appid"]

    return apps


def get_app_details(appid: int, max_retries: int = 5) -> dict | None:
    """Fetches appdetails for a single appid.

    Returns the "data" payload on success, or None if Steam reports no data
    for this appid (delisted, region-locked, etc.). Retries with backoff on
    429s, since this endpoint rate-limits aggressively.
    """
    params = {"appids": appid, "cc": "us", "l": "english"}
    delay = 2.0
    for attempt in range(max_retries):
        resp = _session.get(APP_DETAILS_URL, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        payload = resp.json().get(str(appid))
        if payload is None or not payload.get("success"):
            return None
        return payload["data"]
    raise RuntimeError(f"appdetails for {appid} kept getting rate-limited after {max_retries} retries")


def get_reviews_page(
    appid: int,
    cursor: str = "*",
    num_per_page: int = 100,
    filter_type: str = "all",
    language: str = "english",
    max_retries: int = 5,
) -> dict:
    """Fetch one page of review texts for an appid.

    Returns {"reviews": [...], "cursor": str, "total_reviews": int}.
    Each review dict contains review text plus author/vote metadata.
    Retries with exponential backoff on 429s.
    """
    url = REVIEWS_URL.format(appid=appid)
    params = {
        "json": 1,
        "cursor": cursor,
        "num_per_page": num_per_page,
        "filter": filter_type,
        "language": language,
        "review_type": "all",
        "purchase_type": "all",
    }
    delay = 2.0
    for _ in range(max_retries):
        resp = _session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        data = resp.json()

        reviews_raw = data.get("reviews") or []
        reviews = []
        for r in reviews_raw:
            author = r.get("author") or {}
            reviews.append({
                "recommendationid": r.get("recommendationid"),
                "voted_up": r.get("voted_up"),
                "votes_up": r.get("votes_up"),
                "votes_funny": r.get("votes_funny"),
                "weighted_vote_score": r.get("weighted_vote_score"),
                "steam_purchase": r.get("steam_purchase"),
                "received_for_free": r.get("received_for_free"),
                "written_during_early_access": r.get("written_during_early_access"),
                "author_playtime_forever": author.get("playtime_forever"),
                "author_playtime_last_two_weeks": author.get("playtime_last_two_weeks"),
                "review": r.get("review"),
                "timestamp_created": r.get("timestamp_created"),
            })

        summary = data.get("query_summary") or {}
        return {
            "reviews": reviews,
            "cursor": data.get("cursor", ""),
            "total_reviews": summary.get("total_reviews", 0),
        }
    raise RuntimeError(f"reviews page for {appid} kept getting rate-limited after {max_retries} retries")


def get_review_counts(appid: int, max_retries: int = 5) -> dict | None:
    """Fetches review counts for a single appid from the store reviews endpoint.

    Returns {"total_reviews": int, "total_positive": int, "total_negative": int,
             "review_score": int, "review_score_desc": str}
    or None if Steam returns no data. Retries with backoff on 429s.
    No API key required; language=all returns global totals.
    """
    url = REVIEWS_URL.format(appid=appid)
    params = {"json": 1, "num_per_page": 0, "language": "all"}
    delay = 2.0
    for _ in range(max_retries):
        resp = _session.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            return None
        summary = data.get("query_summary")
        if not summary:
            return None
        return {
            "total_reviews": summary.get("total_reviews", 0),
            "total_positive": summary.get("total_positive", 0),
            "total_negative": summary.get("total_negative", 0),
            "review_score": summary.get("review_score"),
            "review_score_desc": summary.get("review_score_desc"),
        }
    raise RuntimeError(f"review counts for {appid} kept getting rate-limited after {max_retries} retries")
