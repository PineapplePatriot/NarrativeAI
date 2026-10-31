import os


def feedback(request):
    """The tester feedback form (FEEDBACK_FORM_URL on the server), until they say they've filled it in."""
    url = os.environ.get("FEEDBACK_FORM_URL", "").strip()
    user = getattr(request, "user", None)
    show = bool(url and user and user.is_authenticated and not getattr(user, "feedback_done", False))
    return {"feedback_url": url if show else ""}
