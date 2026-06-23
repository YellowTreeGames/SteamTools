"""Thin wrapper around the public Steam Web API / store endpoints used to seed our local DB."""

import time

import requests

from steamtools.config import STEAM_API_KEY

APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
APP_REVIEWS_URL = "https://store.steampowered.com/appreviews/{appid}"

_session = requests.Session()


def _get_with_retry(url: str, params: dict, max_retries: int, context: str) -> requests.Response:
    delay = 2.0
    for _ in range(max_retries):
        resp = _session.get(url, params=params, timeout=30)  # type: ignore[arg-type]
        if resp.status_code == 429:
            time.sleep(delay)
            delay *= 2
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"{context} kept getting rate-limited after {max_retries} retries")


def get_app_list_page(last_appid: int = 0, max_results: int = 50000) -> dict:
    """Fetches a single page of (appid, name) pairs Steam lists as a game.

    Returns {"apps": [...], "have_more_results": bool, "last_appid": int}.
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
    resp = _session.get(APP_LIST_URL, params=params, timeout=30)  # type: ignore[arg-type]
    resp.raise_for_status()
    data = resp.json()["response"]
    return {
        "apps": data.get("apps", []),
        "have_more_results": bool(data.get("have_more_results")),
        "last_appid": data.get("last_appid", last_appid),
    }


def get_app_list() -> list[dict]:
    """Returns every (appid, name) pair Steam lists as a game (full catalog refresh)."""
    apps = []
    last_appid = 0
    while True:
        page = get_app_list_page(last_appid=last_appid)
        apps.extend(page["apps"])
        if not page["have_more_results"]:
            break
        last_appid = page["last_appid"]
    return apps


def get_app_reviews(
    appid: int,
    cursor: str = "*",
    language: str = "all",
    filter: str = "all",
    num_per_page: int = 100,
    max_retries: int = 5,
) -> dict:
    """Fetch one page of reviews for an appid.

    Returns the full JSON response: {"success": int, "query_summary": {...},
    "reviews": [...], "cursor": str}. No API key required.
    """
    params = {
        "json": 1,
        "cursor": cursor,
        "language": language,
        "filter": filter,
        "num_per_page": num_per_page,
        "review_type": "all",
        "purchase_type": "all",
        "filter_offtopic_activity": 0,
    }
    url = APP_REVIEWS_URL.format(appid=appid)
    resp = _get_with_retry(url, params, max_retries, f"reviews for {appid}")
    return resp.json()


def get_app_details(appid: int, max_retries: int = 5) -> dict | None:
    """Fetches appdetails for a single appid.

    Returns the "data" payload on success, or None if Steam reports no data.
    Retries with backoff on 429s.
    """
    params = {"appids": appid, "cc": "us", "l": "english"}
    resp = _get_with_retry(APP_DETAILS_URL, params, max_retries, f"appdetails for {appid}")
    payload = resp.json().get(str(appid))
    if payload is None or not payload.get("success"):
        return None
    return payload["data"]
