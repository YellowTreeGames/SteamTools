"""Unit tests for steamtools.db.connection."""

import pytest
from mongoengine import disconnect_all, get_db

from steamtools.db.connection import connect_db
from tests.conftest import MOCK_CLIENT


@pytest.fixture(autouse=True)
def _clean_connections():
    disconnect_all()
    yield
    disconnect_all()


class TestConnectDb:
    def test_uses_configured_database_name(self, monkeypatch):
        monkeypatch.setattr("steamtools.config.MONGO_DB", "from_config")
        connect_db(**MOCK_CLIENT)
        assert get_db().name == "from_config"

    def test_explicit_db_overrides_config(self):
        connect_db(db="other", **MOCK_CLIENT)
        assert get_db().name == "other"

    def test_repeated_calls_with_same_settings_are_idempotent(self):
        connect_db(db="same", **MOCK_CLIENT)
        connect_db(db="same", **MOCK_CLIENT)
        assert get_db().name == "same"
