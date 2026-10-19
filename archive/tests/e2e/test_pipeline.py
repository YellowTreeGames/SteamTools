"""End-to-end tests — full pipeline via the CLI against a real temp DB and live Steam.

These tests invoke `sto` commands through Typer's CliRunner with the DB_PATH
patched to a temp file, making real Steam API calls. They verify that the
complete fetch → store → query pipeline works as a user would experience it.

Run with: uv run pytest -m e2e

Target app: Ryder (appid 3283790)
Store page: https://store.steampowered.com/app/3283790/Ryder/
"""

from datetime import UTC, datetime

import pytest
from typer.testing import CliRunner

from steamtools_cli.cli import app

runner = CliRunner()
RYDER_APPID = 3283790


def _seed_ryder(conn):
    conn.execute(
        "INSERT INTO apps (appid, name, last_seen_at) VALUES (?, ?, ?)",
        (RYDER_APPID, "Ryder", datetime.now(UTC).isoformat()),
    )


@pytest.mark.e2e
def test_fetch_single_app_details_via_cli(tmp_db):
    """sto app-details fetch --appid 3283790 syncs Ryder from Steam and reports status=game."""
    from steamtools.db.connection import get_connection, init_db

    init_db()
    with get_connection() as conn:
        _seed_ryder(conn)

    result = runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0"])

    assert result.exit_code == 0, f"CLI exited non-zero:\n{result.output}"
    assert "status=game" in result.output
    assert "ryder" in result.output.lower()


@pytest.mark.e2e
def test_fetched_details_visible_in_status(tmp_db):
    """After syncing Ryder, sto status shows 1 app with details."""
    from steamtools.db.connection import get_connection, init_db

    init_db()
    with get_connection() as conn:
        _seed_ryder(conn)

    runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0"])
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "1" in result.output  # apps_with_details


@pytest.mark.e2e
def test_fetched_details_visible_in_app_details_info(tmp_db):
    """After syncing Ryder, sto app-details info reports Total: 1."""
    from steamtools.db.connection import get_connection, init_db

    init_db()
    with get_connection() as conn:
        _seed_ryder(conn)

    runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0"])
    result = runner.invoke(app, ["app-details", "info"])

    assert result.exit_code == 0
    assert "1" in result.output


@pytest.mark.e2e
def test_second_fetch_reports_already_current(tmp_db):
    """A second fetch without --force reports already_current, making no Steam call."""
    from steamtools.db.connection import get_connection, init_db

    init_db()
    with get_connection() as conn:
        _seed_ryder(conn)

    runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0"])
    result = runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0"])

    assert result.exit_code == 0
    assert "already_current" in result.output


@pytest.mark.e2e
def test_force_refetch_succeeds(tmp_db):
    """--force on an existing current row re-fetches from Steam and still reports game."""
    from steamtools.db.connection import get_connection, init_db

    init_db()
    with get_connection() as conn:
        _seed_ryder(conn)

    runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0"])
    result = runner.invoke(app, ["app-details", "fetch", "--appid", str(RYDER_APPID), "--sleep", "0", "--force"])

    assert result.exit_code == 0
    assert "status=game" in result.output
