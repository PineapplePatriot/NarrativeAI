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


def minutes_by_day(session):
    """{local date: minutes} of one session, split at each midnight (in the active time zone): a session from 23:00
    to 04:00 gives 60 minutes to the first day and 240 to the next. A one-page session is a minute on its day."""
    start, end = timezone.localtime(session[0]), timezone.localtime(session[1])
    if end - start < ONE_PAGE:
        return {start.date(): ONE_PAGE.total_seconds() / 60}
    out, at = defaultdict(float), start
    while at < end:
        midnight = (at + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        stop = min(end, midnight)
        out[at.date()] += (stop - at).total_seconds() / 60
        at = stop
    return dict(out)


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


def report(days=None, exclude=("demo",), include_staff=False, week_starts="sunday"):
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
    bulba = defaultdict(lambda: {"setup": 0, "finished": 0, "chat": 0, "proposed": 0, "accepted": 0, "asked": 0})
    for user_id, mode, stage, events, proposals, messages in BulbaSession.objects.filter(user_id__in=ids).values_list(
            "user_id", "mode", "stage", "events", "proposals", "messages"):
        # 🥔 what Bulba offered, what they kept (applied and not undone), and how much they talked to it
        props = [p for p in proposals or [] if isinstance(p, dict)]
        bulba[user_id]["proposed"] += len(props)
        bulba[user_id]["accepted"] += sum(1 for p in props if p.get("status") == "applied")
        bulba[user_id]["asked"] += sum(1 for e in events or [] if isinstance(e, dict) and e.get("type") == "user")
        if len(events or []) > 1:  # opened and actually used
            bulba[user_id]["chat" if mode == "chat" else "setup"] += 1
            bulba[user_id]["finished"] += mode == "setup" and stage == "done"
    characters = dict(Character.objects.filter(author_id__in=ids).values_list("author_id")
                      .annotate(n=Count("id")).values_list("author_id", "n"))

    rows, all_sessions, sessions_by_user = [], [], {}
    for u in users:
        sess = sessions_of(times[u.id])
        all_sessions += sess
        sessions_by_user[u.id] = sess
        sent, notes, chats_used = _messages_sent(u)
        days_active = len({timezone.localtime(t).date() for t in times[u.id]})
        rows.append({
            "username": u.username, "joined": u.date_joined, "last_seen": times[u.id][-1] if times[u.id] else None,
            "active_days": days_active, "sessions": len(sess),
            "minutes": round(sum((length(s) for s in sess), timedelta()).total_seconds() / 60),
            "pages": pages[u.id], "actions": actions[u.id], "messages": sent, "notes": notes, "chats": chats_used,
            "characters": characters.get(u.id, 0), "bulba_setup": bulba[u.id]["setup"],
            "bulba_finished": bulba[u.id]["finished"], "bulba_chat": bulba[u.id]["chat"],
            "bulba_proposed": bulba[u.id]["proposed"], "bulba_accepted": bulba[u.id]["accepted"],
            "bulba_asked": bulba[u.id]["asked"],
            "spend": round(spend.get(u.id) or 0, 4), "feedback": "yes" if u.feedback_done else "",
        })

    active = [r for r in rows if r["sessions"]]
    lengths = sorted(length(s).total_seconds() / 60 for s in all_sessions)
    week_ago, day_ago = now - timedelta(days=7), now - timedelta(days=1)
    daily, daily_minutes = defaultdict(set), defaultdict(float)
    for user_id, ts in times.items():
        for t in ts:
            daily[timezone.localtime(t).date()].add(user_id)
    for s in all_sessions:
        for d, mins in minutes_by_day(s).items():
            daily_minutes[d] += mins
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
            "bulba_changes_accepted": sum(r["bulba_accepted"] for r in rows),
            "bulba_changes_proposed": sum(r["bulba_proposed"] for r in rows),
            "messages_to_bulba": sum(r["bulba_asked"] for r in rows),
            "spend_usd": round(sum(r["spend"] for r in rows), 2),
            "filled_feedback_form": sum(1 for r in rows if r["feedback"]),
        },
        "weekly": weekly(sessions_by_user, now, starts=week_starts),
        "retention": retention(users, times, now, starts=week_starts),
        "week_starts": week_starts,
        "signups_by_day": sorted(((d, n) for d, n in _by_day(r["joined"] for r in rows).items()), reverse=True),
        "active_by_day": sorted(((d, len(u), round(daily_minutes.get(d, 0))) for d, u in daily.items()), reverse=True),
        "time_zone": timezone.get_current_timezone_name(),
        "users": rows,
    }


def _week_start(t, starts="sunday"):
    """The first day of t's week: the Sunday (Sunday to Saturday) or, with starts="monday", the Monday."""
    return _week_start_of_date(timezone.localtime(t).date(), starts)


def _week_start_of_date(d, starts="sunday"):
    return d - timedelta(days=d.weekday() if starts == "monday" else (d.weekday() + 1) % 7)


def weekly(sessions_by_user, now, weeks=12, starts="sunday"):
    """Week by week (Sunday to Saturday, or Monday to Sunday; the last `weeks`, newest first), everyone added up:
    minutes on the site, sessions, and people active. A session counts once, in the week it started; its minutes
    are split at midnight, so each week gets the time actually spent in it."""
    out = defaultdict(lambda: {"minutes": 0.0, "sessions": 0, "people": set()})
    for user_id, sess in sessions_by_user.items():
        for s in sess:
            w = out[_week_start(s[0], starts)]
            w["sessions"] += 1
            w["people"].add(user_id)
            for day, mins in minutes_by_day(s).items():
                wk = out[_week_start_of_date(day, starts)]
                wk["minutes"] += mins
                wk["people"].add(user_id)
    this = _week_start(now, starts)
    rows = []
    for k in range(weeks):
        start = this - timedelta(weeks=k)
        w = out.get(start, {"minutes": 0, "sessions": 0, "people": set()})
        rows.append({"week": start, "hours": round(w["minutes"] / 60, 1), "minutes": round(w["minutes"]),
                     "sessions": w["sessions"], "people": len(w["people"]),
                     "per_person": round(w["minutes"] / len(w["people"])) if w["people"] else 0})
    return rows


def retention(users, times, now, starts="sunday"):
    """Who came back. Day N: of the people signed up at least N days ago, the share active again N or more days
    after signing up. Cohorts: people by the week they signed up, and the share active in each of the 4 weeks
    after (a week only counts once it's over)."""
    days = {}
    for n in (1, 7, 30):
        eligible = [u for u in users if now - u.date_joined >= timedelta(days=n)]
        back = [u for u in eligible if any(t - u.date_joined >= timedelta(days=n) for t in times[u.id])]
        days[n] = {"eligible": len(eligible), "back": len(back),
                   "share": round(100 * len(back) / len(eligible)) if eligible else None}
    cohorts = defaultdict(list)
    for u in users:
        cohorts[_week_start(u.date_joined, starts)].append(u)
    rows = []
    for start in sorted(cohorts, reverse=True)[:12]:
        people = cohorts[start]
        cells = []
        for k in range(1, 5):
            a, b = start + timedelta(weeks=k), start + timedelta(weeks=k + 1)
            if timezone.localtime(now).date() < b:
                cells.append(None)  # that week isn't over yet
                continue
            active = sum(1 for u in people if any(a <= timezone.localtime(t).date() < b for t in times[u.id]))
            cells.append(round(100 * active / len(people)))
        rows.append({"week": start, "people": len(people), "weeks": cells})
    return {"days": days, "cohorts": rows}


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
    "bulba_changes_accepted": "Bulba's changes accepted", "bulba_changes_proposed": "Bulba's changes proposed",
    "messages_to_bulba": "Messages to Bulba",
    "filled_feedback_form": "Filled in the feedback form",
}
COLUMN_LABELS = {
    "username": "User", "joined": "Joined", "last_seen": "Last seen", "active_days": "Days active",
    "sessions": "Sessions", "minutes": "Minutes", "pages": "Pages", "actions": "Actions", "messages": "Messages", "notes": "Director's notes",
    "chats": "Chats", "characters": "Characters", "bulba_setup": "Bulba setups", "bulba_finished": "Setups finished",
    "bulba_chat": "Bulba in chats", "bulba_proposed": "Bulba proposed", "bulba_accepted": "Bulba accepted",
    "bulba_asked": "Messages to Bulba", "spend": "Spend (USD)", "feedback": "Feedback form",
}

COLUMNS = ["username", "joined", "last_seen", "active_days", "sessions", "minutes", "pages", "actions", "messages",
           "notes", "chats", "characters", "bulba_setup", "bulba_finished", "bulba_chat", "bulba_proposed",
           "bulba_accepted", "bulba_asked", "spend", "feedback"]


def csv_text(data):
    import csv
    import io
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    for r in data["users"]:
        writer.writerow({k: (r[k].isoformat(timespec="minutes") if hasattr(r[k], "isoformat") else r[k]) for k in COLUMNS})
    return out.getvalue()
