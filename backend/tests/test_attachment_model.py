import uuid

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
