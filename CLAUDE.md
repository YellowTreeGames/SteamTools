# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & commands

Project is managed with `uv` (Python >=3.13, venv at `.venv/`).

- Install deps: `uv sync`
- Add a dependency: `uv add <package>`
- Run a module: `uv run python -m <package>.<module>`
- Run the CLI: `uv run sto <command>` (entrypoint is `steamtools_cli/cli.py`, built with Typer)
  - `sto info [--app] [--app-details]` — combined status from all tables; narrow with flags
  - `sto fetch [--app] [--app-details] [--count N] [--sleep S] [--appid ID] [--force]` — fetch apps and/or details from Steam; defaults to both
  - `sto reviews fetch --appid ID [--language L] [--force]` — fetch all reviews for a game and store them locally
  - `sto reviews info [--appid ID]` — show stored review stats; with `--appid`, shows that game's summary
- Requires a Steam Web API key: copy `.env.example` to `.env` and set `STEAM_API_KEY` (get one at https://steamcommunity.com/dev/apikey). Loaded via `steamtools/config.py` (`python-dotenv`).

## Testing

The test tree mirrors the source packages exactly under `tests/unit/`, with separate directories for integration and e2e:

```
tests/
  conftest.py                         # shared fixtures (tmp_db, fresh_db) and constants (RYDER_APPID, RYDER_STEAM_DATA)
  unit/
    steamtools/
      db/
        test_connection.py            # mirrors steamtools/db/connection.py
        test_staleness.py             # mirrors steamtools/db/staleness.py
        test_store.py                 # mirrors steamtools/db/store.py
      test_steam_client.py            # mirrors steamtools/steam_client.py
    steamtools_cli/
      test_cli.py                     # mirrors steamtools_cli/cli.py
    steamtools_mcp/
      test_server.py                  # mirrors steamtools_mcp/server.py
  integration/
    test_steam_api.py                 # live HTTP calls to Steam (no API key needed)
  e2e/
    test_pipeline.py                  # CLI commands → temp DB + live Steam
```

**Rules:**
- All three of `steamtools/`, `steamtools_cli/`, and `steamtools_mcp/` must have corresponding unit test files. When adding a new module, add a matching test file.
- Unit tests mock all Steam HTTP calls and patch `DB_PATH` via the `tmp_db` fixture.
- Integration tests hit the real Steam API but involve no DB. Marked `@pytest.mark.integration`.
- E2E tests drive the CLI via CliRunner against a temp DB and the real Steam API. Marked `@pytest.mark.e2e`.
- The quality gate (`run_checks.ps1`) runs only unit tests. To run live tests: `uv run pytest -m integration` or `uv run pytest -m e2e`.
- Test target for live calls: Ryder, appid `3283790` (`https://store.steampowered.com/app/3283790/Ryder/`). `get_app_details` requires no API key.

## Quality gate

**All work is complete only when `run_checks.ps1` passes AND `/code-design-review` reports no issues.**

Run the full quality gate:
```
.\run_checks.ps1
```

This runs in order: ruff format check → ruff lint → mypy type check → bandit security. Any failure stops the script. Do not consider a feature or fix done until the script exits cleanly.

After `run_checks.ps1` passes, run `/code-design-review` via a subagent (use the Agent tool) to keep the main context clean. When the subagent finishes, read its output from `temp/code-design-review.md` and iterate until it reports "Code looks good."

Once the design review passes, run `/update-claude-md` via a subagent to keep this file current. The reviewer never touches documentation — CLAUDE.md updates are always a separate step performed by the main agent after the review is clean.

## Architecture

All domain logic lives in `steamtools/` (the core library). The CLI and MCP server are thin routing layers that import from it. **The dataset is games-only by design** — DLC, demos, software, videos, hardware, mods, etc. are filtered out at every stage rather than stored and filtered later.

- `steamtools/config.py` — loads `STEAM_API_KEY` from `.env` via python-dotenv.
- `steamtools/steam_client.py` — thin HTTP wrappers around the Steam Web API (`get_app_list`, `get_app_list_page`, `get_app_details`, `get_app_reviews`).
- `steamtools/db/` — **the central database API**. All reads and writes go through `StoDB` (defined in `store.py`). Never open raw `get_connection()` calls outside this package; add a method to `StoDB` instead.
  - `connection.py` — `DB_PATH`, `SCHEMA`, `get_connection()`, `init_db()`. The DB file lives at `data/steamtools.db` (gitignored). Schema includes `apps`, `app_details`, `app_review_summary`, and `app_reviews`. On init, drops legacy tables and runs additive column migrations.
  - `staleness.py` — `needs_refresh_details(row)`: app_details are stale after 30 days. `needs_refresh_review_summary(row)`: review summary is stale after 7 days.
  - `store.py` — `StoDB` class. **StoDB is a cache over Steam**: `get_*` methods always check the DB first and only hit Steam when data is missing or stale. `sync_*` methods are explicit pipeline operations (bulk prefetch, force-refresh). Key methods:
    - `status()` / `app_stats()` / `app_details_stats()` / `review_stats()` — DB stats
    - `sync_app_list(count)` — upsert apps table from Steam
    - `get_app_details(appids)` — returns `dict[appid → row | None]`; DB-first, fetches from Steam for stale/missing, returns None for confirmed non-games
    - `sync_app_details(limit, on_progress)` — bulk prefetch pipeline operation (used by `sto fetch --app-details`)
    - `sync_app_details_one(appid, force)` — explicit single-appid fetch with status result; used by CLI `--appid` and MCP `get_app_details`
    - `sync_reviews(appid, force, language)` — paginate Steam review API and upsert `app_reviews` + `app_review_summary`
    - `get_review_summary(appid)` — DB-first review summary fetch; refreshes if stale
    - `search_apps(query)` — name substring search
- `steamtools_cli/` — CLI routing only, no business logic. Entrypoint: `sto` → `steamtools_cli.cli:app`.
- `steamtools_mcp/` — MCP server. Tools: `status`, `search_games`, `get_app_details`, `fetch_app_list`, `fetch_app_details`, `fetch_reviews`, `get_review_summary`. Entrypoint: `uv run python -m steamtools_mcp.server`.
