from django.core.management.base import BaseCommand, CommandError

from attachments.events import mongo, relay


class Command(BaseCommand):
    help = "event_outbox의 미발행 이벤트를 MongoDB로 옮긴다"

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true")

    def handle(self, *args, **options):
        if options["loop"]:
            relay.run_loop(mongo.database())
            return
        try:
            published = relay.relay_once(mongo.database())
        except mongo.MongoError as e:
            raise CommandError(f"mongo unavailable, events kept unpublished: {e}") from e
        self.stdout.write(f"published={published}")
