from django.db import transaction

from attachments.models import Attachment, AttachmentPurgeLog
from attachments.storage.gateway import StorageGateway


def purge(attachment_id: int, *, gateway: StorageGateway, requested_by=None) -> bool:
    if transaction.get_connection().in_atomic_block:
        raise RuntimeError("purge must not run inside an outer transaction")
    with transaction.atomic():
        attachment = (
            Attachment.objects.select_for_update(skip_locked=True).filter(pk=attachment_id).first()
        )
        if attachment is None:
            return False
        if attachment.status != Attachment.Status.DELETING:
            _start_purge(attachment, requested_by)
    gateway.delete(attachment.s3_key)
    Attachment.objects.filter(pk=attachment_id).delete()
    return True


def _start_purge(attachment: Attachment, requested_by) -> None:
    attachment.status = Attachment.Status.DELETING
    attachment.save(update_fields=["status"])
    AttachmentPurgeLog.objects.create(
        attachment_public_id=attachment.public_id,
        created_by_id=attachment.created_by_id,
        s3_key=attachment.s3_key,
        original_filename=attachment.original_filename,
        uploaded_at=attachment.uploaded_at,
        deleted_at=attachment.deleted_at,
        requested_by_id=requested_by.pk if requested_by else None,
    )
