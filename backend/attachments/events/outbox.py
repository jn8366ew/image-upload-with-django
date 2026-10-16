from datetime import datetime

from attachments.models import Attachment, EventOutbox

USER_AGENT_MAX = 512


def record_event(
    type: EventOutbox.Type,
    attachment: Attachment,
    *,
    now: datetime,
    ip: str | None,
    user_agent: str | None,
    requested_by_id: int | None = None,
) -> EventOutbox:
    return EventOutbox.objects.create(
        type=type,
        occurred_at=now,
        payload={
            "attachment_public_id": str(attachment.public_id),
            "user_id": attachment.created_by_id,
            "ip": ip,
            "user_agent": user_agent[:USER_AGENT_MAX] if user_agent else user_agent,
            "requested_by": requested_by_id,
        },
    )
