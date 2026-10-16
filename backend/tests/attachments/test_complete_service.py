from datetime import UTC, datetime

import pytest

from attachments.exceptions import UploadRejected
from attachments.models import Attachment
from attachments.services.completion import complete_upload

PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"jpeg-body"
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
NO_CLIENT = {"ip": None, "user_agent": None}


def test_complete_png_signature_marks_completed(user, gateway, make_attachment):
    att = make_attachment(ext=".png")
    gateway.put(att.s3_key, PNG, "image/png")

    result = complete_upload(user, att.public_id, gateway=gateway, now=lambda: NOW, **NO_CLIENT)

    att.refresh_from_db()
    assert result.status == att.status == Attachment.Status.COMPLETED
    assert att.uploaded_at == NOW


def test_complete_jpeg_signature_marks_completed(user, gateway, make_attachment):
    att = make_attachment(ext=".jpg")
    gateway.put(att.s3_key, JPEG, "image/jpeg")

    complete_upload(user, att.public_id, gateway=gateway, now=lambda: NOW, **NO_CLIENT)

    att.refresh_from_db()
    assert (att.status, att.uploaded_at) == (Attachment.Status.COMPLETED, NOW)


def test_complete_mismatched_signature_rejects_and_deletes_object(user, gateway, make_attachment):
    att = make_attachment(ext=".png")
    gateway.put(att.s3_key, b"<svg xmlns=", "image/png")

    with pytest.raises(UploadRejected) as exc:
        complete_upload(user, att.public_id, gateway=gateway, **NO_CLIENT)

    assert exc.value.reason == "invalid_format"
    att.refresh_from_db()
    assert (att.status, att.uploaded_at) == (Attachment.Status.REJECTED, None)
    assert att.s3_key not in gateway.objects


@pytest.mark.parametrize(("declared", "body"), [("image/png", JPEG), ("image/jpeg", PNG)])
def test_complete_signature_must_match_declared_type(
    user, gateway, make_attachment, declared, body
):
    att = make_attachment()
    gateway.put(att.s3_key, body, declared)

    with pytest.raises(UploadRejected):
        complete_upload(user, att.public_id, gateway=gateway, **NO_CLIENT)

    att.refresh_from_db()
    assert att.status == Attachment.Status.REJECTED


@pytest.mark.parametrize(("declared", "body"), [("image/png", PNG[:4]), ("image/jpeg", JPEG[:2])])
def test_complete_file_shorter_than_signature_rejects(
    user, gateway, make_attachment, declared, body
):
    att = make_attachment()
    gateway.put(att.s3_key, body, declared)

    with pytest.raises(UploadRejected):
        complete_upload(user, att.public_id, gateway=gateway, **NO_CLIENT)

    att.refresh_from_db()
    assert att.status == Attachment.Status.REJECTED


def test_complete_reject_keeps_rejected_when_delete_fails(user, gateway, make_attachment, caplog):
    att = make_attachment()
    gateway.put(att.s3_key, b"not-an-image", "image/png")
    gateway.fail_delete_for.add(att.s3_key)

    with pytest.raises(UploadRejected):
        complete_upload(user, att.public_id, gateway=gateway, **NO_CLIENT)

    att.refresh_from_db()
    assert att.status == Attachment.Status.REJECTED
    assert any(r.levelname == "WARNING" and str(att.public_id) in r.message for r in caplog.records)


def test_complete_reject_logs_error_when_delete_auth_fails(user, gateway, make_attachment, caplog):
    att = make_attachment()
    gateway.put(att.s3_key, b"not-an-image", "image/png")
    real_delete = gateway.delete

    def auth_failing_delete(key):
        gateway.auth_broken = True
        real_delete(key)

    gateway.delete = auth_failing_delete

    with pytest.raises(UploadRejected):
        complete_upload(user, att.public_id, gateway=gateway, **NO_CLIENT)

    att.refresh_from_db()
    assert att.status == Attachment.Status.REJECTED
    assert any(r.levelname == "ERROR" and str(att.public_id) in r.message for r in caplog.records)
