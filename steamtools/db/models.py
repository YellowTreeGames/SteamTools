"""MongoEngine documents for SteamTools."""

from mongoengine import DateTimeField, Document, IntField, StringField


class App(Document):
    """One Steam game, keyed by appid."""

    appid = IntField(primary_key=True)
    name = StringField(required=True)
    last_seen_at = DateTimeField(required=True)

    meta = {"collection": "apps", "indexes": ["name"]}
