from django.db.models import QuerySet

from attachments.models import Attachment


def list_user_attachments(user) -> QuerySet[Attachment]:
    return Attachment.objects.filter(
        created_by=user, status=Attachment.Status.COMPLETED, deleted_at__isnull=True
    )
