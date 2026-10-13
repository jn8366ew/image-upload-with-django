import uuid
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attachments.models import Attachment


def detail_url(public_id):
    return f"/api/attachments/{public_id}"


def completed(make_attachment, **fields):
    return make_attachment(status=Attachment.Status.COMPLETED, uploaded_at=timezone.now(), **fields)


def test_soft_delete_requires_authentication(make_attachment):
    att = completed(make_attachment)

    assert APIClient().delete(detail_url(att.public_id)).status_code == 403


def test_soft_delete_sets_deleted_at(api, make_attachment):
    att = completed(make_attachment)

    response = api.delete(detail_url(att.public_id))

    assert response.status_code == 204
    att.refresh_from_db()
    assert att.deleted_at is not None


def test_soft_delete_forbidden_for_non_uploader(api, make_attachment, django_user_model):
    other = django_user_model.objects.create_user(username="other", password="pw")
    att = completed(make_attachment, owner=other)

    response = api.delete(detail_url(att.public_id))

    assert response.status_code == 403
    att.refresh_from_db()
    assert att.deleted_at is None


@pytest.mark.parametrize(
    "status",
    [Attachment.Status.PENDING, Attachment.Status.REJECTED, Attachment.Status.DELETING, None],
)
def test_soft_delete_unknown_or_incomplete_returns_404(api, make_attachment, status):
    public_id = uuid.uuid4() if status is None else make_attachment(status=status).public_id

    assert api.delete(detail_url(public_id)).status_code == 404


def test_soft_delete_is_idempotent(api, make_attachment):
    first = timezone.now() - timedelta(days=3)
    att = completed(make_attachment, deleted_at=first)

    response = api.delete(detail_url(att.public_id))

    assert response.status_code == 204
    att.refresh_from_db()
    assert att.deleted_at == first
