from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from attachments.events.outbox import record_event
from attachments.exceptions import AttachmentNotFound, NotOwner
from attachments.models import Attachment, EventOutbox


def soft_delete(
    user,
    public_id: UUID,
    *,
    ip: str | None,
    user_agent: str | None,
    now: Callable[[], datetime] = timezone.now,
) -> None:
    attachment = Attachment.objects.filter(
        public_id=public_id, status=Attachment.Status.COMPLETED
    ).first()
    if attachment is None:
        raise AttachmentNotFound(public_id)
    if attachment.created_by_id != user.pk:
        raise NotOwner(public_id)
    at = now()
    live = Attachment.objects.filter(pk=attachment.pk, deleted_at__isnull=True)
    with transaction.atomic():
        if live.update(deleted_at=at) == 1:
            record_event(
                EventOutbox.Type.SOFT_DELETED, attachment, now=at, ip=ip, user_agent=user_agent
            )
