# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & commands

Project is managed with `uv` (Python >=3.13, venv at `.venv/`).

- Install deps: `uv sync`
- Add a dependency: `uv add <package>`
- Run the CLI: `uv run sto <command>` (entrypoint is `steamtools_cli/cli.py`, built with Typer)
  - `sto info` — app count and last-seen timestamp
  - `sto fetch [--count N]` — fetch the Steam app list and upsert into MongoDB; `--count` fetches one page starting after the highest stored appid
  - `sto search QUERY` — case-insensitive name substring search over stored apps
- Config lives in `.env` (copy `.env.example`), loaded by `steamtools/config.py`:
  - `STEAM_API_KEY` — get one at https://steamcommunity.com/dev/apikey
  - `MONGO_URI` (default `mongodb://localhost:27017`) and `MONGO_DB` (default `steamtools`)
- A running MongoDB is required for the CLI and MCP server; unit tests use mongomock and need none.

## Testing

The test tree mirrors the source packages exactly under `tests/unit/`:

```
tests/
  conftest.py                         # `mongo` fixture (mongomock-backed StoDB connection) and MOCK_CLIENT
  unit/
    steamtools/
      db/
        test_connection.py            # mirrors steamtools/db/connection.py
        test_store.py                 # mirrors steamtools/db/store.py
      test_steam_client.py            # mirrors steamtools/steam_client.py
    steamtools_cli/test_cli.py        # mirrors steamtools_cli/cli.py
    steamtools_mcp/test_server.py     # mirrors steamtools_mcp/server.py
```

**Rules:**
- All three of `steamtools/`, `steamtools_cli/`, and `steamtools_mcp/` must have corresponding unit test files. When adding a new module, add a matching test file.
- Unit tests mock all Steam HTTP calls; Mongo-backed tests use the `mongo` fixture (mongomock, in-memory).
- The `mongo` fixture shims mongomock's bulk builder to accept the `sort` argument pymongo now passes.

## Quality gate

**All work is complete only when `run_checks.ps1` passes AND `/code-design-review` reports no issues.**

Run the full quality gate:
```
.\run_checks.ps1
```

This runs in order: ruff format check → ruff lint → mypy type check → bandit security → pytest with a 90% coverage floor. Any failure stops the script. Do not consider a feature or fix done until the script exits cleanly.

After `run_checks.ps1` passes, run `/code-design-review` via a subagent (use the Agent tool) to keep the main context clean. When the subagent finishes, read its output from `temp/code-design-review.md` and iterate until it reports "Code looks good."

Once the design review passes, run `/update-claude-md` via a subagent to keep this file current. The reviewer never touches documentation — CLAUDE.md updates are always a separate step performed by the main agent after the review is clean.

## Architecture

All domain logic lives in `steamtools/` (the core library). The CLI and MCP server are thin routing layers that import from it. **The dataset is games-only by design** — `IStoreService/GetAppList` is queried with only `include_games` set.

- `steamtools/config.py` — loads `STEAM_API_KEY`, `MONGO_URI`, `MONGO_DB` from `.env` via python-dotenv.
- `steamtools/steam_client.py` — HTTP wrappers around `IStoreService/GetAppList` (`get_app_list_page`, `get_app_list`).
- `steamtools/db/` — **the central database API**, built on MongoEngine. Never touch documents or the connection outside this package; add a method to `StoDB` instead.
  - `connection.py` — `connect_db()` registers the default MongoEngine connection (tz-aware datetimes).
  - `models.py` — `App` document (collection `apps`): `appid` (primary key / `_id`), `name`, `last_seen_at`; indexed on `name`.
  - `store.py` — `StoDB`: `sync_app_list(count)` bulk-upserts via `$set` (so extra fields added to app documents later are preserved), `search_apps(query)`, `status()`.
- `steamtools_cli/` — CLI routing only, no business logic. Entrypoint: `sto` → `steamtools_cli.cli:app`.
- `steamtools_mcp/` — MCP server. Tools: `status`, `search_games`, `fetch_app_list`. Entrypoint: `uv run python -m steamtools_mcp.server`.

## Archive

`archive/` holds the earlier SQLite-based implementation (app details, reviews, Gemini ABSA pipeline) and its tests, with original paths preserved under `archive/`. It is excluded from ruff, mypy, bandit and pytest and is not importable; it is reference material for porting features onto the MongoDB layer.
