import threading
from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection, transaction
from pymongo import MongoClient
from pymongo.errors import AutoReconnect, BulkWriteError, PyMongoError

from attachments.events.indexes import EVENTS_COLLECTION
from attachments.events.relay import relay_once, run_loop
from attachments.models import EventOutbox

pytestmark = pytest.mark.mongo

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
LATER = datetime(2026, 10, 16, 9, 5, tzinfo=UTC)


def outbox(**fields):
    fields.setdefault("type", EventOutbox.Type.DOWNLOADED)
    fields.setdefault("occurred_at", NOW)
    fields.setdefault(
        "payload",
        {
            "attachment_public_id": "00000000-0000-0000-0000-000000000001",
            "user_id": 1,
            "ip": "203.0.113.7",
            "user_agent": "ua",
            "requested_by": None,
        },
    )
    return EventOutbox.objects.create(**fields)


@pytest.mark.django_db
def test_relay_publishes_unpublished_events_and_marks_published(events_db):
    rows = [outbox(), outbox()]

    published = relay_once(events_db.database, now=lambda: LATER)

    assert published == 2
    assert sorted(d["event_id"] for d in events_db.find()) == sorted(str(r.event_id) for r in rows)
    assert set(EventOutbox.objects.values_list("published_at", flat=True)) == {LATER}


@pytest.mark.django_db
def test_relay_skips_already_published_rows(events_db):
    outbox(published_at=NOW)
    fresh = outbox()

    published = relay_once(events_db.database, now=lambda: LATER)

    assert published == 1
    assert [d["event_id"] for d in events_db.find()] == [str(fresh.event_id)]


@pytest.mark.django_db
def test_relay_treats_duplicate_event_id_as_success(events_db):
    already_sent = outbox()
    fresh = outbox()
    events_db.insert_one({"event_id": str(already_sent.event_id)})

    published = relay_once(events_db.database, now=lambda: LATER)

    assert published == 2
    assert events_db.count_documents({}) == 2
    assert events_db.count_documents({"event_id": str(fresh.event_id)}) == 1
    assert not EventOutbox.objects.filter(published_at__isnull=True).exists()


@pytest.mark.django_db
def test_relay_keeps_rows_unpublished_when_mongo_down():
    row = outbox()
    down = MongoClient("mongodb://127.0.0.1:1", timeoutMS=5000).get_database("test_down")

    with pytest.raises(PyMongoError):
        relay_once(down, now=lambda: LATER)

    row.refresh_from_db()
    assert row.published_at is None


@pytest.mark.django_db
def test_relay_respects_batch_size(events_db):
    rows = [outbox() for _ in range(3)]

    published = relay_once(events_db.database, batch_size=2, now=lambda: LATER)

    assert published == 2
    assert sorted(d["event_id"] for d in events_db.find()) == sorted(
        str(r.event_id) for r in rows[:2]
    )
    assert list(EventOutbox.objects.filter(published_at__isnull=True)) == [rows[2]]


@pytest.mark.django_db(transaction=True)
def test_concurrent_relays_do_not_select_same_rows(events_db):
    rows = [outbox() for _ in range(4)]
    locked, release = threading.Event(), threading.Event()

    def hold_lock():
        try:
            with transaction.atomic():
                list(
                    EventOutbox.objects.select_for_update().filter(pk__in=[rows[0].pk, rows[1].pk])
                )
                locked.set()
                release.wait(timeout=5)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert locked.wait(timeout=5)
    try:
        published = relay_once(events_db.database, now=lambda: LATER)
    finally:
        release.set()
        holder.join()

    assert published == 2
    assert sorted(d["event_id"] for d in events_db.find()) == sorted(
        str(r.event_id) for r in rows[2:]
    )


@pytest.mark.django_db
def test_relay_document_matches_schema(events_db):
    payload = {
        "attachment_public_id": "00000000-0000-0000-0000-000000000002",
        "user_id": 7,
        "ip": None,
        "user_agent": None,
        "requested_by": None,
    }
    row = outbox(type=EventOutbox.Type.PURGED, payload=payload)

    relay_once(events_db.database, now=lambda: LATER)

    doc = events_db.find_one({}, {"_id": 0})
    assert doc == {"event_id": str(row.event_id), "type": "PURGED", "occurred_at": NOW, **payload}
    assert isinstance(doc["event_id"], str)
    assert doc["occurred_at"].utcoffset() == timedelta(0)


@pytest.mark.django_db
def test_loop_sleeps_when_idle(events_db):
    sleeps = []

    run_loop(events_db.database, sleep=sleeps.append, max_iterations=2)

    assert sleeps == [1, 1]


def scripted_relay(monkeypatch, outcomes):
    script = iter(outcomes)

    def fake_relay_once(db):
        outcome = next(script)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr("attachments.events.relay.relay_once", fake_relay_once)


def test_loop_backs_off_after_mongo_failure(monkeypatch):
    down = AutoReconnect("down")
    scripted_relay(monkeypatch, [down] * 6 + [3, down])
    sleeps = []

    run_loop(None, sleep=sleeps.append, max_iterations=8)

    assert sleeps == [1, 2, 4, 8, 16, 30, 1]


@pytest.mark.parametrize(
    ("error", "level"),
    [
        (BulkWriteError({"writeErrors": [{"index": 0, "code": 121}]}), "ERROR"),
        (AutoReconnect("down"), "WARNING"),
    ],
)
def test_loop_logs_error_for_non_duplicate_write_error(monkeypatch, caplog, error, level):
    scripted_relay(monkeypatch, [error])

    run_loop(None, sleep=lambda s: None, max_iterations=1)

    assert [r.levelname for r in caplog.records if r.name == "attachments.events.relay"] == [level]


@pytest.fixture
def validated_db(events_db):
    db = events_db.database.client[f"{events_db.database.name}_validated"]
    assert db.name.startswith("test_")
    db.client.drop_database(db.name)
    db.create_collection(
        EVENTS_COLLECTION, validator={"$jsonSchema": {"required": ["never_present"]}}
    )
    yield db
    db.client.drop_database(db.name)


@pytest.mark.django_db
def test_relay_keeps_rows_unpublished_on_non_duplicate_write_error(validated_db):
    row = outbox()

    with pytest.raises(BulkWriteError) as exc:
        relay_once(validated_db, now=lambda: LATER)

    assert exc.value.details["writeErrors"][0]["code"] == 121
    row.refresh_from_db()
    assert row.published_at is None
