import threading
from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.utils import timezone

from attachments.exceptions import StorageError
from attachments.models import Attachment, AttachmentPurgeLog
from attachments.services.purge import purge

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def stored(make_attachment, gateway):
    def make(**fields):
        fields.setdefault("status", Attachment.Status.COMPLETED)
        fields.setdefault("uploaded_at", timezone.now())
        att = make_attachment(**fields)
        gateway.put(att.s3_key, b"\x89PNG\r\n\x1a\nbody", "image/png")
        return att

    return make


def logs_for(att):
    return AttachmentPurgeLog.objects.filter(attachment_public_id=att.public_id)


def test_purge_marks_deleting_and_writes_log_before_storage_call(stored, gateway, monkeypatch):
    att = stored()
    seen = {}
    real_delete = gateway.delete

    def spy(key):
        seen["status"] = Attachment.objects.get(pk=att.pk).status
        seen["logs"] = logs_for(att).count()
        real_delete(key)

    monkeypatch.setattr(gateway, "delete", spy)

    assert purge(att.pk, gateway=gateway) is True
    assert seen == {"status": Attachment.Status.DELETING, "logs": 1}


def test_purge_log_copies_uploaded_at_and_deleted_at(stored, gateway):
    uploaded = timezone.now() - timedelta(days=40)
    deleted = timezone.now() - timedelta(days=31)
    att = stored(uploaded_at=uploaded, deleted_at=deleted)

    purge(att.pk, gateway=gateway)

    log = logs_for(att).get()
    assert (log.uploaded_at, log.deleted_at) == (uploaded, deleted)


def test_purge_deletes_object_then_row(stored, gateway):
    att = stored()

    purge(att.pk, gateway=gateway)

    assert att.s3_key not in gateway.objects
    assert not Attachment.objects.filter(pk=att.pk).exists()


def test_purge_storage_failure_keeps_deleting_row(stored, gateway):
    att = stored()
    gateway.fail_delete_for.add(att.s3_key)

    with pytest.raises(StorageError):
        purge(att.pk, gateway=gateway)

    att.refresh_from_db()
    assert att.status == Attachment.Status.DELETING
    assert logs_for(att).count() == 1


def test_purge_retry_does_not_duplicate_log(stored, gateway):
    att = stored()
    gateway.fail_delete_for.add(att.s3_key)
    with pytest.raises(StorageError):
        purge(att.pk, gateway=gateway)
    gateway.fail_delete_for.clear()

    assert purge(att.pk, gateway=gateway) is True

    assert logs_for(att).count() == 1
    assert att.s3_key not in gateway.objects
    assert not Attachment.objects.filter(pk=att.pk).exists()


def test_purge_skips_missing_row(gateway):
    assert purge(999_999, gateway=gateway) is False
    assert not AttachmentPurgeLog.objects.exists()


def test_purge_skips_row_locked_by_another_transaction(stored, gateway):
    att = stored()
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
        result = purge(att.pk, gateway=gateway)
    finally:
        release.set()
        holder.join()

    assert result is False
    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.COMPLETED
    assert att.s3_key in gateway.objects


def test_purge_inside_atomic_raises_runtime_error(stored, gateway):
    att = stored()

    with pytest.raises(RuntimeError), transaction.atomic():
        purge(att.pk, gateway=gateway)

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.COMPLETED
    assert att.s3_key in gateway.objects


def test_purge_records_requested_by_for_ops(stored, gateway, django_user_model):
    operator = django_user_model.objects.create_user(username="ops", password="pw")
    att = stored()

    purge(att.pk, gateway=gateway, requested_by=operator)

    assert logs_for(att).get().requested_by_id == operator.pk
