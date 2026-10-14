import uuid
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from attachments.models import Attachment, AttachmentPurgeLog
from attachments.services.purge import PurgeOutcome

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def command_gateway(gateway, monkeypatch):
    monkeypatch.setattr(
        "attachments.management.commands.purge_attachment.build_s3_gateway",
        lambda: gateway,
    )
    return gateway


@pytest.fixture
def operator(django_user_model):
    return django_user_model.objects.create_user(username="ops", password="pw")


def run(public_id, operator="ops"):
    out = StringIO()
    call_command(
        "purge_attachment", "--public-id", str(public_id), "--operator", operator, stdout=out
    )
    return out.getvalue()


def test_purge_command_hard_deletes_immediately(command_gateway, make_attachment, operator):
    att = make_attachment(status=Attachment.Status.COMPLETED, uploaded_at=timezone.now())
    command_gateway.put(att.s3_key, b"body", "image/png")

    out = run(att.public_id)

    assert "삭제함" in out
    assert not Attachment.objects.filter(pk=att.pk).exists()
    assert att.s3_key not in command_gateway.objects


def test_purge_command_records_operator(command_gateway, make_attachment, operator):
    att = make_attachment()

    run(att.public_id)

    log = AttachmentPurgeLog.objects.get(attachment_public_id=att.public_id)
    assert log.requested_by_id == operator.pk


def test_purge_command_unknown_id_fails_cleanly(command_gateway, make_attachment, operator):
    other = make_attachment()

    with pytest.raises(CommandError):
        run(uuid.uuid4())

    assert Attachment.objects.get(pk=other.pk).status == Attachment.Status.PENDING


def test_purge_command_unknown_operator_fails(command_gateway, make_attachment, operator):
    att = make_attachment()

    with pytest.raises(CommandError):
        run(att.public_id, operator="nobody")

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.PENDING
    assert not AttachmentPurgeLog.objects.exists()


def test_purge_command_inactive_operator_fails(command_gateway, make_attachment, operator):
    operator.is_active = False
    operator.save(update_fields=["is_active"])
    att = make_attachment()

    with pytest.raises(CommandError):
        run(att.public_id)

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.PENDING


def test_purge_command_storage_failure_exits_nonzero_and_keeps_deleting(
    command_gateway, make_attachment, operator
):
    att = make_attachment()
    command_gateway.fail_delete_for.add(att.s3_key)

    with pytest.raises(CommandError):
        run(att.public_id)

    assert Attachment.objects.get(pk=att.pk).status == Attachment.Status.DELETING


def test_purge_command_skipped_locked_fails_with_retry_message(
    command_gateway, make_attachment, operator, monkeypatch
):
    att = make_attachment()
    monkeypatch.setattr(
        "attachments.services.purge.purge",
        lambda *a, **k: PurgeOutcome.SKIPPED_LOCKED,
    )

    with pytest.raises(CommandError, match="처리 중, 다시 시도"):
        run(att.public_id)


def test_purge_command_already_gone_exits_zero(
    command_gateway, make_attachment, operator, monkeypatch
):
    att = make_attachment()
    monkeypatch.setattr(
        "attachments.services.purge.purge",
        lambda *a, **k: PurgeOutcome.ALREADY_GONE,
    )

    out = run(att.public_id)

    assert "이미 삭제됨" in out
    assert "삭제함" not in out


def test_purge_command_invalid_public_id_is_usage_error(command_gateway, operator):
    with pytest.raises(CommandError, match="argument --public-id"):
        run("not-a-uuid")
