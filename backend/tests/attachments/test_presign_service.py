import base64
import json

import pytest

from attachments.exceptions import UploadRejected
from attachments.models import Attachment
from attachments.services.uploads import UploadRequest, presign_uploads


def upload(client_ref="a", **overrides):
    return UploadRequest(
        **{
            "client_ref": client_ref,
            "filename": "cat.png",
            "content_type": "image/png",
            "size": 1000,
            **overrides,
        }
    )


def test_presign_creates_pending_per_file(user, gateway):
    presign_uploads(
        user,
        [
            upload("a", filename="cat.png"),
            upload("b", filename="dog.jpg", content_type="image/jpeg"),
        ],
        gateway=gateway,
    )

    rows = Attachment.objects.order_by("original_filename")
    assert [(r.original_filename, r.status, r.created_by) for r in rows] == [
        ("cat.png", Attachment.Status.PENDING, user),
        ("dog.jpg", Attachment.Status.PENDING, user),
    ]


def test_presign_key_is_scoped_to_user(user, gateway):
    presign_uploads(user, [upload()], gateway=gateway)

    row = Attachment.objects.get()
    assert row.s3_key.startswith(f"attachments/{user.pk}/{row.public_id}")


@pytest.mark.parametrize(
    ("filename", "content_type", "ext"),
    [("photo.jpeg", "image/png", ".png"), ("photo.png", "image/jpeg", ".jpg")],
)
def test_presign_key_extension_matches_mime(user, gateway, filename, content_type, ext):
    presign_uploads(user, [upload(filename=filename, content_type=content_type)], gateway=gateway)

    row = Attachment.objects.get()
    assert row.s3_key == f"attachments/{user.pk}/{row.public_id}{ext}"


def test_presign_policy_contains_size_type_key_conditions(user, gateway):
    result = presign_uploads(user, [upload(content_type="image/jpeg")], gateway=gateway)

    assert len(result) == 1
    policy = json.loads(base64.b64decode(result[0].fields["policy"]))
    row = Attachment.objects.get()
    assert {"key": row.s3_key} in policy["conditions"]
    assert {"Content-Type": "image/jpeg"} in policy["conditions"]
    assert ["content-length-range", 1, 2_621_440] in policy["conditions"]


@pytest.mark.parametrize("content_type", ["image/heic", "image/svg+xml"])
def test_presign_rejects_disallowed_type(user, gateway, content_type):
    with pytest.raises(UploadRejected) as exc:
        presign_uploads(user, [upload("bad", content_type=content_type)], gateway=gateway)

    assert (exc.value.reason, exc.value.client_ref) == ("disallowed_type", "bad")


def test_presign_rejects_oversized_file(user, gateway):
    presign_uploads(user, [upload("max", size=2_621_440)], gateway=gateway)

    with pytest.raises(UploadRejected) as exc:
        presign_uploads(user, [upload("big", size=2_621_441)], gateway=gateway)

    assert (exc.value.reason, exc.value.client_ref) == ("too_large", "big")


def test_presign_rejects_too_many_files(user, gateway):
    presign_uploads(user, [upload(str(i)) for i in range(10)], gateway=gateway)

    with pytest.raises(UploadRejected) as exc:
        presign_uploads(user, [upload(str(i)) for i in range(11)], gateway=gateway)

    assert exc.value.reason == "too_many_files"
