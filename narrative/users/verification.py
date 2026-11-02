"""Email verification at sign-up, through Brevo's email API. It switches on by itself when the server has
BREVO_API_KEY and BREVO_SENDER_EMAIL (BREVO_SENDER_NAME optional); without them sign-up works as before.

New accounts get a link (valid LINK_DAYS days) and can't use the app until they click it; the "Check your email"
page can send it again. Accounts made before this, and the demo, count as verified."""
import logging
import os

import requests
from django.core import signing
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse

log = logging.getLogger(__name__)
BREVO_URL = "https://api.brevo.com/v3/smtp/email"
LINK_DAYS = 3
SALT = "narrativeai-email-verification"
RESEND_EVERY = 60  # seconds between two emails to one account
# Pages an unverified account may still open: the waiting page, the link itself, logging out
OPEN_PATHS = ("/users/verify", "/users/logout", "/users/delete", "/users/login", "/static/", "/media/", "/favicon")


def enabled():
    return bool(os.environ.get("BREVO_API_KEY") and os.environ.get("BREVO_SENDER_EMAIL"))


def token_for(user):
    return signing.TimestampSigner(salt=SALT).sign(f"{user.pk}:{user.email}")


def check(token):
    """The user a link is for, or None (unknown, expired, or the email changed since)."""
    from django.contrib.auth import get_user_model
    try:
        value = signing.TimestampSigner(salt=SALT).unsign(token, max_age=LINK_DAYS * 24 * 3600)
    except signing.BadSignature:  # also SignatureExpired
        return None
    pk, _, email = value.partition(":")
    user = get_user_model().objects.filter(pk=pk).first()
    return user if user and user.email == email else None


def send(request, user):
    """Emails the link. Returns an error message for the page, or None when it went out."""
    if not cache.add(f"verify-sent:{user.pk}", 1, RESEND_EVERY):
        return "An email was just sent. Give it a minute (and check spam) before asking again."
    link = request.build_absolute_uri(reverse("users:verify_link", args=[token_for(user)]))
    text = (f"Hi {user.username},\n\nConfirm your email to start using Narrative AI:\n{link}\n\n"
            f"The link works for {LINK_DAYS} days. If you didn't sign up, ignore this email.\n\n"
            f"Вітаємо! Підтвердіть пошту, щоб почати користуватися Narrative AI, за посиланням вище. "
            f"Воно діє {LINK_DAYS} дні. Якщо ви не реєструвалися, просто проігноруйте цей лист.")
    html = (f"<p>Hi {user.username},</p><p>Confirm your email to start using Narrative AI:</p>"
            f'<p><a href="{link}" style="display:inline-block;padding:10px 18px;background:#7e3af2;color:#fff;'
            f'border-radius:8px;text-decoration:none;font-weight:600">Confirm my email</a></p>'
            f"<p>The link works for {LINK_DAYS} days. If you didn't sign up, ignore this email.</p><hr>"
            f"<p>Вітаємо! Підтвердіть пошту, щоб почати користуватися Narrative AI: натисніть кнопку вище. "
            f"Посилання діє {LINK_DAYS} дні. Якщо ви не реєструвалися, просто проігноруйте цей лист.</p>")
    body = {"sender": {"email": os.environ["BREVO_SENDER_EMAIL"],
                       "name": os.environ.get("BREVO_SENDER_NAME") or "Narrative AI"},
            "to": [{"email": user.email, "name": user.username}],
            "subject": "Confirm your email · Підтвердіть пошту (Narrative AI)",
            "htmlContent": html, "textContent": text}
    try:
        resp = requests.post(BREVO_URL, json=body, timeout=15,
                             headers={"api-key": os.environ["BREVO_API_KEY"], "accept": "application/json"})
    except requests.RequestException as e:
        log.warning("Brevo couldn't be reached: %s", e)
        cache.delete(f"verify-sent:{user.pk}")
        return "The email couldn't be sent just now. Try again in a minute."
    if resp.status_code >= 400:
        log.warning("Brevo refused the email (%s): %s", resp.status_code, resp.text[:300])
        cache.delete(f"verify-sent:{user.pk}")
        return "The email couldn't be sent. If it keeps happening, tell the people running this test."
    return None


class VerificationMiddleware:
    """An account that hasn't confirmed its email sees only the "Check your email" page (and can log out)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (user and user.is_authenticated and not getattr(user, "email_verified", True) and not user.is_staff
                and enabled() and not request.path.startswith(OPEN_PATHS)):
            if request.method != "GET" or "application/json" in request.headers.get("Accept", ""):
                from django.http import JsonResponse
                return JsonResponse({"error": "Confirm your email first (check your inbox)."}, status=403)
            return redirect("users:verify")
        return self.get_response(request)
