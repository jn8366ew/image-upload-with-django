from enum import Enum
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import transaction

from attachments.exceptions import AttachmentNotFound, OperatorNotAllowed
from attachments.models import Attachment, AttachmentPurgeLog
from attachments.storage.gateway import StorageGateway


class PurgeOutcome(Enum):
    PURGED = "purged"
    ALREADY_GONE = "already_gone"
    SKIPPED_LOCKED = "skipped_locked"


def purge(attachment_id: int, *, gateway: StorageGateway, requested_by=None) -> PurgeOutcome:
    if transaction.get_connection().in_atomic_block:
        raise RuntimeError("purge must not run inside an outer transaction")
    with transaction.atomic():
        attachment = (
            Attachment.objects.select_for_update(skip_locked=True).filter(pk=attachment_id).first()
        )
        if attachment is None:
            if Attachment.objects.filter(pk=attachment_id).exists():
                return PurgeOutcome.SKIPPED_LOCKED
            return PurgeOutcome.ALREADY_GONE
        if attachment.status != Attachment.Status.DELETING:
            _start_purge(attachment, requested_by)
    gateway.delete(attachment.s3_key)
    deleted, _ = Attachment.objects.filter(pk=attachment_id).delete()
    return PurgeOutcome.PURGED if deleted == 1 else PurgeOutcome.ALREADY_GONE


def purge_by_operator(
    public_id: UUID, *, operator_username: str, gateway: StorageGateway
) -> PurgeOutcome:
    operator = get_user_model().objects.filter(username=operator_username, is_active=True).first()
    if operator is None:
        raise OperatorNotAllowed(operator_username)
    attachment = Attachment.objects.filter(public_id=public_id).first()
    if attachment is None:
        raise AttachmentNotFound(public_id)
    return purge(attachment.pk, gateway=gateway, requested_by=operator)


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
