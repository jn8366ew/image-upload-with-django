from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from attachments.models import Attachment

URL = "/api/attachments"


@pytest.mark.django_db
def test_list_requires_authentication():
    assert APIClient().get(URL).status_code == 403


@pytest.fixture
def completed(make_attachment):
    def make(owner=None, uploaded_at=None, **fields):
        return make_attachment(
            owner=owner,
            status=Attachment.Status.COMPLETED,
            uploaded_at=uploaded_at or timezone.now(),
            **fields,
        )

    return make


def ids(response):
    return [item["public_id"] for item in response.json()["results"]]


def test_list_returns_only_own_attachments(api, completed, django_user_model):
    mine = completed()
    completed(owner=django_user_model.objects.create_user(username="other", password="pw"))

    assert ids(api.get(URL)) == [str(mine.public_id)]


def test_list_excludes_pending_rejected_deleting(api, completed, make_attachment):
    visible = completed()
    for status in (
        Attachment.Status.PENDING,
        Attachment.Status.REJECTED,
        Attachment.Status.DELETING,
    ):
        make_attachment(status=status)

    assert ids(api.get(URL)) == [str(visible.public_id)]


def test_list_excludes_soft_deleted(api, completed):
    visible = completed()
    completed(deleted_at=timezone.now())

    assert ids(api.get(URL)) == [str(visible.public_id)]


def test_list_ordered_by_uploaded_at_desc(api, completed):
    t = timezone.now()
    oldest = completed(uploaded_at=t - timedelta(days=2))
    newest = completed(uploaded_at=t)
    middle = completed(uploaded_at=t - timedelta(days=1))
    newest_tie = completed(uploaded_at=t)

    assert ids(api.get(URL)) == [str(a.public_id) for a in (newest_tie, newest, middle, oldest)]


def test_list_items_expose_only_public_fields(api, completed):
    att = completed(uploaded_at=datetime(2026, 10, 13, 9, 0, tzinfo=UTC))

    assert api.get(URL).json()["results"] == [
        {
            "public_id": str(att.public_id),
            "original_filename": att.original_filename,
            "uploaded_at": "2026-10-13T09:00:00Z",
        }
    ]


def test_list_response_has_no_s3_key_bucket_or_s3_domain(api, completed, gateway):
    att = completed()

    body = api.get(URL).content.decode()

    for leaked in (att.s3_key, gateway.bucket, "amazonaws.com", "attachments/"):
        assert leaked not in body


def test_list_paginates_with_cursor(api, completed):
    t = timezone.now()
    created = [completed(uploaded_at=t - timedelta(minutes=i)) for i in range(51)]

    first = api.get(URL).json()
    second = api.get(first["next"]).json()

    assert len(first["results"]) == 50
    assert second["next"] is None
    seen = [item["public_id"] for item in first["results"] + second["results"]]
    assert seen == [str(a.public_id) for a in created]
