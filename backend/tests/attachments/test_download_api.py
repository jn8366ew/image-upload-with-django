import uuid

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attachments.models import Attachment


def download_url(public_id):
    return f"/api/attachments/{public_id}/download"


@pytest.mark.django_db
def test_download_requires_authentication():
    assert APIClient().get(download_url(uuid.uuid4())).status_code == 403


@pytest.fixture
def stored(make_attachment, gateway):
    def make(owner=None, body=b"\x89PNG\r\n\x1a\nbody", content_type="image/png", **fields):
        fields.setdefault("status", Attachment.Status.COMPLETED)
        fields.setdefault("uploaded_at", timezone.now())
        att = make_attachment(owner=owner, **fields)
        gateway.put(att.s3_key, body, content_type)
        return att

    return make


def test_download_forbidden_for_other_user(api, stored, django_user_model):
    att = stored(owner=django_user_model.objects.create_user(username="other", password="pw"))

    assert api.get(download_url(att.public_id)).status_code == 403


def test_download_soft_deleted_returns_404(api, stored):
    att = stored(deleted_at=timezone.now())

    assert api.get(download_url(att.public_id)).status_code == 404


@pytest.mark.parametrize("status", ["PENDING", "REJECTED", "DELETING", "unknown"])
def test_download_pending_returns_404(api, stored, status):
    if status == "unknown":
        public_id = uuid.uuid4()
    else:
        public_id = stored(status=status, uploaded_at=None).public_id

    assert api.get(download_url(public_id)).status_code == 404


def test_download_streams_object_bytes(api, stored):
    body = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 100
    att = stored(body=body, content_type="image/jpeg")

    response = api.get(download_url(att.public_id))

    assert response.status_code == 200
    assert response.streaming
    assert b"".join(response.streaming_content) == body


def test_download_sets_attachment_disposition_with_original_filename(api, stored):
    att = stored(original_filename="고양이 사진.png")

    response = api.get(download_url(att.public_id))

    assert response["Content-Disposition"] == (
        "attachment; filename*=utf-8''%EA%B3%A0%EC%96%91%EC%9D%B4%20%EC%82%AC%EC%A7%84.png"
    )


def test_download_sets_content_type_from_object(api, stored):
    att = stored(original_filename="looks-like.png", content_type="image/jpeg")

    response = api.get(download_url(att.public_id))

    assert response["Content-Type"] == "image/jpeg"


def test_download_sets_nosniff_and_no_store(api, stored):
    att = stored()

    response = api.get(download_url(att.public_id))

    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Cache-Control"] == "private, no-store"


def test_download_missing_object_returns_404_and_logs_warning(api, stored, gateway, caplog):
    att = stored()
    gateway.objects.clear()

    response = api.get(download_url(att.public_id))

    assert response.status_code == 404
    assert any(r.levelname == "WARNING" and str(att.public_id) in r.message for r in caplog.records)


def test_download_response_has_no_redirect_or_s3_url(api, stored, gateway):
    att = stored()

    response = api.get(download_url(att.public_id))

    assert response.status_code == 200
    exposed = " ".join(f"{k}: {v}" for k, v in response.items())
    exposed += b"".join(response.streaming_content).decode("latin-1")
    for leaked in (att.s3_key, gateway.bucket, "amazonaws.com"):
        assert leaked not in exposed
