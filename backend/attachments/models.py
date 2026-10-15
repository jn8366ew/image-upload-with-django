from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models import Q


class Attachment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING"
        COMPLETED = "COMPLETED"
        REJECTED = "REJECTED"
        DELETING = "DELETING"

    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attachments"
    )
    s3_key = models.CharField(max_length=512, unique=True)
    original_filename = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    created_at = models.DateTimeField(auto_now_add=True)
    uploaded_at = models.DateTimeField(null=True)
    deleted_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(status="COMPLETED") | Q(uploaded_at__isnull=False),
                name="att_completed_has_uploaded_at",
            ),
            models.CheckConstraint(
                condition=Q(deleted_at__isnull=True) | Q(status__in=["COMPLETED", "DELETING"]),
                name="att_deleted_at_only_completed_or_deleting",
            ),
        ]
        indexes = [
            models.Index(
                fields=["created_at"], name="att_pending_idx", condition=Q(status="PENDING")
            ),
            models.Index(
                fields=["deleted_at"], name="att_softdel_idx", condition=Q(deleted_at__isnull=False)
            ),
            models.Index(
                fields=["uploaded_at"], name="att_expire_idx", condition=Q(status="COMPLETED")
            ),
            models.Index(
                fields=["created_by", "uploaded_at"],
                name="att_list_idx",
                condition=Q(status="COMPLETED", deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        return str(self.public_id)


class AttachmentPurgeLog(models.Model):
    attachment_public_id = models.UUIDField()
    created_by_id = models.BigIntegerField()
    s3_key = models.CharField(max_length=512)
    original_filename = models.CharField(max_length=255)
    uploaded_at = models.DateTimeField(null=True)
    deleted_at = models.DateTimeField(null=True)
    requested_by_id = models.BigIntegerField(null=True)
    purged_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return str(self.attachment_public_id)


class EventOutbox(models.Model):
    class Type(models.TextChoices):
        UPLOAD_COMPLETED = "UPLOAD_COMPLETED"
        UPLOAD_REJECTED = "UPLOAD_REJECTED"
        DOWNLOADED = "DOWNLOADED"
        SOFT_DELETED = "SOFT_DELETED"
        PURGED = "PURGED"

    event_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    type = models.CharField(max_length=32, choices=Type.choices)
    payload = models.JSONField()
    occurred_at = models.DateTimeField()
    published_at = models.DateTimeField(null=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["id"],
                name="outbox_unpublished_idx",
                condition=Q(published_at__isnull=True),
            ),
            models.Index(
                fields=["published_at"],
                name="outbox_published_idx",
                condition=Q(published_at__isnull=False),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.type} {self.event_id}"
