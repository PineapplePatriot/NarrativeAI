"""One-off plans, invitations and free, idempotent chat reminder delivery."""
import hashlib
import json
import logging
import math
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from mainapp.models import MessengerThread, PulseReminder, ScreenEntry

STATUSES = ("planned", "invited", "tentative", "confirmed", "declined", "cancelled", "completed")


def normalize(raw):
    from mainapp.screen_apps import text
    when = parse_datetime(text(raw.get("when", ""), 50, True))
    if not when or timezone.is_naive(when):
        raise ValueError("Choose a date and time with a timezone.")
    zone = text(raw.get("timezone", "UTC"), 80, True)
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Choose a valid IANA timezone, such as Europe/Kyiv.")
    done = raw.get("done", False)
    if not isinstance(done, bool):
        raise ValueError("Done must be true or false.")
    status = "completed" if done else raw.get("status", "planned")
    clock = raw.get("clock", "real")
    if status not in STATUSES or clock not in ("real", "chat"):
        raise ValueError("Choose a valid plan status and clock.")
    minutes, duration = raw.get("reminder_minutes"), raw.get("duration_minutes", 60)
    if minutes is not None and (type(minutes) is not int or not 0 <= minutes <= 10080):
        raise ValueError("Reminder lead time must be 0–10080 minutes, or off.")
    if type(duration) is not int or not 5 <= duration <= 1440:
        raise ValueError("Duration must be 5–1440 minutes.")
    participants = raw.get("participants")
    if participants is not None and (not isinstance(participants, list) or len(participants) > 20 or
            any(not isinstance(s, str) or not s or len(s) > 255 for s in participants) or len(set(participants)) != len(participants)):
        raise ValueError("Choose up to 20 distinct characters from this chat.")
    return {"when": when.isoformat(), "timezone": zone, "clock": clock, "status": status,
            "done": status == "completed", "location": text(raw.get("location", ""), 200),
            "duration_minutes": duration, "reminder_minutes": minutes, "participants": participants}


def prepare(data, thread, previous=None, title="", body=""):
    members = set(thread.characters.values_list("slug", flat=True))
    data["participants"] = sorted(members) if data["participants"] is None else data["participants"]
    if len(data["participants"]) > 20 or not set(data["participants"]) <= members:
        raise ValueError("Every participant must belong to this chat.")
    if previous:
        old = previous.data
        keys = ("clock", "location", "duration_minutes")
        old_cast = old.get("participants") if isinstance(old.get("participants"), list) else data["participants"]
        changed = (parse_datetime(data["when"]) != parse_datetime(old["when"]) or
                   set(data["participants"]) != set(old_cast) or
                   any(data.get(k) != old.get(k, data.get(k)) for k in keys) or title != previous.title or body != previous.body)
        if changed:
            if data["status"] not in ("cancelled", "completed"):
                data["status"], data["done"] = "planned", False
        else:
            for key in ("invitation_id", "responses"):
                if key in old:
                    data[key] = old[key]
    return data


def sync_event(entry):
    data = entry.data
    when = parse_datetime(data["when"])
    minutes = data.get("reminder_minutes")
    due = when - timedelta(minutes=minutes or 0)
    signature = hashlib.sha256(json.dumps([when.timestamp(), data.get("clock", "real"), minutes], sort_keys=True).encode()).hexdigest()
    old = PulseReminder.objects.filter(event=entry).first()
    PulseReminder.objects.update_or_create(event=entry, defaults={"event_revision": entry.revision,
        "due_at": due, "clock": data.get("clock", "real"), "fingerprint": signature,
        "enabled": data.get("status") == "confirmed" and minutes is not None,
        "delivered_at": old.delivered_at if old and old.fingerprint == signature else None})


def schedule_info(entry):
    try:
        job = entry.pulse_reminder
    except PulseReminder.DoesNotExist:
        return {"enabled": False, "delivered_at": None}
    return {"enabled": job.enabled, "due_at": job.due_at.isoformat(),
            "delivered_at": job.delivered_at.isoformat() if job.delivered_at else None}


def label(data):
    zone = ZoneInfo(data.get("timezone", "UTC"))
    return parse_datetime(data["when"]).astimezone(zone).strftime("%d %b %Y, %H:%M %Z")


def _append(thread, messages, unread=False):
    from mainapp import messenger
    data = messenger.thread_data(thread)
    try:
        display_time = datetime.fromtimestamp(messenger.chat_now(data), tz=timezone.get_current_timezone()).strftime("%H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        display_time = timezone.localtime().strftime("%H:%M")
    for message in messages:
        message.update(id=uuid.uuid4().hex[:12], ts=timezone.now().timestamp(),
                       time=display_time)
        data["messages"].append(message)
    if unread:
        data["unread"] = data.get("unread", 0) + len(messages)
    messenger.save_thread_data(thread, data)


def _store(item, data, messages=()):
    from mainapp.screen_apps import packed
    with transaction.atomic():
        changed = ScreenEntry.objects.filter(pk=item.pk, owner=item.owner, revision=item.revision).update(
            data=data, revision=F("revision") + 1, updated=timezone.now())
        if not changed:
            return JsonResponse({"error": "The plan changed. Refresh it before continuing."}, status=409)
        item.refresh_from_db()
        sync_event(item)
        if messages:
            thread = MessengerThread.objects.select_for_update().get(pk=item.thread_id, user=item.owner)
            if not set(data.get("participants") or []) <= set(thread.characters.values_list("slug", flat=True)):
                raise ValueError("The chat cast changed. Update the plan and invite again.")
            _append(thread, messages)
    return JsonResponse({"entry": packed(item), "chat_changed": bool(messages)})


def scene_seed(user, item, revision):
    if item.owner_id != user.pk or item.kind != "event" or item.revision != revision:
        raise ValueError("The plan changed. Reopen it from Pulse.")
    if item.data.get("status") != "confirmed":
        raise ValueError("Confirm this plan before preparing a VN scene.")
    slugs = item.data.get("participants") or []
    if not slugs or not set(slugs) <= set(item.thread.characters.values_list("slug", flat=True)):
        raise ValueError("The plan's cast changed. Update its participants first.")
    return {"id": item.pk, "revision": item.revision, "thread_id": item.thread_id, "title": item.title,
            "when": item.data["when"], "when_label": label(item.data), "clock": item.data.get("clock", "real"),
            "location": item.data.get("location", ""), "purpose": item.body, "participants": slugs}


def action(user, thread, item, body):
    from mainapp import ai_client, messenger
    if item.kind != "event":
        raise ValueError("Choose a Pulse plan.")
    data = dict(item.data)
    if body["action"] == "pulse_scene_seed":
        return JsonResponse({"pulse_seed": scene_seed(user, item, item.revision)})
    if body["action"] == "pulse_invite":
        if data.get("status") in ("invited", "confirmed", "cancelled", "completed"):
            raise ValueError("This plan is already invited, confirmed or closed.")
        participants = data.get("participants") or []
        if not participants or not set(participants) <= set(thread.characters.values_list("slug", flat=True)):
            raise ValueError("Choose participants from this chat and save the plan first.")
        data.update(status="invited", done=False, invitation_id=uuid.uuid4().hex, responses=[])
        return _store(item, data, [{"role": "user", "text": f"Pulse invitation: {item.title}",
            "pulse_event_id": item.pk, "file": {"name": "invitation.txt", "content":
            f"When: {label(data)} ({data.get('clock', 'real')} clock)\nWhere: {data.get('location', '')}\n"
            f"Participants: {', '.join(participants)}\nPurpose: {item.body}"}}])
    if body["action"] != "pulse_respond":
        raise ValueError("Unknown Pulse action.")
    if data.get("status") != "invited" or not data.get("invitation_id") or data.get("responses"):
        raise ValueError("Send an invitation before requesting its replies.")
    participants = data.get("participants") or []
    cast = {c.slug: c for c in thread.characters.filter(slug__in=participants)}
    if set(cast) != set(participants):
        raise ValueError("The cast changed. Update the plan and invite again.")
    messages = messenger.build_messenger_prompt(user, thread)
    messages.append({"role": "system", "content":
        'PULSE INVITATION REPLIES: Answer the saved invitation as each listed participant, in their own voice. '
        'Use their known priorities and commitments; do not invent schedule conflicts, force agreement, '
        'hostility or flirting. A tentative answer is valid when information is missing. No stage directions. '
        'Return only JSON {"responses":[{"slug":"exact character slug","response":"accepted|tentative|declined",'
        '"text":"their actual reply"}]}, with exactly one response per invited participant. '
        'These replies will be delivered in their chat. Accepting a future plan does not mean it happened.'})
    messages.append({"role": "user", "content": json.dumps({"title": item.title, "plan": data,
        "purpose": item.body, "cast": [{"slug": s, "name": c.name} for s, c in cast.items()]}, ensure_ascii=False)})
    parsed = messenger._read_json(ai_client.complete(user, "chat", messages, max_tokens=3000, temperature=0.8) or "")
    replies = parsed.get("responses")
    if not isinstance(replies, list) or len(replies) != len(cast):
        raise ValueError("The model did not return a reply for every participant. The plan is unchanged.")
    seen, cleaned, bubbles = set(), [], []
    for reply in replies:
        if not isinstance(reply, dict) or reply.get("slug") not in cast or reply["slug"] in seen or reply.get("response") not in ("accepted", "tentative", "declined") or not isinstance(reply.get("text"), str) or not reply["text"].strip() or len(reply["text"]) > 2000:
            raise ValueError("The invitation replies were incomplete or invalid. Nothing was delivered.")
        slug = reply["slug"]; seen.add(slug)
        cleaned.append({"slug": slug, "name": cast[slug].name, "response": reply["response"], "text": reply["text"].strip()})
        bubbles.append({"role": "assistant", "sender_slug": slug, "sender_name": cast[slug].name,
            "text": reply["text"].strip(), "pulse_event_id": item.pk})
    outcomes = {r["response"] for r in cleaned}
    data.update(responses=cleaned, status="declined" if "declined" in outcomes else "confirmed" if outcomes == {"accepted"} else "tentative")
    return _store(item, data, bubbles)


def deliver_due(user=None, limit=200, now=None):
    """No models. Claim and append atomically; missed, finished events do not flood chats."""
    now = now or timezone.now()
    jobs = PulseReminder.objects.filter(enabled=True, delivered_at__isnull=True).filter(
        Q(clock="chat") | Q(due_at__lte=now)).order_by(F("checked_at").asc(nulls_first=True), "due_at")
    if user is not None:
        jobs = jobs.filter(event__owner=user)
    delivered, expired, threads, reminders = 0, 0, set(), []
    for job_id in list(jobs.values_list("pk", flat=True)[:limit]):
        with transaction.atomic():
            job = PulseReminder.objects.select_related("event", "event__thread").filter(pk=job_id).first()
            if not job:
                continue
            item = ScreenEntry.objects.select_for_update().filter(pk=job.event_id).first()
            if not item:
                continue
            if item.revision != job.event_revision or item.data.get("status") != "confirmed":
                PulseReminder.objects.filter(pk=job.pk, event_revision=job.event_revision).update(enabled=False)
                continue
            thread = MessengerThread.objects.select_for_update().filter(pk=item.thread_id, user_id=item.owner_id).first()
            if not thread:
                continue
            PulseReminder.objects.filter(pk=job.pk).update(checked_at=now)
            try:
                offset = float((thread.data or {}).get("clock_offset") or 0) if job.clock == "chat" else 0
                if not math.isfinite(offset):
                    raise ValueError("Non-finite clock.")
                clock_now = now + timedelta(seconds=offset)
            except (ValueError, TypeError, OverflowError):
                PulseReminder.objects.filter(pk=job.pk, event_revision=item.revision).update(enabled=False)
                logging.getLogger(__name__).warning("Disabled Pulse reminder %s: invalid story clock.", job.pk)
                continue
            if clock_now < job.due_at:
                continue
            ends = parse_datetime(item.data["when"]) + timedelta(minutes=item.data.get("duration_minutes", 60))
            if clock_now >= ends:
                PulseReminder.objects.filter(pk=job.pk, delivered_at__isnull=True).update(enabled=False)
                reminders.append({"id": item.pk, "expired": True})
                expired += 1; continue
            claimed = PulseReminder.objects.filter(pk=job.pk, event_revision=item.revision,
                enabled=True, delivered_at__isnull=True).update(delivered_at=now)
            if not claimed:
                continue
            _append(thread, [{"role": "system", "pulse_event_id": item.pk,
                "text": f"Pulse reminder: {item.title} — {label(item.data)} ({job.clock} clock)"
                        + (f" · {item.data.get('location')}" if item.data.get("location") else "")
                        + ". Open the plan for details and scene setup."}], unread=True)
            delivered += 1; threads.add(thread.pk)
            reminders.append({"id": item.pk, "delivered_at": now.isoformat()})
    return {"delivered": delivered, "expired": expired, "thread_ids": sorted(threads), "reminders": reminders}
