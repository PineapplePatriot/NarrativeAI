"""Records page views and actions of signed-in people (users.models.Activity), for the usage report."""
import logging

from django.core.cache import cache

log = logging.getLogger(__name__)
SKIP = ("/static/", "/media/", "/admin/", "/favicon")
ACTION_EVERY = 60  # seconds: a chat sends many requests; one action a minute is enough to see a session


class ActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            record(request, response)
        except Exception:  # counting must never break a page
            log.exception("Couldn't record activity")
        return response


def record(request, response):
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated) or response.status_code >= 400 or request.path.startswith(SKIP):
        return
    from users.models import Activity
    page = request.method == "GET" and response.get("Content-Type", "").startswith("text/html")
    if request.method == "GET" and not page:
        return  # data the pages fetch while open (polls, lists): not something the person did
    if not page:
        if not cache.add(f"activity:{user.pk}", 1, ACTION_EVERY):
            return
    Activity.objects.create(user=user, kind=Activity.KIND_PAGE if page else Activity.KIND_ACTION,
                            path=request.path[:200])
