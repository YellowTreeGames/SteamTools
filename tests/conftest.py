"""Shared pytest fixtures."""

from functools import partial

import mongomock
import pytest
from mongoengine import disconnect_all
from mongomock.collection import BulkOperationBuilder

from steamtools.db.connection import connect_db

MOCK_CLIENT = {"host": "localhost", "mongo_client_class": mongomock.MongoClient}


def _ignoring_sort(method):
    def wrapper(self, *args, sort=None, **kwargs):
        return method(self, *args, **kwargs)

    return wrapper


@pytest.fixture()
def mongo(monkeypatch):
    """Route StoDB's connection to a fresh in-memory mongomock database for the test.

    mongomock's bulk builder predates the `sort` argument pymongo now passes, so it is accepted and dropped.
    """
    disconnect_all()
    monkeypatch.setattr(BulkOperationBuilder, "add_update", _ignoring_sort(BulkOperationBuilder.add_update))
    monkeypatch.setattr(BulkOperationBuilder, "add_replace", _ignoring_sort(BulkOperationBuilder.add_replace))
    monkeypatch.setattr("steamtools.db.store.connect_db", partial(connect_db, db="steamtools_test", **MOCK_CLIENT))
    yield
    disconnect_all()
