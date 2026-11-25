import logging
import time
from django.core.management.base import BaseCommand, CommandError
from mainapp import pulse


class Command(BaseCommand):
    help = "Deliver due Pulse reminders without model calls. Run every minute for offline delivery."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=200)
        parser.add_argument("--user-id", type=int)
        parser.add_argument("--watch", action="store_true")
        parser.add_argument("--interval", type=int, default=60)

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        if not 1 <= options["limit"] <= 5000 or not 10 <= options["interval"] <= 3600:
            raise CommandError("Use a limit of 1–5000 and an interval of 10–3600 seconds.")
        try:
            user = get_user_model().objects.get(pk=options["user_id"]) if options["user_id"] else None
        except get_user_model().DoesNotExist:
            raise CommandError("User not found.")
        try:
            while True:
                try:
                    result = pulse.deliver_due(user=user, limit=options["limit"])
                    if not options["watch"] or result["delivered"] or result["expired"]:
                        self.stdout.write(str(result))
                except Exception:
                    if not options["watch"]:
                        raise
                    logging.getLogger(__name__).exception("Pulse tick failed; retrying after the interval.")
                if not options["watch"]:
                    return
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            return
