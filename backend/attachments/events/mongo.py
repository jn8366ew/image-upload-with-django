from functools import cache

from django.conf import settings
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError as MongoError

__all__ = ["MongoError", "client", "database"]


@cache
def client() -> MongoClient:
    return MongoClient(settings.MONGO_URI, tz_aware=True, timeoutMS=5000)


def database() -> Database:
    return client().get_default_database()
