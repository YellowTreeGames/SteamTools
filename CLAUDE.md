# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & commands

Project is managed with `uv` (Python >=3.13, venv at `.venv/`).

- Install deps: `uv sync`
- Add a dependency: `uv add <package>`
- Run a module: `uv run python -m <package>.<module>`
- Run the CLI: `uv run sto <command>` (entrypoint is `steamtools_cli/cli.py`, built with Typer)
  - `sto app info` — high-level stats on the apps table
  - `sto app fetch [--count N]` — refresh the master app list
  - `sto app-details info` — stats on the app_details table
  - `sto app-details fetch [--count N] [--sleep S]` — batch-fetch missing app details
- Requires a Steam Web API key: copy `.env.example` to `.env` and set `STEAM_API_KEY` (get one at https://steamcommunity.com/dev/apikey). Loaded via `steamtools/config.py` (`python-dotenv`).

No linter/test suite is configured yet — add this section once one exists.

## Architecture

All domain logic lives in `steamtools/` (the core library). The CLI and MCP server are thin routing layers that import from it. **The dataset is games-only by design** — DLC, demos, software, videos, hardware, mods, etc. are filtered out at every stage rather than stored and filtered later.

**Seed database**: `C:\Users\atawz\Github\AutomatedLifeToolkit\data\game_dev\steam.db` — a legacy SQLite DB with a `bronze_steam_app_details` table that includes richer fields than our current schema. Used by running `seed_legacy_db.py` directly for the initial data import.

- `steamtools/config.py` — loads env vars (`STEAM_API_KEY`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `MAX_SCORES`) from `.env` via python-dotenv.
- `steamtools/steam_client.py` — thin HTTP wrappers around the Steam Web API (GetAppList, appdetails, reviews endpoints).
- `steamtools/db/` — **the central database API**. All reads and writes go through `StoDB` (defined in `store.py`). Never open raw `get_connection()` calls outside this package; add a method to `StoDB` instead.
  - `connection.py` — `DB_PATH`, `SCHEMA`, `get_connection()`, `init_db()`. The DB file lives at `data/steamtools.db` (gitignored).
  - `staleness.py` — refresh policy rules. `needs_refresh_details(row)`: monthly for all app_details. `needs_refresh_reviews(review_row, details_row)`: monthly for unreleased games and games released under a year ago; yearly for games over a year old.
  - `store.py` — `StoDB` class. Key methods:
    - `sync_app_list(count)` — upsert apps table from Steam
    - `get_app_details(appids, auto_sync=True)` — returns dict[appid → row], fetches stale/missing from Steam if auto_sync
    - `sync_app_details(limit, on_progress)` — batch refresh stale/missing app_details
    - `sync_app_details_one(appid, force)` — single-appid fetch; deletes non-games from apps table
    - `get_review_counts(appids, auto_sync=True)` — returns dict[appid → row], applies staleness policy
    - `sync_review_counts(appids, limit, on_progress)` — batch refresh stale/missing review counts
    - `get_stale_review_appids_for_evals()` — used by `sto ai eval sync`
- `steamtools/ai/` — LLM-based evaluations. `eval.py` orchestrates game scoring; `gemini_client.py` wraps the Gemini API.
- `steamtools/vectordb/` — ChromaDB wrapper (`VectorManager`). Vector data lives at `data/vectordb/`.
- `steamtools/review_topics/` — review topic discovery pipeline: `embedder.py` (sentence-transformers), `clusterer.py` (HDBSCAN), `labeler.py` (Gemini cluster naming), `pipeline.py` (end-to-end orchestration).
- `steamtools_cli/` — CLI routing only, no business logic. Entrypoint: `sto` → `steamtools_cli.cli:app`.
- `steamtools_mcp/` — MCP server (public API for LLM use). Entrypoint: `uv run python -m steamtools_mcp.server`.
