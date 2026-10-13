from dataclasses import dataclass
from uuid import UUID, uuid4

from attachments.exceptions import UploadRejected
from attachments.models import Attachment
from attachments.storage.gateway import StorageGateway

EXTENSIONS = {"image/png": ".png", "image/jpeg": ".jpg"}
MAX_FILES_PER_REQUEST = 10
MAX_BYTES = 2_621_440
PRESIGN_EXPIRES = 300


@dataclass(frozen=True)
class UploadRequest:
    client_ref: str
    filename: str
    content_type: str
    size: int


@dataclass(frozen=True)
class PresignedUpload:
    client_ref: str
    public_id: UUID
    url: str
    fields: dict[str, str]


def presign_uploads(
    user, files: list[UploadRequest], *, gateway: StorageGateway
) -> list[PresignedUpload]:
    if len(files) > MAX_FILES_PER_REQUEST:
        raise UploadRejected("too_many_files")
    for f in files:
        if f.content_type not in EXTENSIONS:
            raise UploadRejected("disallowed_type", f.client_ref)
        if f.size > MAX_BYTES:
            raise UploadRejected("too_large", f.client_ref)

    result = []
    for f in files:
        public_id = uuid4()
        key = f"attachments/{user.pk}/{public_id}{EXTENSIONS[f.content_type]}"
        Attachment.objects.create(
            public_id=public_id, created_by=user, s3_key=key, original_filename=f.filename
        )
        post = gateway.presign_post(key, f.content_type, MAX_BYTES, PRESIGN_EXPIRES)
        result.append(PresignedUpload(f.client_ref, public_id, post.url, post.fields))
    return result
