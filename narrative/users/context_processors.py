import os


def feedback(request):
    """The tester feedback form (FEEDBACK_FORM_URL on the server), until they say they've filled it in."""
    url = os.environ.get("FEEDBACK_FORM_URL", "").strip()
    user = getattr(request, "user", None)
    show = bool(url and user and user.is_authenticated and not getattr(user, "feedback_done", False))
    signed_in = bool(user and user.is_authenticated)
    return {"feedback_url": url if show else "",
            "bug_form_url": os.environ.get("BUG_FORM_URL", "").strip() if signed_in else ""}


def tomato_pit(request):
    """🍅 The Tomato Pit's link in the top bar, once this account has found it (static/js/tomato.js)."""
    user = getattr(request, "user", None)
    if not (user and user.is_authenticated):
        return {}
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).only("appearance").first()
    return {"tomato_pit_found": bool(obj and ((obj.appearance or {}).get("tomatoes") or {}).get("found"))}
