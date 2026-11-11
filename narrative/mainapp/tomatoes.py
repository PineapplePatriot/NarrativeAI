"""
🍅 Tomatoes thrown "in the wild": at a chat or at Bulba while waiting for a reply (static/js/tomato.js). They're
what the leaderboard ranks and, later, what pays for spins. Throws in the Tomato Pit's own field and on the splat
wall count only towards the personal total (views.tomato_state), so an auto-clicker on the Pit wins nothing.

The browser says how many it threw, so the server only believes what a person could do:
- RATE throws a second since the last sync, plus a small BURST (several tabs, a sync that failed and came later);
- at most DAY_MAX a day (UTC). An honest heavy day of chatting stays well under it.
What goes over is dropped, and the browser takes the server's number back on its next sync.
"""
from django.db import transaction
from django.utils import timezone

RATE = 12       # throws a second: faster than anyone's clicking, slower than a script's
BURST = 60      # allowed on top, whatever the time since the last sync
DAY_MAX = 5000  # chat + Bulba throws counted per day
BOARD_SIZE = 20


def score_of(user):
    from mainapp.models import TomatoScore
    obj, _ = TomatoScore.objects.get_or_create(user=user)
    return obj


def allowed(score, now):
    """How many chat + Bulba throws one sync may add right now."""
    if score.synced_at is None:
        by_time = BURST * 5  # the first sync ever: a few minutes' worth thrown before syncs began
    else:
        by_time = BURST + int(max(0.0, (now - score.synced_at).total_seconds()) * RATE)
    today = now.date()
    used = score.day_wild if score.day == today else 0
    return max(0, min(by_time, DAY_MAX - used))


def add_wild(user, sent):
    """Count `sent` chat + Bulba throws (bounded as above); returns the saved score."""
    from mainapp.models import TomatoScore
    now = timezone.now()
    with transaction.atomic():
        score_of(user)  # make sure the row exists before locking it
        score = TomatoScore.objects.select_for_update().get(user=user)
        add = min(max(0, sent), allowed(score, now))
        today = now.date()
        if score.day != today:
            score.day, score.day_wild = today, 0
        score.wild += add
        score.day_wild += add
        score.synced_at = now
        score.save()
    return score


def board(user):
    """The leaderboard: the top BOARD_SIZE who joined, and where this user stands (or would stand if they joined)."""
    from mainapp.models import TomatoScore
    me = score_of(user)
    joined = TomatoScore.objects.filter(on_board=True, wild__gt=0).select_related("user")
    top = [{"name": s.user.username, "wild": s.wild, "me": s.user_id == user.id}
           for s in joined.order_by("-wild", "synced_at", "id")[:BOARD_SIZE]]
    ahead = joined.filter(wild__gt=me.wild).exclude(user=user).count()
    return {"top": top, "me": {"wild": me.wild, "on_board": me.on_board, "rank": ahead + 1 if me.wild else None,
                               "today": me.day_wild if me.day == timezone.now().date() else 0},
            "players": joined.count(), "day_max": DAY_MAX}


def join(user, on):
    score = score_of(user)
    score.on_board = bool(on)
    score.save(update_fields=["on_board"])
    return score
