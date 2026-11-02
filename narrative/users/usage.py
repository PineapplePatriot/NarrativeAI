"""Usage numbers for the project: unique users, visits, sessions and their length, who came back, what they used
and what it cost. Read by the stats page (/users/stats/) and `python manage.py usage_report`.

A session is a run of activity with no gap longer than SESSION_GAP; its length is first to last activity (a
session with a single page counts as one minute). Activity is recorded by users/activity.py."""
from collections import defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Sum
from django.utils import timezone

SESSION_GAP = timedelta(minutes=30)
ONE_PAGE = timedelta(minutes=1)


def sessions_of(times):
    """[(start, end)] from sorted activity times."""
    out = []
    for t in times:
        if out and t - out[-1][1] <= SESSION_GAP:
            out[-1][1] = t
        else:
            out.append([t, t])
    return [(a, b) for a, b in out]


def length(session):
    start, end = session
    return max(end - start, ONE_PAGE)


def _messages_sent(user):
    """(story messages, director's notes, chats with any) they wrote, read from the chat files. A note is a message
    of its own now; before, it rode on the reply it steered ("directed"), so those count as notes too."""
    from mainapp import chats
    from mainapp.models import Chat
    sent = notes = with_messages = 0
    for chat in Chat.objects.filter(character__author=user):
        try:
            messages = [m for m in chats.read(chat).get("messages") or [] if isinstance(m, (list, tuple)) and m]
        except Exception:
            continue
        mine = their_notes = 0
        for i, m in enumerate(messages):
            if m[0] == "user":
                if chats.is_note(m):
                    their_notes += 1
                else:
                    mine += 1
            elif m[0] == "assistant" and chats.directed_of(m) and not (i and chats.is_note(messages[i - 1])):
                their_notes += 1
        sent += mine
        notes += their_notes
        with_messages += (mine + their_notes) > 0
    return sent, notes, with_messages


def report(days=None, exclude=("demo",), include_staff=False):
    """Everything the stats page shows. `days`: only the last N days of activity; `exclude`: usernames left out
    (the demo account, which graders share); staff accounts are left out unless include_staff."""
    from mainapp.models import BulbaSession, Character
    from users.models import Activity, UsageRecord
    User = get_user_model()
    now = timezone.now()
    since = now - timedelta(days=days) if days else None
    users = User.objects.exclude(username__in=exclude)
    if not include_staff:
        users = users.filter(is_staff=False, is_superuser=False)
    users = list(users.order_by("date_joined"))
    ids = [u.id for u in users]

    activity = Activity.objects.filter(user_id__in=ids)
    if since:
        activity = activity.filter(at__gte=since)
    times, pages, actions = defaultdict(list), defaultdict(int), defaultdict(int)
    for user_id, at, kind in activity.order_by("at").values_list("user_id", "at", "kind"):
        times[user_id].append(at)
        if kind == Activity.KIND_PAGE:
            pages[user_id] += 1
        else:
            actions[user_id] += 1
    spend = dict(UsageRecord.objects.filter(user_id__in=ids, **({"time_create__gte": since} if since else {}))
                 .values_list("user_id").annotate(total=Sum("cost")).values_list("user_id", "total"))
    bulba = defaultdict(lambda: {"setup": 0, "finished": 0, "chat": 0})
    for user_id, mode, stage, events in BulbaSession.objects.filter(user_id__in=ids).values_list(
            "user_id", "mode", "stage", "events"):
        if len(events or []) > 1:  # opened and actually used
            bulba[user_id]["chat" if mode == "chat" else "setup"] += 1
            bulba[user_id]["finished"] += mode == "setup" and stage == "done"
    characters = dict(Character.objects.filter(author_id__in=ids).values_list("author_id")
                      .annotate(n=Count("id")).values_list("author_id", "n"))

    rows, all_sessions = [], []
    for u in users:
        sess = sessions_of(times[u.id])
        all_sessions += sess
        sent, notes, chats_used = _messages_sent(u)
        days_active = len({t.date() for t in times[u.id]})
        rows.append({
            "username": u.username, "joined": u.date_joined, "last_seen": times[u.id][-1] if times[u.id] else None,
            "active_days": days_active, "sessions": len(sess),
            "minutes": round(sum((length(s) for s in sess), timedelta()).total_seconds() / 60),
            "pages": pages[u.id], "actions": actions[u.id], "messages": sent, "notes": notes, "chats": chats_used,
            "characters": characters.get(u.id, 0), "bulba_setup": bulba[u.id]["setup"],
            "bulba_finished": bulba[u.id]["finished"], "bulba_chat": bulba[u.id]["chat"],
            "spend": round(spend.get(u.id) or 0, 4), "feedback": "yes" if u.feedback_done else "",
        })

    active = [r for r in rows if r["sessions"]]
    lengths = sorted(length(s).total_seconds() / 60 for s in all_sessions)
    week_ago, day_ago = now - timedelta(days=7), now - timedelta(days=1)
    daily = defaultdict(set)
    for user_id, ts in times.items():
        for t in ts:
            daily[t.date()].add(user_id)
    return {
        "generated": now, "days": days, "excluded": list(exclude),
        "summary": {
            "accounts": len(rows),
            "active_users": len(active),
            "active_last_7_days": sum(1 for r in active if r["last_seen"] and r["last_seen"] >= week_ago),
            "active_last_day": sum(1 for r in active if r["last_seen"] and r["last_seen"] >= day_ago),
            "returning_users": sum(1 for r in active if r["active_days"] >= 2),
            "users_who_chatted": sum(1 for r in rows if r["messages"] or r["notes"]),
            "sessions": len(all_sessions),
            "avg_session_minutes": round(sum(lengths) / len(lengths), 1) if lengths else 0,
            "median_session_minutes": round(lengths[len(lengths) // 2], 1) if lengths else 0,
            "page_views": sum(r["pages"] for r in rows),
            "messages_sent": sum(r["messages"] for r in rows),
            "notes_sent": sum(r["notes"] for r in rows),
            "finished_bulba_setup": sum(1 for r in rows if r["bulba_finished"]),
            "used_bulba_in_a_chat": sum(1 for r in rows if r["bulba_chat"]),
            "spend_usd": round(sum(r["spend"] for r in rows), 2),
            "filled_feedback_form": sum(1 for r in rows if r["feedback"]),
        },
        "signups_by_day": sorted(((d, n) for d, n in _by_day(r["joined"] for r in rows).items()), reverse=True),
        "active_by_day": sorted(((d, len(u)) for d, u in daily.items()), reverse=True),
        "users": rows,
    }


def _by_day(times):
    out = defaultdict(int)
    for t in times:
        out[timezone.localtime(t).date()] += 1
    return out


LABELS = {
    "accounts": "Accounts", "active_users": "Active users", "active_last_7_days": "Active in the last 7 days",
    "active_last_day": "Active in the last day", "returning_users": "Came back another day",
    "users_who_chatted": "Sent at least one message", "sessions": "Sessions",
    "avg_session_minutes": "Average session (minutes)", "median_session_minutes": "Median session (minutes)",
    "page_views": "Page views", "messages_sent": "Messages sent", "notes_sent": "Director's notes sent", "finished_bulba_setup": "Finished Bulba's setup",
    "used_bulba_in_a_chat": "Used Bulba in a chat", "spend_usd": "Spent on AI (USD)",
    "filled_feedback_form": "Filled in the feedback form",
}
COLUMN_LABELS = {
    "username": "User", "joined": "Joined", "last_seen": "Last seen", "active_days": "Days active",
    "sessions": "Sessions", "minutes": "Minutes", "pages": "Pages", "actions": "Actions", "messages": "Messages", "notes": "Director's notes",
    "chats": "Chats", "characters": "Characters", "bulba_setup": "Bulba setups", "bulba_finished": "Setups finished",
    "bulba_chat": "Bulba in chats", "spend": "Spend (USD)", "feedback": "Feedback form",
}

COLUMNS = ["username", "joined", "last_seen", "active_days", "sessions", "minutes", "pages", "actions", "messages",
           "notes", "chats", "characters", "bulba_setup", "bulba_finished", "bulba_chat", "spend", "feedback"]


def csv_text(data):
    import csv
    import io
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    for r in data["users"]:
        writer.writerow({k: (r[k].isoformat(timespec="minutes") if hasattr(r[k], "isoformat") else r[k]) for k in COLUMNS})
    return out.getvalue()
