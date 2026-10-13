from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from django.utils import timezone

from attachments.exceptions import AttachmentNotFound, NotOwner
from attachments.models import Attachment


def soft_delete(user, public_id: UUID, *, now: Callable[[], datetime] = timezone.now) -> None:
    attachment = Attachment.objects.filter(
        public_id=public_id, status=Attachment.Status.COMPLETED
    ).first()
    if attachment is None:
        raise AttachmentNotFound(public_id)
    if attachment.created_by_id != user.pk:
        raise NotOwner(public_id)
    Attachment.objects.filter(pk=attachment.pk, deleted_at__isnull=True).update(deleted_at=now())
