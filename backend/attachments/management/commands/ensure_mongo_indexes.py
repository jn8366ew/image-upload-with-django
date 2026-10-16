from django.core.management.base import BaseCommand

from attachments.events import mongo
from attachments.events.indexes import ensure_indexes


class Command(BaseCommand):
    help = "attachment_events 컬렉션의 인덱스를 만든다 (멱등)"

    def handle(self, *args, **options):
        names = ensure_indexes(mongo.database())
        self.stdout.write(f"indexes: {', '.join(names)}")
