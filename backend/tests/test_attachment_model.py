import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from django.db import IntegrityError

from attachments.models import Attachment

pytestmark = pytest.mark.django_db

Status = Attachment.Status


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create_user(username="uploader", password="pw")


def make_attachment(user, **fields) -> Attachment:
    return Attachment.objects.create(
        created_by=user,
        s3_key=fields.pop("s3_key", f"attachments/{user.pk}/{uuid.uuid4()}.png"),
        original_filename="photo.png",
        **fields,
    )


def test_completed_requires_uploaded_at(user):
    with pytest.raises(IntegrityError):
        make_attachment(user, status=Status.COMPLETED, uploaded_at=None)


@pytest.mark.parametrize("status", [Status.PENDING, Status.REJECTED])
def test_deleted_at_only_for_completed_or_deleting(user, status):
    with pytest.raises(IntegrityError):
        make_attachment(user, status=status, deleted_at=datetime.now(UTC))


@pytest.mark.parametrize("field", ["public_id", "s3_key"])
def test_public_id_and_s3_key_are_unique(user, field):
    first = make_attachment(user)

    with pytest.raises(IntegrityError):
        make_attachment(user, **{field: getattr(first, field)})


def test_timestamps_are_utc(user):
    kst = timezone(timedelta(hours=9))
    uploaded = datetime(2026, 10, 12, 9, 0, tzinfo=kst)
    make_attachment(user, status=Status.COMPLETED, uploaded_at=uploaded)

    saved = Attachment.objects.get()

    assert saved.uploaded_at == uploaded
    assert saved.uploaded_at.utcoffset() == timedelta(0)
    assert saved.created_at.utcoffset() == timedelta(0)
