import pytest
from django.core.management import call_command

from attachments.events.indexes import EVENTS_COLLECTION

pytestmark = pytest.mark.mongo


def index(db, name):
    return db[EVENTS_COLLECTION].index_information().get(name, {})


def test_creates_unique_event_id_index(mongo_db):
    call_command("ensure_mongo_indexes")

    info = index(mongo_db, "event_id_unique")
    assert (info.get("key"), info.get("unique")) == ([("event_id", 1)], True)


def test_creates_ttl_index_400_days_on_occurred_at(mongo_db):
    call_command("ensure_mongo_indexes")

    info = index(mongo_db, "occurred_at_ttl")
    assert (info.get("key"), info.get("expireAfterSeconds")) == (
        [("occurred_at", 1)],
        400 * 24 * 60 * 60,
    )


@pytest.mark.parametrize(
    ("name", "key"),
    [
        ("user_occurred_at", [("user_id", 1), ("occurred_at", -1)]),
        ("attachment_occurred_at", [("attachment_public_id", 1), ("occurred_at", -1)]),
    ],
)
def test_creates_user_and_attachment_lookup_indexes(mongo_db, name, key):
    call_command("ensure_mongo_indexes")

    assert index(mongo_db, name).get("key") == key
