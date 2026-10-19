"""Thin wrapper around the Steam Web API used to seed the local apps collection."""

import requests

from steamtools.config import STEAM_API_KEY

APP_LIST_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"

_session = requests.Session()


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
