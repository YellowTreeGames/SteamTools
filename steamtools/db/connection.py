"""MongoDB connection plumbing for SteamTools."""

from mongoengine import connect

from steamtools import config

ALIAS = "default"


def connect_db(host: str | None = None, db: str | None = None, **kwargs):
    """Registers the default MongoEngine connection (idempotent for a given alias)."""
    return connect(db=db or config.MONGO_DB, host=host or config.MONGO_URI, alias=ALIAS, tz_aware=True, **kwargs)
