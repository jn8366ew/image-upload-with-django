from datetime import timedelta

from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.database import Database

EVENTS_COLLECTION = "attachment_events"
TTL = timedelta(days=400)

INDEXES = [
    IndexModel([("event_id", ASCENDING)], name="event_id_unique", unique=True),
    IndexModel(
        [("occurred_at", ASCENDING)],
        name="occurred_at_ttl",
        expireAfterSeconds=int(TTL.total_seconds()),
    ),
    IndexModel([("user_id", ASCENDING), ("occurred_at", DESCENDING)], name="user_occurred_at"),
    IndexModel(
        [("attachment_public_id", ASCENDING), ("occurred_at", DESCENDING)],
        name="attachment_occurred_at",
    ),
]


def ensure_indexes(db: Database) -> list[str]:
    return db[EVENTS_COLLECTION].create_indexes(INDEXES)
