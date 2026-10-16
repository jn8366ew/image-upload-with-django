import logging
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from attachments.events.outbox import record_event
from attachments.exceptions import (
    AttachmentNotFound,
    NotOwner,
    ObjectNotFound,
    StorageAuthError,
    StorageError,
    UploadNotReceived,
    UploadRejected,
)
from attachments.models import Attachment, EventOutbox
from attachments.storage.gateway import StorageGateway

logger = logging.getLogger(__name__)

SIGNATURES = {"image/png": b"\x89PNG\r\n\x1a\n", "image/jpeg": b"\xff\xd8\xff"}


def complete_upload(
    user,
    public_id: UUID,
    *,
    gateway: StorageGateway,
    ip: str | None,
    user_agent: str | None,
    now: Callable[[], datetime] = timezone.now,
) -> Attachment:
    attachment = (
        Attachment.objects.filter(public_id=public_id, deleted_at__isnull=True)
        .exclude(status=Attachment.Status.DELETING)
        .first()
    )
    if attachment is None:
        raise AttachmentNotFound(public_id)
    if attachment.created_by_id != user.pk:
        raise NotOwner(public_id)
    if attachment.status == Attachment.Status.COMPLETED:
        return attachment
    if attachment.status == Attachment.Status.REJECTED:
        raise UploadRejected("invalid_format")
    return finalize_pending(attachment, gateway=gateway, now=now(), ip=ip, user_agent=user_agent)


def finalize_pending(
    attachment: Attachment,
    *,
    gateway: StorageGateway,
    now: datetime,
    ip: str | None,
    user_agent: str | None,
) -> Attachment:
    try:
        declared = gateway.head(attachment.s3_key)
    except ObjectNotFound as e:
        raise UploadNotReceived(attachment.public_id) from e
    if not gateway.read_prefix(attachment.s3_key).startswith(SIGNATURES[declared]):
        _reject(attachment, gateway, now=now, ip=ip, user_agent=user_agent)
    with transaction.atomic():
        if _pending(attachment).update(status=Attachment.Status.COMPLETED, uploaded_at=now) == 1:
            record_event(
                EventOutbox.Type.UPLOAD_COMPLETED, attachment, now=now, ip=ip, user_agent=user_agent
            )
    attachment.refresh_from_db()
    return attachment


def _pending(attachment: Attachment):
    return Attachment.objects.filter(pk=attachment.pk, status=Attachment.Status.PENDING)


def _reject(
    attachment: Attachment,
    gateway: StorageGateway,
    *,
    now: datetime,
    ip: str | None,
    user_agent: str | None,
) -> None:
    with transaction.atomic():
        if _pending(attachment).update(status=Attachment.Status.REJECTED) == 1:
            record_event(
                EventOutbox.Type.UPLOAD_REJECTED, attachment, now=now, ip=ip, user_agent=user_agent
            )
    attachment.refresh_from_db()
    try:
        gateway.delete(attachment.s3_key)
    except StorageAuthError:
        logger.error("rejected upload %s: object delete auth failed", attachment.public_id)
    except StorageError:
        logger.warning("rejected upload %s: object delete failed", attachment.public_id)
    raise UploadRejected("invalid_format")
