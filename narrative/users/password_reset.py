"""
"Forgot password?": they give their email, get a link (through Brevo, like the verification email) and set a new
password themselves. The link works for LINK_HOURS hours and only once (Django's token changes with the password).
The page answers the same whether or not the email has an account, so it can't be used to find out who's signed up.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from users import verification

LINK_HOURS = 2
EVERY = 120          # seconds between two reset emails to one account
PER_ADDRESS = 10     # requests from one network address per hour


def link_for(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return request.build_absolute_uri(reverse("users:reset", args=[uid, default_token_generator.make_token(user)]))


def user_for(uidb64, token):
    try:
        user = get_user_model().objects.filter(pk=force_str(urlsafe_base64_decode(uidb64))).first()
    except (ValueError, TypeError, OverflowError):
        return None
    return user if user and default_token_generator.check_token(user, token) else None


def request_reset(request, email):
    """Sends the link if the email has an account. Returns an error only for things they can act on (too many
    requests from here); an unknown email looks exactly like a sent one."""
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    address = forwarded or request.META.get("REMOTE_ADDR", "")
    key = f"reset-ip:{address}"
    cache.add(key, 0, 3600)
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 3600)
        count = 1
    if count > PER_ADDRESS:
        return "Too many requests from here. Try again in an hour."
    user = get_user_model().objects.filter(email__iexact=email.strip(), is_active=True).first() if email.strip() else None
    if user is None or not cache.add(f"reset-sent:{user.pk}", 1, EVERY):
        return None
    link = link_for(request, user)
    text = (f"Hi {user.username},\n\nSomeone (hopefully you) asked to reset your Narrative AI password. Set a new one "
            f"here:\n{link}\n\nThe link works for {LINK_HOURS} hours and only once. If it wasn't you, ignore this "
            f"email: your password stays as it is.\n\nВітаємо! Щоб задати новий пароль для Narrative AI, перейдіть за "
            f"посиланням вище. Воно діє {LINK_HOURS} години й лише один раз. Якщо це були не ви, просто проігноруйте лист.")
    html = (f"<p>Hi {user.username},</p><p>Someone (hopefully you) asked to reset your Narrative AI password.</p>"
            f'<p><a href="{link}" style="display:inline-block;padding:10px 18px;background:#7e3af2;color:#fff;'
            f'border-radius:8px;text-decoration:none;font-weight:600">Set a new password</a></p>'
            f"<p>The link works for {LINK_HOURS} hours and only once. If it wasn't you, ignore this email: your "
            f"password stays as it is.</p><hr><p>Вітаємо! Щоб задати новий пароль, натисніть кнопку вище. Посилання "
            f"діє {LINK_HOURS} години й лише один раз. Якщо це були не ви, просто проігноруйте лист.</p>")
    error = verification.brevo_send(user, "Reset your password · Новий пароль (Narrative AI)", html, text)
    if error:
        cache.delete(f"reset-sent:{user.pk}")
        return error
    return None


def unlock(user):
    """A new password lifts the wrong-password lock on their username."""
    cache.delete(f"login-fail:user:{(user.username or '').strip().lower()}")
