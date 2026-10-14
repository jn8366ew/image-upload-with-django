from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from attachments.models import Attachment

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def command_gateway(gateway, monkeypatch):
    monkeypatch.setattr(
        "attachments.management.commands.attachment_maintenance.build_s3_gateway",
        lambda: gateway,
    )
    return gateway


def test_maintenance_command_prints_counts_and_exits_zero_on_transient_failure(
    command_gateway, make_attachment
):
    att = make_attachment(status=Attachment.Status.REJECTED)
    command_gateway.fail_delete_for.add(att.s3_key)
    out = StringIO()

    call_command("attachment_maintenance", stdout=out)

    assert "failed=1" in out.getvalue()
    assert "deleting_remaining=1" in out.getvalue()


def test_maintenance_command_exits_nonzero_on_auth_error(command_gateway, make_attachment):
    make_attachment(status=Attachment.Status.REJECTED)
    command_gateway.auth_broken = True

    with pytest.raises(CommandError):
        call_command("attachment_maintenance", stdout=StringIO())
