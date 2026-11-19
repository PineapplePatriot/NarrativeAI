"""Lore owned by a messenger chat, shared with its in-person episodes."""
import copy
import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse

from mainapp import ai_client, lorebook
from mainapp.models import MessengerThread, Worldbook


FIELDS = ("lorebook", "lore_mode", "lore_pending", "lore_draft")


def mark_modernized(character):
    for pk in MessengerThread.objects.filter(user=character.author, characters=character).values_list("pk", flat=True):
        with transaction.atomic():
            thread = MessengerThread.objects.select_for_update().get(pk=pk)
            thread.data = {**(thread.data or {}), "lore_pending": True, "lore_mode": "off"}
            thread.save(update_fields=["data"])


def ensure_selection(thread):
    """Offer setup to modernized chats created before chat-specific lore was introduced."""
    from mainapp import messenger
    if "lore_mode" in (thread.data or {}):
        return
    if not any(messenger.is_set_up(c) and messenger.char_profile(c)["mode"] == "modern_au" for c in thread.characters.all()):
        return
    with transaction.atomic():
        locked = MessengerThread.objects.select_for_update().get(pk=thread.pk)
        if "lore_mode" not in (locked.data or {}):
            locked.data = {**(locked.data or {}), "lore_pending": True, "lore_mode": "off"}
            locked.save(update_fields=["data"])
        thread.data = locked.data


def books_for(thread):
    ensure_selection(thread)
    raw = thread.data or {}
    mode = raw.get("lore_mode", "inherit")
    if mode == "local":
        return [lorebook.normalize_book(raw.get("lorebook") or {})]
    if mode == "off":
        return []
    seen, books = set(), []
    for character in thread.characters.all():
        if character.worldbook_id and character.worldbook_id not in seen:
            books.append(lorebook.load_worldbook(character.worldbook))
            seen.add(character.worldbook_id)
    return books


def activate_for(thread, messages=None, notes=""):
    messages = messages if messages is not None else (thread.data or {}).get("messages", [])
    entries, reports, notices = [], [], []
    for book in books_for(thread):
        result = lorebook.activate(book, messages, notes_text=notes)
        entries.extend(result["entries"])
        reports.extend({**r, "book": book["title"]} for r in result["report"])
        notices.extend(result["notes"])
    return {"text": lorebook.format_for_prompt(entries), "report": reports, "notes": notices}


def describe(thread):
    ensure_selection(thread)
    raw = thread.data or {}
    book = raw.get("lorebook") or {}
    return {"mode": raw.get("lore_mode", "inherit"), "pending": bool(raw.get("lore_pending")),
            "title": book.get("title", ""), "entries": len(book.get("entries") or [])}


def payload(thread):
    return {"summary": describe(thread), "book": copy.deepcopy((thread.data or {}).get("lorebook")),
            "draft": copy.deepcopy((thread.data or {}).get("lore_draft")),
            "activation": activate_for(thread),
            "sources": list(Worldbook.objects.filter(author=thread.user).values("id", "title"))}


@login_required
def api(request):
    from mainapp import messenger
    if request.method not in ("GET", "POST"):
        return JsonResponse({"error": "GET or POST required."}, status=405)
    try:
        body = json.loads(request.body or b"{}") if request.method == "POST" else request.GET
        if not isinstance(body, dict) and request.method == "POST":
            raise ValueError("Expected an object.")
        tid = body.get("thread_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
        if thread is None:
            return JsonResponse({"error": "Chat not found."}, status=404)
        if request.method == "GET":
            return JsonResponse(payload(thread))
        if request.method != "POST":
            return JsonResponse({"error": "POST required."}, status=405)
        action = body.get("action")
        raw = copy.deepcopy(thread.data or {})
        updates = {}
        if action == "save":
            if not isinstance(body.get("book"), dict):
                raise ValueError("Supply a lorebook.")
            updates.update(lorebook=lorebook.normalize_book(body["book"]), lore_mode="local", lore_pending=False)
        elif action == "copy":
            source = Worldbook.objects.filter(author=request.user, id=body.get("source_id")).first()
            if source is None:
                raise ValueError("Choose one of your lorebooks.")
            updates.update(lorebook=copy.deepcopy(lorebook.load_worldbook(source)), lore_mode="local", lore_pending=False)
        elif action == "mode":
            mode = body.get("mode")
            if mode not in ("off", "inherit", "local"):
                raise ValueError("Unknown lore mode.")
            updates.update(lore_mode=mode, lore_pending=False)
        elif action == "draft":
            profiles = [{"name": c.name, **messenger.char_profile(c)} for c in thread.characters.all()]
            prompt = (
                "Draft a lorebook specifically for this chat's current setting. Return JSON {title, entries: "
                "[{comment, keys: [keywords], content, constant: false}]}. Keep established facts and the user's "
                "directions. Separate suggested additions from facts by asking rather than asserting unsupported "
                "major events or relationships. Do not import fantasy institutions into a modern AU unless retained "
                "in the setup. Use concrete searchable keywords; constant entries only for essential setting facts.\n"
                + json.dumps({"characters": profiles, "scenario": raw.get("scenario_override"),
                              "persona": raw.get("persona"), "directions": str(body.get("directions") or "")[:4000],
                              "existing_lore": raw.get("lorebook")}, ensure_ascii=False))
            draft = messenger.ask_json(request.user, prompt, need=("entries",), max_tokens=3500)
            updates["lore_draft"] = lorebook.normalize_book(draft)
        else:
            raise ValueError("Unknown lore action.")
        # Generation happens before locking; only lore fields are changed, preserving concurrent texts.
        with transaction.atomic():
            locked = MessengerThread.objects.select_for_update().get(pk=thread.pk, user=request.user)
            locked.data = {**(locked.data or {}), **updates}
            locked.save(update_fields=["data"])
        thread.refresh_from_db()
        return JsonResponse({**payload(thread), "thread": messenger.serialize_thread_full(thread, request.user)})
    except (ValueError, TypeError, ai_client.AIError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
