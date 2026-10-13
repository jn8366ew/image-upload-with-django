import logging
from dataclasses import dataclass
from uuid import UUID

from attachments.exceptions import AttachmentNotFound, NotOwner, ObjectNotFound
from attachments.models import Attachment
from attachments.storage.gateway import StorageGateway, StoredObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Download:
    attachment: Attachment
    stored: StoredObject


def open_download(user, public_id: UUID, *, gateway: StorageGateway) -> Download:
    attachment = Attachment.objects.filter(
        public_id=public_id, status=Attachment.Status.COMPLETED, deleted_at__isnull=True
    ).first()
    if attachment is None:
        raise AttachmentNotFound(public_id)
    if attachment.created_by_id != user.pk:
        raise NotOwner(public_id)
    try:
        stored = gateway.open(attachment.s3_key)
    except ObjectNotFound as e:
        logger.warning("download %s: object missing in storage", public_id)
        raise AttachmentNotFound(public_id) from e
    return Download(attachment, stored)
