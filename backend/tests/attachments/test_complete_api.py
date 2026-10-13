import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attachments.models import Attachment


def complete_url(public_id):
    return f"/api/attachments/{public_id}/complete"


@pytest.mark.django_db
def test_complete_requires_authentication():
    response = APIClient().post(complete_url(uuid.uuid4()))

    assert response.status_code == 403


def test_complete_forbidden_for_other_user(api, make_attachment, django_user_model):
    other = django_user_model.objects.create_user(username="other", password="pw")
    att = make_attachment(owner=other)

    response = api.post(complete_url(att.public_id))

    assert response.status_code == 403


@pytest.mark.parametrize("case", ["unknown", "soft_deleted", "deleting"])
def test_complete_unknown_or_deleted_returns_404(api, make_attachment, case):
    now = timezone.now()
    public_id = {
        "unknown": lambda: uuid.uuid4(),
        "soft_deleted": lambda: (
            make_attachment(
                status=Attachment.Status.COMPLETED, uploaded_at=now, deleted_at=now
            ).public_id
        ),
        "deleting": lambda: make_attachment(status=Attachment.Status.DELETING).public_id,
    }[case]()

    response = api.post(complete_url(public_id))

    assert response.status_code == 404


def test_complete_missing_object_returns_409_and_stays_pending(api, make_attachment):
    att = make_attachment()

    response = api.post(complete_url(att.public_id))

    assert response.status_code == 409
    att.refresh_from_db()
    assert att.status == Attachment.Status.PENDING


def test_complete_rejected_again_returns_400(api, gateway, make_attachment):
    att = make_attachment()
    gateway.put(att.s3_key, b"not-an-image", "image/png")

    first = api.post(complete_url(att.public_id))
    second = api.post(complete_url(att.public_id))

    assert (first.status_code, first.json()) == (400, {"detail": "invalid_format"})
    assert (second.status_code, second.json()) == (400, {"detail": "invalid_format"})


def test_complete_is_idempotent(api, gateway, make_attachment):
    att = make_attachment()
    gateway.put(att.s3_key, b"\x89PNG\r\n\x1a\nbody", "image/png")

    first = api.post(complete_url(att.public_id))
    att.refresh_from_db()
    uploaded_at = att.uploaded_at
    second = api.post(complete_url(att.public_id))

    expected = {"public_id": str(att.public_id), "status": "COMPLETED"}
    assert (first.status_code, first.json()) == (200, expected)
    assert (second.status_code, second.json()) == (200, expected)
    att.refresh_from_db()
    assert att.uploaded_at == uploaded_at


def test_complete_response_has_no_s3_key_or_url(api, gateway, make_attachment):
    att = make_attachment()
    gateway.put(att.s3_key, b"\x89PNG\r\n\x1a\nbody", "image/png")

    body = api.post(complete_url(att.public_id)).content.decode()

    for leaked in (att.s3_key, gateway.bucket, "amazonaws.com", "attachments/"):
        assert leaked not in body
