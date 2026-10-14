from dataclasses import asdict

from django.core.management.base import BaseCommand, CommandError

from attachments.exceptions import StorageAuthError
from attachments.services.maintenance import run_maintenance
from attachments.storage.s3 import build_s3_gateway


class Command(BaseCommand):
    def handle(self, *args, **options):
        try:
            result = run_maintenance(gateway=build_s3_gateway())
        except StorageAuthError as e:
            raise CommandError(f"storage auth error, aborted: {e}") from e
        self.stdout.write(" ".join(f"{k}={v}" for k, v in asdict(result).items()))
