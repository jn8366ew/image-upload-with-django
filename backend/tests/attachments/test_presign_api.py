import pytest
from rest_framework.test import APIClient

from attachments.models import Attachment

URL = "/api/attachments/presign"


def png(client_ref="a", **overrides):
    return {
        "client_ref": client_ref,
        "filename": "cat.png",
        "content_type": "image/png",
        "size": 1000,
        **overrides,
    }


@pytest.mark.django_db
def test_presign_requires_authentication():
    response = APIClient().post(URL, {"files": [png()]}, format="json")

    assert response.status_code == 403


def test_presign_rejected_request_creates_no_rows(api):
    response = api.post(
        URL, {"files": [png("ok"), png("bad", content_type="image/heic")]}, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "disallowed_type", "client_ref": "bad"}
    assert not Attachment.objects.exists()


@pytest.mark.parametrize(
    "filename",
    ["a" * 252 + ".png", "", "a\x00.png", "a\n.png"],
    ids=["over_255", "empty", "nul", "newline"],
)
def test_presign_rejects_invalid_filename(api, filename):
    response = api.post(URL, {"files": [png(filename=filename)]}, format="json")

    assert response.status_code == 400
    assert not Attachment.objects.exists()


def test_presign_response_echoes_client_ref_with_public_id(api):
    response = api.post(
        URL, {"files": [png("x1"), png("x2", content_type="image/jpeg")]}, format="json"
    )

    assert response.status_code == 201
    uploads = response.json()["uploads"]
    rows = {str(r.public_id): r for r in Attachment.objects.all()}
    assert [u["client_ref"] for u in uploads] == ["x1", "x2"]
    for u in uploads:
        assert set(u) == {"client_ref", "public_id", "url", "fields"}
        assert u["public_id"] in rows
        assert u["fields"]["key"] == rows[u["public_id"]].s3_key


def test_presign_throttled_after_limit(api):
    for _ in range(60):
        assert api.post(URL, {"files": [png()]}, format="json").status_code == 201

    assert api.post(URL, {"files": [png()]}, format="json").status_code == 429
