from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from pymongo import MongoClient

from attachments.models import EventOutbox
from tests.attachments.test_relay import outbox

pytestmark = pytest.mark.mongo


@pytest.mark.django_db
def test_relay_events_command_publishes_once(events_db):
    outbox()
    out = StringIO()

    call_command("relay_events", stdout=out)

    assert out.getvalue().strip() == "published=1"
    assert events_db.count_documents({}) == 1
    assert not EventOutbox.objects.filter(published_at__isnull=True).exists()


@pytest.mark.django_db
def test_relay_events_command_fails_when_mongo_down(monkeypatch):
    from attachments.events import mongo

    outbox()
    down = MongoClient("mongodb://127.0.0.1:1", timeoutMS=200).get_database("test_down")
    monkeypatch.setattr(mongo, "database", lambda: down)

    with pytest.raises(CommandError):
        call_command("relay_events")

    assert EventOutbox.objects.filter(published_at__isnull=True).count() == 1


def test_relay_events_loop_option_runs_loop(monkeypatch, events_db):
    calls = []
    monkeypatch.setattr("attachments.events.relay.run_loop", lambda db: calls.append(db))

    call_command("relay_events", "--loop")

    assert calls == [events_db.database]
