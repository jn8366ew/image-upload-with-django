import logging
import time
from collections.abc import Callable
from datetime import datetime

from django.db import transaction
from django.utils import timezone
from pymongo.database import Database
from pymongo.errors import BulkWriteError, PyMongoError

from attachments.events.indexes import EVENTS_COLLECTION
from attachments.models import EventOutbox

logger = logging.getLogger(__name__)

BATCH_SIZE = 100
IDLE_SECONDS = 1
BACKOFF_START_SECONDS = 1
BACKOFF_MAX_SECONDS = 30
DUPLICATE_KEY = 11000


def relay_once(
    db: Database, *, batch_size: int = BATCH_SIZE, now: Callable[[], datetime] = timezone.now
) -> int:
    with transaction.atomic():
        rows = list(
            EventOutbox.objects.select_for_update(skip_locked=True)
            .filter(published_at__isnull=True)
            .order_by("id")[:batch_size]
        )
        if not rows:
            return 0
        try:
            db[EVENTS_COLLECTION].insert_many([_document(row) for row in rows], ordered=False)
        except BulkWriteError as e:
            if not _is_all_duplicates(e.details):
                raise
        EventOutbox.objects.filter(pk__in=[row.pk for row in rows]).update(published_at=now())
    return len(rows)


def _document(row: EventOutbox) -> dict:
    return {
        "event_id": str(row.event_id),
        "type": row.type,
        "occurred_at": row.occurred_at,
        **row.payload,
    }


def _is_all_duplicates(details: dict) -> bool:
    codes = [error["code"] for error in details.get("writeErrors", [])]
    return bool(codes) and all(code == DUPLICATE_KEY for code in codes)


def run_loop(db: Database, *, sleep=time.sleep, max_iterations: int | None = None) -> None:
    iterations = 0
    delay = BACKOFF_START_SECONDS
    while max_iterations is None or iterations < max_iterations:
        iterations += 1
        try:
            published = relay_once(db)
        except PyMongoError as e:
            if isinstance(e, BulkWriteError):
                logger.error("relay: write rejected by mongo, retrying in %ss: %s", delay, e)
            else:
                logger.warning("relay: mongo unavailable, retrying in %ss", delay)
            sleep(delay)
            delay = min(delay * 2, BACKOFF_MAX_SECONDS)
            continue
        delay = BACKOFF_START_SECONDS
        if published == 0:
            sleep(IDLE_SECONDS)
