import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
import time_machine
from django.db import connection, transaction

from attachments.exceptions import StorageAuthError
from attachments.models import Attachment, AttachmentPurgeLog
from attachments.services.maintenance import MaintenanceResult, run_maintenance

pytestmark = pytest.mark.django_db(transaction=True)

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
PNG = b"\x89PNG\r\n\x1a\nbody"


def run(gateway):
    with time_machine.travel(NOW, tick=False):
        return run_maintenance(gateway=gateway)


@pytest.fixture
def stored(make_attachment, gateway):
    def make(body=PNG, **fields):
        att = make_attachment(**fields)
        gateway.put(att.s3_key, body, "image/png")
        return att

    return make


def gone(att, gateway):
    return not Attachment.objects.filter(pk=att.pk).exists() and att.s3_key not in gateway.objects


def test_leftover_deleting_rows_are_retried(stored, gateway):
    att = stored(status=Attachment.Status.DELETING)

    run(gateway)

    assert gone(att, gateway)


def pending_created_at(stored, when, **fields):
    with time_machine.travel(when, tick=False):
        return stored(status=Attachment.Status.PENDING, **fields)


def test_pending_older_than_24h_with_valid_object_is_completed(stored, gateway):
    att = pending_created_at(stored, NOW - timedelta(hours=24))

    run(gateway)

    att.refresh_from_db()
    assert (att.status, att.uploaded_at) == (Attachment.Status.COMPLETED, NOW)


def test_pending_older_than_24h_without_object_is_purged(stored, gateway):
    att = pending_created_at(stored, NOW - timedelta(hours=24))
    gateway.objects.pop(att.s3_key)

    run(gateway)

    assert not Attachment.objects.filter(pk=att.pk).exists()


def test_pending_younger_than_24h_is_untouched(stored, gateway):
    att = pending_created_at(stored, NOW - timedelta(hours=24) + timedelta(seconds=1))

    run(gateway)

    att.refresh_from_db()
    assert att.status == Attachment.Status.PENDING
    assert att.s3_key in gateway.objects


def test_pending_older_than_24h_with_invalid_object_is_purged(stored, gateway):
    att = pending_created_at(stored, NOW - timedelta(hours=24), body=b"GIF89a-not-png")

    run(gateway)

    assert gone(att, gateway)


def test_rejected_rows_are_purged(stored, gateway):
    att = stored(status=Attachment.Status.REJECTED)

    run(gateway)

    assert gone(att, gateway)


def completed(stored, **fields):
    fields.setdefault("uploaded_at", NOW - timedelta(days=60))
    return stored(status=Attachment.Status.COMPLETED, **fields)


def test_soft_deleted_30_days_is_purged(stored, gateway):
    att = completed(stored, deleted_at=NOW - timedelta(days=30))

    run(gateway)

    assert gone(att, gateway)


def test_soft_deleted_just_under_30_days_is_kept(stored, gateway):
    att = completed(stored, deleted_at=NOW - timedelta(days=30) + timedelta(seconds=1))

    run(gateway)

    assert Attachment.objects.filter(pk=att.pk, status=Attachment.Status.COMPLETED).exists()
    assert att.s3_key in gateway.objects


def test_uploaded_365_days_is_purged(stored, gateway):
    att = completed(stored, uploaded_at=NOW - timedelta(days=365))

    run(gateway)

    assert gone(att, gateway)


def test_uploaded_just_under_365_days_is_kept(stored, gateway):
    att = completed(stored, uploaded_at=NOW - timedelta(days=365) + timedelta(seconds=1))

    run(gateway)

    assert Attachment.objects.filter(pk=att.pk, status=Attachment.Status.COMPLETED).exists()
    assert att.s3_key in gateway.objects


def test_purge_keeps_rows_deleting_when_s3_delete_fails(stored, gateway):
    failing = stored(status=Attachment.Status.REJECTED)
    other = stored(status=Attachment.Status.REJECTED)
    gateway.fail_delete_for.add(failing.s3_key)

    run(gateway)

    assert Attachment.objects.get(pk=failing.pk).status == Attachment.Status.DELETING
    assert gone(other, gateway)


def test_failed_purge_is_not_retried_in_same_run(stored, gateway, monkeypatch):
    att = stored(status=Attachment.Status.REJECTED)
    gateway.fail_delete_for.add(att.s3_key)
    attempts = []
    real_delete = gateway.delete

    def counting_delete(key):
        attempts.append(key)
        real_delete(key)

    monkeypatch.setattr(gateway, "delete", counting_delete)

    run(gateway)

    assert attempts == [att.s3_key]


def test_pending_transient_storage_error_counts_as_failed(stored, gateway):
    att = pending_created_at(stored, NOW - timedelta(hours=25))
    rejected = stored(status=Attachment.Status.REJECTED)
    gateway.fail_head_for.add(att.s3_key)

    result = run(gateway)

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.PENDING
    assert gone(rejected, gateway)
    assert result.failed == 1

    gateway.fail_head_for.clear()
    retry = run(gateway)

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.COMPLETED
    assert retry.completed == 1


def test_auth_error_while_checking_pending_aborts_run(stored, gateway):
    att = pending_created_at(stored, NOW - timedelta(hours=25))
    gateway.auth_broken = True

    with pytest.raises(StorageAuthError):
        run(gateway)

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.PENDING


@contextmanager
def row_locked_elsewhere(att):
    locked, release = threading.Event(), threading.Event()

    def hold_lock():
        try:
            with transaction.atomic():
                Attachment.objects.select_for_update().get(pk=att.pk)
                locked.set()
                release.wait(timeout=5)
        finally:
            connection.close()

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert locked.wait(timeout=5)
    try:
        yield
    finally:
        release.set()
        holder.join()


def test_maintenance_reports_counts(stored, gateway):
    pending_created_at(stored, NOW - timedelta(hours=25))
    pending_created_at(stored, NOW - timedelta(hours=25), body=b"GIF89a-not-png")
    missing = pending_created_at(stored, NOW - timedelta(hours=25))
    gateway.objects.pop(missing.s3_key)
    stored(status=Attachment.Status.DELETING)
    stored(status=Attachment.Status.REJECTED)
    failing = stored(status=Attachment.Status.REJECTED)
    gateway.fail_delete_for.add(failing.s3_key)
    locked = stored(status=Attachment.Status.REJECTED)

    with row_locked_elsewhere(locked):
        result = run(gateway)

    assert result == MaintenanceResult(
        processed=7,
        completed=1,
        purged=4,
        skipped=1,
        failed=1,
        deleting_remaining=1,
        outbox_deleted=0,
    )
    assert result.processed == result.completed + result.purged + result.skipped + result.failed


def test_concurrent_runs_do_not_double_process(stored, gateway):
    atts = [stored(status=Attachment.Status.REJECTED) for _ in range(20)]
    start = threading.Barrier(2)
    results = []

    def run_in_thread():
        try:
            start.wait(timeout=5)
            results.append(run_maintenance(gateway=gateway))
        finally:
            connection.close()

    threads = [threading.Thread(target=run_in_thread) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sum(r.purged for r in results) == len(atts)
    assert sum(r.failed for r in results) == 0
    assert AttachmentPurgeLog.objects.count() == len(atts)
    assert not Attachment.objects.exists()
    assert not gateway.objects
