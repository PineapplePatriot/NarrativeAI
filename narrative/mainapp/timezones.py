"""🌍 Each request starts and ends on the server's own time zone (UTC). Pages that show times in the browser's zone
switch to it themselves (messenger.use_browser_time_zone); this makes sure that never sticks to the worker thread
and leaks into the next request, someone else's."""
from django.utils import timezone


class ResetTimeZoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        timezone.deactivate()
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
