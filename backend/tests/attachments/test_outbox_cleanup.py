from datetime import UTC, datetime, timedelta

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from attachments.models import EventOutbox
from attachments.services.maintenance import run_maintenance

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)


def outbox_row(published_at=None, occurred_at=NOW - timedelta(days=30)):
    return EventOutbox.objects.create(
        type=EventOutbox.Type.DOWNLOADED,
        payload={},
        occurred_at=occurred_at,
        published_at=published_at,
    )


def outbox_queries(captured):
    return [q["sql"] for q in captured if "attachments_eventoutbox" in q["sql"]]


@pytest.mark.django_db
def test_published_outbox_rows_older_than_7_days_are_deleted(gateway):
    row = outbox_row(published_at=NOW - timedelta(days=7))

    with CaptureQueriesContext(connection) as captured:
        result = run_maintenance(gateway=gateway, now=lambda: NOW)

    assert not EventOutbox.objects.filter(pk=row.pk).exists()
    assert result.outbox_deleted == 1
    queries = outbox_queries(captured)
    assert len(queries) == 1 and queries[0].startswith("DELETE")


@pytest.mark.django_db
def test_published_outbox_rows_younger_than_7_days_are_kept(gateway):
    row = outbox_row(published_at=NOW - timedelta(days=7) + timedelta(seconds=1))

    result = run_maintenance(gateway=gateway, now=lambda: NOW)

    assert EventOutbox.objects.filter(pk=row.pk).exists()
    assert result.outbox_deleted == 0


@pytest.mark.django_db
def test_unpublished_outbox_rows_are_never_deleted(gateway):
    row = outbox_row(published_at=None, occurred_at=NOW - timedelta(days=400))

    result = run_maintenance(gateway=gateway, now=lambda: NOW)

    assert EventOutbox.objects.filter(pk=row.pk).exists()
    assert result.outbox_deleted == 0
