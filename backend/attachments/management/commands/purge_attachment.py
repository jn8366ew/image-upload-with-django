import uuid

from django.core.management.base import BaseCommand, CommandError

from attachments.exceptions import AttachmentNotFound, OperatorNotAllowed, StorageError
from attachments.services.purge import PurgeOutcome, purge_by_operator
from attachments.storage.s3 import build_s3_gateway


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--public-id", type=uuid.UUID, required=True)
        parser.add_argument("--operator", required=True)

    def handle(self, *args, **options):
        public_id = options["public_id"]
        try:
            outcome = purge_by_operator(
                public_id, operator_username=options["operator"], gateway=build_s3_gateway()
            )
        except OperatorNotAllowed as e:
            raise CommandError(f"operator not found or inactive: {e}") from e
        except AttachmentNotFound as e:
            raise CommandError(f"attachment not found: {e}") from e
        except StorageError as e:
            raise CommandError(f"storage error, left DELETING for retry: {e}") from e
        if outcome is PurgeOutcome.SKIPPED_LOCKED:
            raise CommandError(f"{public_id} 처리 중, 다시 시도")
        if outcome is PurgeOutcome.ALREADY_GONE:
            self.stdout.write(f"{public_id} 이미 삭제됨")
            return
        self.stdout.write(f"{public_id} 삭제함")
