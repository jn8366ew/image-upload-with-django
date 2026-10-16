from datetime import UTC, datetime

import pytest

from attachments.events.outbox import record_event
from attachments.exceptions import UploadRejected
from attachments.models import Attachment, EventOutbox
from attachments.services.completion import complete_upload, finalize_pending
from attachments.services.deletion import soft_delete
from attachments.services.maintenance import run_maintenance
from attachments.services.purge import purge_by_operator

PNG = b"\x89PNG\r\n\x1a\nbody"
NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
CLIENT = {"ip": "203.0.113.7", "user_agent": "Mozilla/5.0 test"}


def test_complete_writes_upload_completed_event(user, gateway, make_attachment):
    att = make_attachment()
    gateway.put(att.s3_key, PNG, "image/png")

    complete_upload(user, att.public_id, gateway=gateway, now=lambda: NOW, **CLIENT)

    event = EventOutbox.objects.get()
    assert (event.type, event.occurred_at, event.published_at) == (
        EventOutbox.Type.UPLOAD_COMPLETED,
        NOW,
        None,
    )
    assert event.payload == {
        "attachment_public_id": str(att.public_id),
        "user_id": user.pk,
        "ip": "203.0.113.7",
        "user_agent": "Mozilla/5.0 test",
        "requested_by": None,
    }


def test_concurrent_complete_writes_one_event(gateway, make_attachment):
    att = make_attachment()
    gateway.put(att.s3_key, PNG, "image/png")
    stale = Attachment.objects.get(pk=att.pk)

    finalize_pending(att, gateway=gateway, now=NOW, **CLIENT)
    result = finalize_pending(stale, gateway=gateway, now=NOW, **CLIENT)

    assert result.status == Attachment.Status.COMPLETED
    assert EventOutbox.objects.count() == 1


def test_reject_writes_upload_rejected_event(user, gateway, make_attachment):
    att = make_attachment()
    gateway.put(att.s3_key, b"<svg xmlns=", "image/png")

    with pytest.raises(UploadRejected):
        complete_upload(user, att.public_id, gateway=gateway, now=lambda: NOW, **CLIENT)

    event = EventOutbox.objects.get()
    assert (event.type, event.occurred_at) == (EventOutbox.Type.UPLOAD_REJECTED, NOW)
    assert (event.payload["ip"], event.payload["user_agent"]) == (
        "203.0.113.7",
        "Mozilla/5.0 test",
    )


def completed(make_attachment, gateway, **fields):
    att = make_attachment(status=Attachment.Status.COMPLETED, uploaded_at=NOW, **fields)
    gateway.put(att.s3_key, PNG, "image/png")
    return att


def test_download_writes_downloaded_event_with_ip_and_user_agent(api, gateway, make_attachment):
    att = completed(make_attachment, gateway)

    response = api.get(
        f"/api/attachments/{att.public_id}/download",
        REMOTE_ADDR="198.51.100.4",
        HTTP_USER_AGENT="Mozilla/5.0 download",
    )

    assert response.status_code == 200
    event = EventOutbox.objects.get()
    assert event.type == EventOutbox.Type.DOWNLOADED
    assert event.payload == {
        "attachment_public_id": str(att.public_id),
        "user_id": att.created_by_id,
        "ip": "198.51.100.4",
        "user_agent": "Mozilla/5.0 download",
        "requested_by": None,
    }


@pytest.mark.parametrize("case", ["other_user", "object_missing"])
def test_download_denied_writes_no_event(api, gateway, make_attachment, django_user_model, case):
    if case == "other_user":
        att = completed(
            make_attachment,
            gateway,
            owner=django_user_model.objects.create_user(username="other", password="pw"),
        )
    else:
        att = completed(make_attachment, gateway)
        gateway.objects.pop(att.s3_key)

    response = api.get(f"/api/attachments/{att.public_id}/download")

    assert response.status_code in (403, 404)
    assert not EventOutbox.objects.exists()


def test_soft_delete_writes_soft_deleted_event(user, gateway, make_attachment):
    att = completed(make_attachment, gateway)

    soft_delete(user, att.public_id, now=lambda: NOW, **CLIENT)

    event = EventOutbox.objects.get()
    assert (event.type, event.occurred_at) == (EventOutbox.Type.SOFT_DELETED, NOW)
    assert (event.payload["ip"], event.payload["user_agent"]) == (
        "203.0.113.7",
        "Mozilla/5.0 test",
    )


def test_repeated_soft_delete_writes_one_event(user, gateway, make_attachment):
    att = completed(make_attachment, gateway)

    soft_delete(user, att.public_id, now=lambda: NOW, **CLIENT)
    soft_delete(user, att.public_id, now=lambda: NOW, **CLIENT)

    assert EventOutbox.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_purge_by_batch_writes_purged_event_with_null_ip(gateway, make_attachment):
    att = make_attachment(status=Attachment.Status.REJECTED)

    run_maintenance(gateway=gateway, now=lambda: NOW)

    event = EventOutbox.objects.get()
    assert (event.type, event.occurred_at) == (EventOutbox.Type.PURGED, NOW)
    assert event.payload == {
        "attachment_public_id": str(att.public_id),
        "user_id": att.created_by_id,
        "ip": None,
        "user_agent": None,
        "requested_by": None,
    }


@pytest.mark.django_db(transaction=True)
def test_purge_by_ops_writes_requested_by(gateway, make_attachment, django_user_model):
    att = completed(make_attachment, gateway)
    operator = django_user_model.objects.create_user(username="ops", password="pw")

    purge_by_operator(att.public_id, operator_username="ops", gateway=gateway)

    event = EventOutbox.objects.get()
    assert event.type == EventOutbox.Type.PURGED
    assert event.payload["requested_by"] == operator.pk


class OutboxDown(Exception):
    pass


def failing_record_event(*args, **kwargs):
    raise OutboxDown


@pytest.mark.parametrize("case", ["complete", "reject", "soft_delete"])
def test_event_rolled_back_with_business_transaction(
    user, gateway, make_attachment, monkeypatch, case
):
    if case == "soft_delete":
        att = completed(make_attachment, gateway)
        monkeypatch.setattr("attachments.services.deletion.record_event", failing_record_event)
        call = lambda: soft_delete(user, att.public_id, **CLIENT)  # noqa: E731
    else:
        att = make_attachment()
        gateway.put(att.s3_key, PNG if case == "complete" else b"<svg", "image/png")
        monkeypatch.setattr("attachments.services.completion.record_event", failing_record_event)
        call = lambda: complete_upload(user, att.public_id, gateway=gateway, **CLIENT)  # noqa: E731
    before = Attachment.objects.values().get(pk=att.pk)

    with pytest.raises(OutboxDown):
        call()

    assert Attachment.objects.values().get(pk=att.pk) == before
    assert not EventOutbox.objects.exists()


def test_user_agent_truncated_to_512(make_attachment):
    att = make_attachment()

    event = record_event(
        EventOutbox.Type.DOWNLOADED, att, now=NOW, ip=None, user_agent="a" * 511 + "bc"
    )

    event.refresh_from_db()
    assert event.payload["user_agent"] == "a" * 511 + "b"
