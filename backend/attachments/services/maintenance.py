from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db.models import QuerySet
from django.utils import timezone

from attachments.exceptions import (
    StorageAuthError,
    StorageError,
    UploadNotReceived,
    UploadRejected,
)
from attachments.models import Attachment
from attachments.services.completion import finalize_pending
from attachments.services.purge import PurgeOutcome, purge
from attachments.storage.gateway import StorageGateway

PENDING_TTL = timedelta(hours=24)
SOFT_DELETE_TTL = timedelta(days=30)
RETENTION = timedelta(days=365)


@dataclass(frozen=True)
class MaintenanceResult:
    processed: int
    completed: int
    purged: int
    skipped: int
    failed: int
    deleting_remaining: int


def run_maintenance(
    *, gateway: StorageGateway, now: Callable[[], datetime] = timezone.now
) -> MaintenanceResult:
    at = now()
    counts: Counter[str] = Counter()
    _purge_all(Attachment.objects.filter(status=Attachment.Status.DELETING), gateway, counts, at)
    stale = Attachment.objects.filter(
        status=Attachment.Status.PENDING, created_at__lte=at - PENDING_TTL
    )
    for attachment in list(stale):
        try:
            finalize_pending(attachment, gateway=gateway, now=at, ip=None, user_agent=None)
            counts["completed"] += 1
        except UploadNotReceived:
            _purge_one(attachment.pk, gateway, counts, at)
        except UploadRejected:
            pass
        except StorageAuthError:
            raise
        except StorageError:
            counts["failed"] += 1
    _purge_all(Attachment.objects.filter(status=Attachment.Status.REJECTED), gateway, counts, at)
    _purge_all(
        Attachment.objects.filter(
            status=Attachment.Status.COMPLETED, deleted_at__lte=at - SOFT_DELETE_TTL
        ),
        gateway,
        counts,
        at,
    )
    _purge_all(
        Attachment.objects.filter(
            status=Attachment.Status.COMPLETED, uploaded_at__lte=at - RETENTION
        ),
        gateway,
        counts,
        at,
    )
    return MaintenanceResult(
        processed=counts.total(),
        completed=counts["completed"],
        purged=counts["purged"],
        skipped=counts["skipped"],
        failed=counts["failed"],
        deleting_remaining=Attachment.objects.filter(status=Attachment.Status.DELETING).count(),
    )


def _purge_all(
    targets: QuerySet[Attachment], gateway: StorageGateway, counts: Counter[str], at: datetime
) -> None:
    for attachment_id in list(targets.values_list("pk", flat=True)):
        _purge_one(attachment_id, gateway, counts, at)


def _purge_one(
    attachment_id: int, gateway: StorageGateway, counts: Counter[str], at: datetime
) -> None:
    try:
        outcome = purge(attachment_id, gateway=gateway, now=lambda: at)
    except StorageAuthError:
        raise
    except StorageError:
        counts["failed"] += 1
        return
    counts["purged" if outcome is PurgeOutcome.PURGED else "skipped"] += 1
