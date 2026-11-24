# --- Standard library ---
import io
import json
import logging
import os
import traceback
import uuid
from datetime import datetime

# --- Django core ---
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import Http404, HttpResponse, JsonResponse, HttpResponseNotFound, StreamingHttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.generic import (
    TemplateView, ListView, DetailView,
    FormView, CreateView, UpdateView
)
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin

# --- Local imports ---
from mainapp.models import Character, Worldbook, ChatSettings
from .forms import AddCharacterForm, UploadFileForm
from .models import Character, Worldbook, ChatSettings, MessengerThread
from . import basics as basics_mod
from . import writing_quality
from . import sprites as sprite_mod
from . import chat_looks
from . import story_memory
from .bulba import vision as bulba_vision
from . import echo, favourites, fresh_details, speaker_colors, texture
from . import live as live_jobs  # work that outlives the page (not the local "live" lists below)
from . import extras, game, html_objects, media_library, recall, story, thinking, ai_client, cards, chats, regex_rules, experiences, model_profiles, presets, samplers, starters, tomato_garden, tomato_machine, tomatoes, trackers, translation, voice
from .bulba import control, polish, watch
from mainapp import mature, refusals

from .utils import build_ai_request, get_elevenlabs_key
from .lorebook import (
    normalize_book, load_worldbook, save_worldbook, activate, format_for_prompt, to_sillytavern,
    DEFAULT_SETTINGS as LORE_DEFAULT_SETTINGS, DEFAULT_ENTRY as LORE_DEFAULT_ENTRY,
)


@login_required
def index_page(request):
    # First run: the welcome page asks for a key and a model before anything else
    if not ai_client.has_connection(request.user):
        return redirect("users:welcome")
    # Your characters, the ones you played most recently first
    from django.db.models import F, Max
    characters = (Character.objects.filter(author=request.user)
                  .annotate(last_played=Max("chats__time_update"))
                  .order_by(F("last_played").desc(nulls_last=True), "-id"))
    context = {
        "characters": characters[:8],
        "character_count": characters.count(),
        "has_connection": ai_client.has_connection(request.user),
    }
    return render(request, 'main.html', context)


def guide_page(request):
    """How to try the app: open to everyone, linked from the top bar and the home page."""
    return render(request, "guide.html")


@login_required
def tomato_pit(request):
    """🍅 The secret Tomato Pit: throw as many as you like (static/js/tomato.js; progress kept on the account)."""
    return render(request, "mainapp/tomato_pit.html", {"scenes": tomatoes.scene_choices(),
                                                       "radio": media_library.radio()})


TOMATO_MAX_ADD = 3000  # throws one sync may add (it syncs every few seconds: well above any human rate)


def _tomato_state(raw):
    raw = raw if isinstance(raw, dict) else {}
    num = lambda v: max(0, int(v)) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0
    return {"count": num(raw.get("count")), "waits": num(raw.get("waits")), "best10": num(raw.get("best10")),
            "skin": str(raw.get("skin") or "tomato")[:20], "found": bool(raw.get("found")),
            "ach": {str(k)[:20]: num(v) for k, v in list((raw.get("ach") or {}).items())[:50]}
            if isinstance(raw.get("ach"), dict) else {},
            "days": [str(d)[:10] for d in (raw.get("days") or [])][-30:] if isinstance(raw.get("days"), list) else []}


@login_required
def tomato_state(request):
    """The account's tomatoes. POST adds what this browser threw since its last sync (a delta, so two devices
    add up instead of overwriting each other) and merges achievements, days and the picked skin."""
    from .models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=request.user)
    state = _tomato_state((obj.appearance or {}).get("tomatoes"))
    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        sent = _tomato_state(body)
        add = min(TOMATO_MAX_ADD, max(0, int(body.get("add") or 0))) if isinstance(body.get("add"), int) else 0
        state["count"] += add
        state["waits"] += min(100, max(0, int(body.get("add_waits") or 0))) if isinstance(body.get("add_waits"), int) else 0
        state["best10"] = min(200, max(state["best10"], sent["best10"]))  # nobody throws 20 a second for 10 seconds
        state["found"] = state["found"] or sent["found"]
        for k, v in sent["ach"].items():
            state["ach"].setdefault(k, v)
        state["days"] = sorted(set(state["days"]) | set(sent["days"]))[-30:]
        if "skin" in body:
            state["skin"] = sent["skin"]
        obj.appearance = {**(obj.appearance or {}), "tomatoes": state}
        obj.save(update_fields=["appearance"])
        wild = body.get("add_wild")
        if isinstance(wild, int) and not isinstance(wild, bool) and wild > 0:
            score = tomatoes.add_wild(request.user, min(wild, add))  # chat + Bulba throws are part of the same throws
            golden = body.get("add_golden")
            if isinstance(golden, int) and not isinstance(golden, bool) and golden > 0:
                if tomato_machine.add_golden(score, min(golden, wild)):  # 🌟 a free spin each
                    score.save(update_fields=["machine"])
    score = tomatoes.score_of(request.user)
    return JsonResponse({**state, "wild": score.wild, "on_board": score.on_board,
                         "prize_skins": tomato_machine.owned_skins(score), "worn": tomato_machine.worn(score)})


@login_required
def tomato_garden_page(request):
    """🌻 The garden: a live pixel-art plot for the machine's seeds, decorations and gardeners."""
    return render(request, "mainapp/tomato_garden.html")


@login_required
def tomato_garden_state(request):
    """GET: the garden now. POST {"action": plant|place|harvest|dig|remove, "x", "y", "id"} (mainapp/tomato_garden.py)."""
    if request.method == "POST":
        body = _json_body(request)
        if body is None:
            return JsonResponse({"error": "Invalid request."}, status=400)
        try:
            return JsonResponse(tomato_garden.act(request.user, body))
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
    return JsonResponse(tomato_garden.visit(request.user))


@login_required
def tomato_machine_view(request):
    """🎰 The Sauce-o-Matic. GET: its state. POST {"action": "spin", "n": 1|10} · {"action": "promise", "id"} ·
    {"action": "compost"} · {"action": "equip", "slot", "id"} (mainapp/tomato_machine.py)."""
    if request.method == "POST":
        body = _json_body(request)
        if body is None:
            return JsonResponse({"error": "Invalid request."}, status=400)
        act = body.get("action")
        try:
            if act == "spin":
                results, state = tomato_machine.spin(request.user, body.get("n") if body.get("n") in (1, 10) else 0,
                                                     banner=str(body.get("banner") or "standard"))
                return JsonResponse({**state, "results": results})
            if act == "promise":
                return JsonResponse(tomato_machine.promise(request.user, body.get("id") or None,
                                                           banner=str(body.get("banner") or "standard")))
            if act == "compost":
                return JsonResponse(tomato_machine.compost_spin(request.user))
            if act == "equip":
                return JsonResponse(tomato_machine.equip(request.user, body.get("slot"), body.get("id") or None))
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"error": "Unknown action."}, status=400)
    return JsonResponse(tomato_machine.public(tomatoes.score_of(request.user)))


@login_required
def tomato_board(request):
    """🏆 The leaderboard of chat + Bulba tomatoes. POST {"on_board": true/false} joins or leaves it."""
    if request.method == "POST":
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        if not isinstance(body, dict) or not isinstance(body.get("on_board"), bool):
            return JsonResponse({"error": "Say on_board: true or false."}, status=400)
        tomatoes.join(request.user, body["on_board"])
    return JsonResponse(tomatoes.board(request.user))


def _json_body(request):
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return None
    return body if isinstance(body, dict) else None


@login_required
def tomato_gallery(request):
    """🖼 The gallery: your saved splat walls, and everyone's shared ones (mainapp/tomatoes.py)."""
    return render(request, "mainapp/tomato_gallery.html", {"scenes": tomatoes.scene_choices()})


@login_required
def tomato_art(request):
    """GET: a page of pieces (?scope=mine|all, ?sort=new|liked, ?page=N). POST {title, bg, splats}: save the wall."""
    from .models import TomatoArt
    if request.method == "POST":
        body = _json_body(request)
        if body is None:
            return JsonResponse({"error": "Invalid request."}, status=400)
        splats = tomatoes.clean_art(body.get("splats"))
        if not splats:
            return JsonResponse({"error": "The wall is empty: throw something first."}, status=400)
        if TomatoArt.objects.filter(user=request.user).count() >= tomatoes.MAX_ART:
            return JsonResponse({"error": f"The gallery holds {tomatoes.MAX_ART} pieces. Delete one to make room."},
                                status=400)
        art = TomatoArt.objects.create(user=request.user, title=tomatoes.clean_title(body.get("title")),
                                       bg=tomatoes.clean_bg(body.get("bg")), splats=splats,
                                       shared=body.get("shared") is True)
        return JsonResponse(tomatoes.art_item(art, request.user))
    try:
        page = int(request.GET.get("page") or 1)
    except ValueError:
        page = 1
    scope = "all" if request.GET.get("scope") == "all" else "mine"
    return JsonResponse(tomatoes.art_list(request.user, scope, request.GET.get("sort") or "new", page))


@login_required
def tomato_art_one(request, art_id):
    """One piece with its splats (yours, or a shared one). POST {title?, shared?} edits yours; DELETE removes it."""
    from django.db.models import Q
    from .models import TomatoArt
    art = get_object_or_404(TomatoArt.objects.select_related("user"),
                            Q(user=request.user) | Q(shared=True), id=art_id)
    mine = art.user_id == request.user.id
    if request.method == "DELETE":
        if not mine:
            return JsonResponse({"error": "That isn't yours."}, status=403)
        art.delete()
        return JsonResponse({"deleted": art_id})
    if request.method == "POST":
        if not mine:
            return JsonResponse({"error": "That isn't yours."}, status=403)
        body = _json_body(request)
        if body is None:
            return JsonResponse({"error": "Invalid request."}, status=400)
        if "title" in body:
            art.title = tomatoes.clean_title(body["title"])
        if isinstance(body.get("shared"), bool):
            art.shared = body["shared"]
        art.save()
    return JsonResponse(tomatoes.art_item(art, request.user, full=True))


@login_required
def tomato_art_like(request, art_id):
    """❤ POST toggles your like on someone else's shared piece."""
    from .models import TomatoArt
    if request.method != "POST":
        return JsonResponse({"error": "POST only."}, status=405)
    art = get_object_or_404(TomatoArt, id=art_id, shared=True)
    if art.user_id == request.user.id:
        return JsonResponse({"error": "No liking your own art. Bulba checked."}, status=400)
    if art.likes.filter(id=request.user.id).exists():
        art.likes.remove(request.user)
    else:
        art.likes.add(request.user)
    return JsonResponse({"likes": art.likes.count(), "liked": art.likes.filter(id=request.user.id).exists()})


@login_required
def characters_list(request):
    return render(request, 'mainapp/characters.html')




import re
from urllib.parse import urlencode

log = logging.getLogger(__name__)

def _summary_line(message):
    return f"{message[0]}: {html_objects.shrink(chats.prompt_text(message))}"


def _summarize(user, messages, existing="", room=None):
    """One summary piece for `messages`, continuing `existing` when there is one. With `room` (tokens), a single
    message longer than that is cut to fit (its end kept)."""
    if existing:  # the instructions are the preset's utility prompts (Presets page → Utility prompts)
        sys_prompt = (f"Existing summary: {existing}\n\nTask: {presets.job_prompt(user, 'summary_continue')}\n\n"
                      "(Write only what happens in the messages below. Your text is added after the existing "
                      "summary, which stays as it is: don't repeat or rewrite it.)")
    else:
        sys_prompt = presets.job_prompt(user, "summary_new")
    lines = [_summary_line(m) for m in messages]
    if room and len(lines) == 1:
        lines = [samplers.cut_to(lines[0], room)]
    prompt_text = "\n".join(lines)
    return ai_client.complete(user, "summary", [{"role": "system", "content": sys_prompt},
                                                {"role": "user", "content": prompt_text}])


def _summarize_pieces(user, messages, start, earlier=""):
    """Summary pieces for `messages` (the first one is message number `start`): one piece when they fit the
    summary model's window, else several in a row, each continuing the ones before, so nothing is dropped."""
    window = samplers.job_window(user, "summary")
    pieces, i = [], 0
    while i < len(messages):
        existing = "\n".join(filter(None, [earlier] + [p["text"] for p in pieces]))
        room = max(1000, window - samplers.approx_tokens(existing) - 300)  # 300: the instructions
        j, used = i, 0
        while j < len(messages):
            cost = samplers.approx_tokens(_summary_line(messages[j]))
            if j > i and used + cost > room:
                break
            used, j = used + cost, j + 1
        pieces.append({"text": _summarize(user, messages[i:j], existing, room), "from": start + i, "to": start + j})
        i = j
    return pieces


def _story_text(user, chat_state, count):
    """What the model reads as the story so far: story memory or the manual summary (the chat's mode), after what
    the chats linked to this one remember (🔗, oldest first)."""
    own = story_memory.story_text(user, {"summary_mode": chat_state.get("summary_mode"), "memory": chat_state.get("memory"),
                                         "summary_parts": chat_state.get("summary_parts"), "summary": chat_state.get("summary")},
                                  chat_state.get("summary") or "", count)
    linked = [x for x in linked_now(user, chat_state.get("linked")) if x.get("text")]
    if not linked:
        return own
    before = "\n\n".join(f"[From another chat: “{x.get('title') or 'a chat'}” with {x.get('character') or 'someone'}. "
                          f"It happened; the people who were there remember it]\n{x['text']}" for x in linked)
    return before + ("\n\n[This chat]\n" + own if own else "")


LINKED_CHATS = 3
FAVOURITES = 60  # ⭐ starred messages kept per chat


def _fav_places(favs, messages):
    """⭐ Where each starred message is now: messages before it may have been deleted, so it's found by its text;
    one that was edited away keeps its copy with "i": -1 (it shows in the list, not on a message)."""
    texts = [speaker_colors.strip_tags(m[2]) if isinstance(m, (list, tuple)) and len(m) > 2 else "" for m in messages]
    out = []
    for f in favs:
        i = f.get("i", -1)
        if not (isinstance(i, int) and 0 <= i < len(texts) and texts[i] == f["text"]):
            i = next((j for j, t in enumerate(texts) if t == f["text"]), -1)
        out.append({**f, "i": i})
    return out


def _what_a_chat_has(data):
    """(text, kind) another chat already holds, for free: its story memory, else its summary; ("", "") if neither."""
    text = story_memory.linked_text(data.get("memory"))
    if text:
        return text, "memory"
    msgs = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    text = chats.summary_text(chats.summary_parts(data, len(msgs)))
    return (text, "summary") if text.strip() else ("", "")


def linked_now(user, linked):
    """The linked chats with their text as of now: a live one reads the other chat's memory (or summary) each time,
    so it follows that chat as it goes on; a frozen one keeps the text it was brought in with."""
    from .models import Chat
    out = []
    for x in linked or []:
        if not isinstance(x, dict):
            continue
        if x.get("live"):
            chat = Chat.objects.filter(id=x.get("chat_id"), character__author=user).select_related("character").first()
            if chat is not None:
                try:
                    text, kind = _what_a_chat_has(chats.read(chat))
                except chats.ChatUnreadable:
                    text, kind = "", ""
                if text:
                    x = {**x, "text": text.strip()[:16000], "how": kind, "title": chat.title, "character": chat.character.name}
        out.append(x)
    return out


def _linkable_chats(user, current):
    """🔗 Their other chats (any character), newest first: what bringing each one in would take."""
    from .models import Chat
    out = []
    for chat in Chat.objects.filter(character__author=user).exclude(id=current.id if current else None).select_related("character").order_by("-time_update")[:300]:
        if len(out) >= 40:  # (chats with just a greeting are skipped, so look further than the first 40)
            break
        try:
            data = chats.read(chat)
        except chats.ChatUnreadable:
            continue
        msgs = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
        if len(msgs) < 2:
            continue
        parts = chats.summary_parts(data, len(msgs))
        upto = chats.summary_upto(parts)
        mem = story_memory.linked_text(data.get("memory"))
        has_text, has_kind = _what_a_chat_has(data)
        out.append({"id": chat.id, "title": chat.title, "character": chat.character.name, "count": len(msgs),
                    "tokens": sum(samplers.approx_tokens(_summary_line(m)) for m in msgs),
                    "has_summary": bool(parts), "summary_upto": upto,
                    "tokens_rest": sum(samplers.approx_tokens(_summary_line(m)) for m in msgs[upto:]),
                    "milestones": story_memory.milestone_count(data.get("memory")) if mem else 0,
                    "memory_tokens": samplers.approx_tokens(mem) if mem else 0,
                    "free": has_kind, "free_tokens": samplers.approx_tokens(has_text) if has_text else 0,
                    "updated": chat.time_update.strftime("%Y-%m-%d")})
    return out


def _link_chat(user, other, how):
    """(text, how) of another chat, for this one to remember: summarized anew ("anew"), or its own summary with
    the messages after it summarized onto it ("append"). Long chats go in pieces (the summary model's window)."""
    data = chats.read(other)
    msgs = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    parts = chats.summary_parts(data, len(msgs))
    if how == "memory":  # its milestones, people and relationships as they are: nothing to summarize
        text = story_memory.linked_text(data.get("memory"))
        if text:
            return text.strip()[:16000], "memory"
        how = "anew"
    if how == "append" and parts:
        earlier, start = chats.summary_text(parts), chats.summary_upto(parts)
    else:
        how, earlier, start = "anew", "", 0
    new = _summarize_pieces(user, msgs[start:], start, earlier) if msgs[start:] else []
    text = "\n\n".join(filter(None, [earlier, *[p["text"] for p in new]]))
    return text.strip()[:12000], how


NOTE_FRAME = "[Director's note, outside the story (not something said or done in it): {text}]"


def _write_mine(request, data, character, chat_obj, chat_state, messages, text_rules):
    """Write my message: the AI writes their next message, or writes out their draft. A dict for the page."""
    draft = text_rules("saved", str(data.get("text") or "").strip(), "user") if data.get("text") else ""
    preset = presets.normalize(presets.get_active(request.user).data)
    ask = (preset["utility"]["impersonation"].strip() or presets.UTILITY_DEFAULTS["impersonation"])
    preset = control.for_impersonation(preset)  # its "never write for {{user}}" rules don't apply here
    if draft:
        ask += ("\n\n[{{user}} sketched their next move below. Write it out as their full message, in the "
                "story's language and style and about as long as their earlier messages: what they say, "
                "and how they say and do it (tone, gesture, a small detail of the moment). Keep their intent "
                "and decisions; don't add new decisions for them, other characters' reactions or "
                f"outcomes.]\n{draft}")
    names = prompt_names(request.user, character, chat_state["persona"])
    ask = ask.replace("{{user}}", names["user"]).replace("{{char}}", names["char"])
    yours = speaker_colors.for_writing_user(speaker_colors.settings(character), names["user"])
    if yours:  # story colours: their lines in their own colour
        ask += "\n\n" + yours
    theirs = [m[2] for m in messages if isinstance(m, (list, tuple)) and len(m) > 2 and m[0] == "user" and not chats.is_note(m)]
    ask += "\n\n" + control.pov_note(control.pov_of(theirs, names["user"]), names["user"])  # their own point of view
    avoid = polish.avoid_line(request.user)  # 🛡 the same habits kept out of their message
    if avoid:
        ask += "\n" + avoid
    reading = translation.reading_language(request.user)  # read in another language: English, cleaned, translated
    english = translation.english_note(request.user)
    try:
        # As a user turn, so the request ends on one: Gemini and the newest Claude refuse a conversation that
        # ends on the model's own reply (OpenRouter moves system messages out of the conversation)
        built = build_chat_request(request.user, chat_obj, preset=preset, drop_last_reply=False,
                                   generation="impersonate",
                                   tail=[{"role": "user", "content": ask + (
                                       "\n\n" + english["content"] if english else "")}])
        message, _ = ai_client.complete_message(request.user, "chat", built["messages"], **built["params"])
        thought, written = thinking.split(message.get("content") or "")
        if not written.strip() and (thought or message.get("reasoning")):  # all thinking: once more without it
            _, model = ai_client.resolve(request.user, "chat")
            message, _ = ai_client.complete_message(request.user, "chat", built["messages"],
                                                    **thinking.without_thinking(model, built["params"]))
    except ai_client.AIError as e:
        return {"success": False, "error": str(e)}
    thought, written = thinking.split(message.get("content") or "")
    written = written.strip()
    if not written:
        why = ("The model used up the reply length thinking. Raise the reply length limit (Samplers) or "
               "ask Bulba." if thought or message.get("reasoning") else "The model sent back nothing. Try again.")
        return {"success": False, "error": why, "text": draft, "spending": ai_client.spending(request.user)}
    if draft and written.strip() == draft.strip():
        return {"success": False, "error": "The model gave your draft back unchanged. Try again, "
                "or add a word about what you want.", "text": draft, "spending": ai_client.spending(request.user)}
    # Bulba's polish: the habits they asked to have fixed, in their written-out message too
    fixed = []
    habits = polish.habits_for_draft(request.user, chat_obj, written, polish.others_before(messages, len(messages), "user"))
    if habits:
        try:
            written, fixed = polish.polish_text(request.user, character, chat_obj, written,
                                                polish.others_before(messages, len(messages), "user"),
                                                _story_text(request.user, chat_state, len(messages)), habits, whose="theirs")
        except ai_client.AIError as e:
            log.info("Polish skipped for a written message: %s", e)
    if reading and not translation.already_in(written, reading):  # into the language they write in
        try:
            written = translation.translate(request.user, written, reading,
                                            glossary=_glossary(request.user, character, chat_state))
        except ai_client.AIError as e:
            return {"success": False, "error": f"Written, but not translated: {e}",
                    "text": draft, "spending": ai_client.spending(request.user)}
    return {"success": True, "text": written, "polished": len(fixed), "spending": ai_client.spending(request.user)}


def _cut_echo(before, message):
    """`message` (a new reply) with any sentences that copy their latest message cut out (mainapp/echo.py), kept
    like a polish so Show original / Undo work. `before`: the chat up to the reply. Returns (message, its text)."""
    theirs = []
    for m in reversed(before):
        if m[0] == "assistant":
            break
        if m[0] == "user" and not chats.is_note(m):
            theirs.append(m[2])
    clean, cuts = echo.cut(message[2], "\n\n".join(reversed(theirs)))
    if not cuts:
        return message, message[2]
    rec = {**polish.record(message[2], cuts, [echo.HABIT]), "echo": True}
    return chats.with_polish(message, clean, rec), clean


def _history(messages, note_slot=False):
    """The chat as the AI reads it. Director's notes come framed as directions; with note_slot, a note at the very
    end is left out, because the request carries it in the preset's director's note slot."""
    out = []
    replies = [i for i, m in enumerate(messages) if m[0] == "assistant"]
    full = set(replies[-html_objects.KEEP_FULL:])  # older designed objects become a one-line label
    for i, m in enumerate(messages):
        if m[0] not in ("user", "assistant"):
            continue
        text = extras.for_prompt(chats.prompt_text(m), chats.game_of(m))
        if i not in full:
            text = html_objects.shrink(text)
        if chats.is_note(m):
            if note_slot and i == len(messages) - 1:
                continue
            text = NOTE_FRAME.replace("{text}", text)
        out.append({"role": m[0], "content": text})
    return out


def _user_pictured(user, chat_persona):
    """Their persona pictures show in this chat: they have some, and the chat uses their usual persona."""
    if not getattr(user, "persona_photo_neutral", None):
        return False
    own = (chat_persona or {}).get("name")
    return not own or own == (user.persona_name or "")


def _photo(character, prefix, emotion):
    """The sprite for an emotion (one of the nine, or one of the character's extra moods), falling back to neutral."""
    image = getattr(character, f"{prefix}_{emotion}", None) if emotion in sprite_mod.BUILT_IN else None
    if not image and prefix in ("photo", "photo_second") and emotion not in sprite_mod.BUILT_IN:
        extra = sprite_mod.url_of(character, prefix, emotion)
        if extra:
            return extra
    image = image or getattr(character, f"{prefix}_neutral", None)
    return image.url if image else None


@login_required
def chat(request, slug):
    # Only your own characters (and their chats) are reachable
    character = get_object_or_404(Character, slug=slug, author=request.user)

    # A main AI connection is needed before chatting
    if not ai_client.has_connection(request.user):
        if request.method == "POST":
            return JsonResponse({"error": "No AI connection is set up yet. Add one on the Connections page."},
                                status=400)
        return redirect("users:welcome")

    # --- Which chat (a character can have many) ---
    chat_obj = chats.current(character, request.GET.get("chat"))
    if not chat_obj.log_file:
        chats.write(chat_obj, {"messages": chats.greeting(character)})
    chat_file_path = chat_obj.log_file.path

    chat_state = {
        "summary": "",          # all summary pieces joined (what the prompt gets)
        "summary_upto": 0,      # number of messages already covered by the summary
        "summary_parts": [],    # [{"text", "from", "to"}], see chats.summary_parts
        "trackers": {},         # tracker values, locks and "upto" (see mainapp/trackers.py)
        "tracker_history": [],  # snapshots of the trackers by message count (for deletes and branches)
        "summary_paused": False,  # automatic summaries are paused for this chat
        "out_of_view": 0,  # the oldest messages the last reply's request couldn't hold (they need the summary)
        "memory": {},  # story memory (mainapp/story_memory.py)
        "linked": [],  # 🔗 up to 3 other chats this one remembers: [{chat_id, character, title, text, how, count}]
        "favourites": [],  # ⭐ messages they starred to read again: [{"i", "who", "text", "at"}] (a copy of the text)
        "summary_mode": "",  # "memory" or "manual" once chosen ("" = not yet: story_memory.chat_mode decides)
        "context_guides": {},
        "current_bg": "",
        "current_music": {},
        "skin": "",             # this chat's own chat style ("" = the character's; see CHAT_SKINS)
        "music_follow": {},     # {"on": bool, "since": replies since the last pick}: music follows the scene
        "last_recall": [],      # old messages free recall brought back for the last reply (see mainapp/recall.py)
        "persona": {},          # {"name", "description"}: who the user is in this chat only (else their usual persona)
        "game": {},             # dice and inventory: the starting inventory after manual edits (see mainapp/game.py)
        "voices": {},           # voices picked for speakers in this chat (see mainapp/voice.py), so they stay the same
        "story": {},            # story systems' values: meters, story time, events (see mainapp/story.py)
        "designs": {},          # the look of each kind of AI-designed object, kept the same (html_objects.py)
    }
    game_mode = game.mode_for(request.user, character)
    extra_kinds = extras.kinds_for(request.user)        # letters, phone screens, milestones (Extras page)
    # ...minus the ones the preset's AI-designed objects take over (never both for the same thing)
    taken = html_objects.replaced_kinds(presets.normalize(presets.get_active(request.user).data))
    extra_kinds = [k for k in extra_kinds if k not in taken]
    use_tools = game_mode != "off" or bool(extra_kinds) or bool(story.of_type(story.systems_of(character), "table"))

    def summary_payload():
        """What the summary panel shows."""
        task = ai_client.get_task_setting(request.user, "summary")
        _, model = ai_client.resolve(request.user, "summary")
        return {
            "summary": chat_state["summary"],
            "summary_upto": chat_state["summary_upto"],
            "parts": chat_state["summary_parts"],
            "total": len(messages),
            "first_uncovered": chats.first_uncovered(chat_state["summary_parts"], len(messages)),
            "out_of_view": min(chat_state["out_of_view"], len(messages)),
            "paused": chat_state["summary_paused"],
            "auto": task.mode == task.MODE_AUTO,
            "interval": task.interval,
            "model": model,
        }

    def set_summary(parts):
        chat_state["summary_parts"] = parts
        chat_state["summary"] = chats.summary_text(parts)
        chat_state["summary_upto"] = chats.summary_upto(parts)

    def load_messages():
        # chats.load_path: a broken file falls back to its backup, and raises rather than reading as empty (an
        # empty read used to put the greeting back and save it over the whole chat)
        data = chats.load_path(chat_file_path)
        if data is not None:
            if isinstance(data, dict):
                set_summary(chats.summary_parts(data, len(data.get("messages") or [])))
                chat_state["trackers"] = data.get("trackers") or {}
                chat_state["tracker_history"] = data.get("tracker_history") or []
                chat_state["summary_paused"] = bool(data.get("summary_paused"))
                chat_state["out_of_view"] = int(data.get("out_of_view") or 0)
                chat_state["memory"] = data.get("memory") if isinstance(data.get("memory"), dict) else {}
                chat_state["linked"] = [x for x in (data.get("linked") or []) if isinstance(x, dict) and x.get("text")][:LINKED_CHATS]
                chat_state["favourites"] = [x for x in (data.get("favourites") or []) if isinstance(x, dict) and x.get("text")][-FAVOURITES:]
                chat_state["summary_mode"] = data.get("summary_mode") if data.get("summary_mode") in ("memory", "manual") else ""
                chat_state["context_guides"] = data.get("context_guides", {})
                chat_state["current_bg"] = data.get("current_bg", "")
                chat_state["current_music"] = data.get("current_music", {})
                chat_state["skin"] = data.get("skin") if data.get("skin") in (*CHAT_SKINS, *chat_looks.READY, "none", "custom") \
                    or str(data.get("skin") or "").startswith("shelf:") else ""
                chat_state["music_follow"] = data.get("music_follow") if isinstance(data.get("music_follow"), dict) else {}
                chat_state["last_recall"] = data.get("last_recall") if isinstance(data.get("last_recall"), list) else []
                chat_state["persona"] = data.get("persona") if isinstance(data.get("persona"), dict) else {}
                if "persona" not in data and isinstance((character.theme or {}).get("story_persona"), dict):
                    chat_state["persona"] = dict(character.theme["story_persona"])  # 🎭 a new chat: their story's persona
                chat_state["game"] = data.get("game") if isinstance(data.get("game"), dict) else {}
                chat_state["voices"] = data.get("voices") if isinstance(data.get("voices"), dict) else {}
                chat_state["story"] = data.get("story") if isinstance(data.get("story"), dict) else {}
                chat_state["designs"] = data.get("designs") if isinstance(data.get("designs"), dict) else {}
                messages_list = data.get("messages", [])
            else:
                messages_list = data


            fixed_messages = []
            for msg in messages_list:

                if len(msg) == 3: # (role, time, text)
                    fixed_messages.append((msg[0], msg[1], msg[2], "neutral", 1))
                elif len(msg) == 4: # (role, time, text, emotion)
                    fixed_messages.append((msg[0], msg[1], msg[2], msg[3], 1))
                elif len(msg) >= 5: # New format, plus swipes (see chats.add_version)
                    fixed_messages.append(tuple(msg[:6]) if len(msg) > 5 and isinstance(msg[5], dict)
                                          else tuple(msg[:5]))

            # The greeting was filled with whatever name they had then (often the login, before a persona)
            u = request.user
            fixed_messages, renamed = chats.refresh_greeting(
                fixed_messages, character, prompt_names(u, character, chat_state["persona"])["user"],
                [u.username, u.name, getattr(u, "persona_name", ""), "Stranger", "You"])
            if renamed:
                chats.write(chat_obj, {**chats.read(chat_obj), "messages": fixed_messages})
            if not chat_state["designs"]:  # a chat from before: its objects' first looks, from the history
                for m in fixed_messages:
                    if m[0] == "assistant":
                        html_objects.remember(chat_state["designs"], m[2])
            return fixed_messages
        else:
            return []

    # --- Text rules (regex scripts) from the active preset and the character card ---
    def text_rules(mode, text, role, edits_only=False):
        rules = regex_rules.for_chat(presets.normalize(presets.get_active(request.user).data), character, request.user)
        if edits_only:
            rules = [r for r in rules if r["run_on_edit"]]
        return regex_rules.run(rules, mode, text, role, prompt_names(request.user, character, chat_state["persona"]))

    # --- Save messages to file ---
    def game_trackers():
        """The tracker panel's state when the app keeps some trackers (sent back after replies and swipes)."""
        if game_mode != "full" and not {"milestones", "keepsakes"} & set(extra_kinds):
            return None
        return trackers.normalize_state(chat_state["trackers"], trackers.normalize_config(character.tracker_config, game_mode, "milestones" in extra_kinds,
            "keepsakes" in extra_kinds))

    systems = story.systems_of(character)  # Lattice-style story systems Bulba set up for this character

    def story_state():
        chat_state["story"] = story.state_of(chat_state["story"], systems)
        return chat_state["story"]

    def _synced(state):
        """The tracker state with the World's date and time from the story clock (when there is one)."""
        if systems and isinstance(state.get("trackers"), dict):
            story.sync_world(story_state(), systems, state["trackers"])
        return state["trackers"]

    def story_payload():
        """What the tracker panel shows of the story systems (None when there are none)."""
        if not systems:
            return None
        st = story_state()
        return {"meters": [{"label": m["label"], "value": st["values"].get(m["id"]), "min": m["min"], "max": m["max"]}
                           for m in story.of_type(systems, "meter")],
                "clock": story.clock_text(st["minutes"]) if story.of_type(systems, "clock") else "",
                "next_events": story.upcoming(systems, st), "log": st["log"][-5:],
                "pending": bool(st.get("pending"))}

    def sync_game_trackers(messages):
        """Trackers the app keeps itself: Inventory and Conditions ("full" dice mode), Milestones (story extra)."""
        if game_mode != "full" and not {"milestones", "keepsakes"} & set(extra_kinds):
            return
        if not isinstance(chat_state["trackers"], dict):
            chat_state["trackers"] = {}
        values = chat_state["trackers"].setdefault("values", {})
        if game_mode == "full":
            state = game.current_state(chat_state, messages)
            values["inventory"], values["conditions"] = state["inventory"], state["conditions"]
        if "milestones" in extra_kinds:
            values["milestones"] = extras.milestones(messages)
        if "keepsakes" in extra_kinds:
            values["scrapbook"] = extras.keepsakes(messages)

    def chat_mode():
        """This chat's summary mode: story memory or the manual summary (story_memory.chat_mode)."""
        return story_memory.chat_mode(request.user, {"summary_mode": chat_state["summary_mode"],
                                                     "summary_parts": chat_state["summary_parts"],
                                                     "summary": chat_state["summary"]}, len(messages))

    def save_messages(messages):
        sync_game_trackers(messages)
        if not chat_state["summary_mode"]:  # decided once (a new chat: memory), so it doesn't change as it grows
            chat_state["summary_mode"] = story_memory.chat_mode(request.user, {"summary_parts": chat_state["summary_parts"],
                                                                               "summary": chat_state["summary"]}, len(messages))
        if chat_state["memory"]:  # deleted messages take what memory knew of them along
            chat_state["memory"] = story_memory.trim_to(chat_state["memory"], len(messages))
        full_data = {
            "messages": messages,
            "summary": chat_state["summary"],
            "summary_upto": chat_state["summary_upto"],
            "summary_parts": chat_state["summary_parts"],
            "summary_paused": chat_state["summary_paused"],
            "out_of_view": chat_state["out_of_view"],
            "memory": chat_state["memory"],
            "linked": chat_state["linked"],
            "favourites": chat_state["favourites"],
            "summary_mode": chat_state["summary_mode"],
            "trackers": chat_state["trackers"],
            "tracker_history": chat_state["tracker_history"],
            "context_guides": chat_state["context_guides"],
            "current_bg": chat_state["current_bg"],
            "current_music": chat_state["current_music"],
            "skin": chat_state["skin"],
            "music_follow": chat_state["music_follow"],
            "last_recall": chat_state["last_recall"],
            "persona": chat_state["persona"],
            "game": chat_state["game"],
            "voices": chat_state["voices"],
            "story": chat_state["story"],
            "designs": chat_state["designs"],
        }
        chats.save_path(chat_file_path, full_data)
        chat_obj.save(update_fields=["time_update"])

    def polish_unwatched():
        """A reply finished with nobody watching (they left the page): the automatic polish the page would have
        asked for, done here, so they come back to the polished reply (mainapp/live.py calls it)."""
        msgs = load_messages()
        if not msgs or msgs[-1][0] != "assistant" or not polish.due(request.user, chat_obj, msgs):
            return
        rec_now = chats.polish_of(msgs[-1])
        if rec_now and not rec_now.get("echo"):
            return
        original = msgs[-1][2]
        try:
            new_text, fixes = polish.polish(request.user, character, chat_obj, msgs, _story_text(request.user, chat_state, len(msgs)), len(msgs) - 1)
        except ai_client.AIError as e:
            log.info("Polish skipped for a reply nobody was watching: %s", e)
            return
        msgs = load_messages()  # read again: they may have come back meanwhile
        if not fixes or msgs[-1][0] != "assistant" or msgs[-1][2] != original:
            return
        habits = polish.habits_of(request.user, fixes)
        rec = (polish.record(rec_now["original"], (rec_now.get("fixes") or []) + fixes,
                             list(dict.fromkeys((rec_now.get("habits") or []) + habits)))
               if rec_now else polish.record(original, fixes, habits))
        msgs[-1] = chats.with_polish(msgs[-1], new_text, rec)
        save_messages(msgs)

    def after_unwatched():
        """Everything the page would have asked for after a reply nobody watched: the polish, then story memory."""
        try:
            polish_unwatched()
        finally:
            msgs = load_messages()
            if not msgs or chat_mode() != "memory" or not story_memory.due(request.user, chat_state["memory"], len(msgs)):
                return
            try:
                memory = story_memory.update(request.user, character, chat_state["memory"], msgs,
                                             prompt_names(request.user, character, chat_state["persona"]))
                chat_state["memory"] = story_memory.roll_arcs(request.user, memory)
            except ai_client.AIError as e:
                log.info("Story memory skipped for a reply nobody was watching: %s", e)
                return
            save_messages(load_messages_keep_memory(msgs))

    def load_messages_keep_memory(fallback):
        """The messages as saved now, keeping the memory just written (loading would put the saved one back)."""
        memory = chat_state["memory"]
        msgs = load_messages() or fallback
        chat_state["memory"] = memory
        return msgs

    try:
        messages = load_messages()
    except chats.ChatUnreadable:
        logging.getLogger(__name__).error("Chat %s: its file and backups can't be read", chat_obj.id)
        why = ("This chat's file couldn't be read, so nothing was changed or saved. Please don't start over: "
               "tell the app's owner, the chat can still be recovered from its backups.")
        if request.method == "POST":
            return JsonResponse({"success": False, "error": why}, status=503)
        return HttpResponse(why, status=503, content_type="text/plain; charset=utf-8")

    # --- Initial assistant message ---
    if not messages and character.initial_message:
        # Added ', 1' at the end for char_count
        messages.append(("assistant", datetime.now().strftime("%H:%M"), character.initial_message, "neutral", 1))
        save_messages(messages)

    # --- POST request ---
    if request.method == "POST":
        data = json.loads(request.body)
        action = data.get("action", "chat")
        regen_from = None  # the reply being regenerated; the new one becomes its next swipe
        # --- Chats: list, new, rename, delete ---
        if action == "new_chat_sources":  # + New chat → continue from: the chats that already have memory or a summary
            return JsonResponse({"success": True, "current": chat_obj.id,
                                 "chats": [c for c in _linkable_chats(request.user, None) if c["free"]]})
        if action in ("list_chats", "new_chat", "rename_chat", "delete_chat", "import_chat"):
            go_to = None
            if action == "new_chat":
                from .models import Chat
                source = Chat.objects.filter(id=data.get("continue_from") or 0, character__author=request.user).select_related("character").first()
                start = {"messages": chats.greeting(character)}
                if source is not None:  # 🔗 the new chat remembers that one, live
                    text, kind = _what_a_chat_has(chats.read(source))
                    if text:
                        start["linked"] = [{"chat_id": source.id, "character": source.character.name, "title": source.title,
                                            "text": text.strip()[:16000], "how": kind, "live": True,
                                            "at": datetime.now().strftime("%Y-%m-%d")}]
                go_to = chats.create(character, data=start).id
            elif action == "import_chat":  # a chat file (this app's, the rescue snippet's or SillyTavern's): a new chat
                try:
                    imported = chats.clean_import(data.get("chat"))
                except ValueError as e:
                    return JsonResponse({"success": False, "error": str(e)}, status=400)
                title = " ".join(str(data.get("title") or "").split())[:200] or "Imported chat"
                go_to = chats.create(character, title=title, data={"messages": imported}).id
            elif action in ("rename_chat", "delete_chat"):
                target = character.chats.filter(id=data.get("id")).first()
                if target is None:
                    return JsonResponse({"success": False, "error": "No such chat."}, status=404)
                if action == "rename_chat":
                    target.title = (data.get("title") or "").strip()[:200] or target.title
                    target.save(update_fields=["title"])
                else:
                    was_open = target.id == chat_obj.id
                    chats.delete(target)
                    if was_open:
                        go_to = chats.current(character).id
            return JsonResponse({"success": True, "chats": chats.summary_list(character, chat_obj.id),
                                 "go_to": go_to})

        # Handle edit action
        elif action == "edit":
            try:
                index = int(data.get("index"))
                new_text = data.get("text", "").strip()

                if not new_text:
                    return JsonResponse({"success": False, "error": "Message cannot be empty"})

                if 0 <= index < len(messages):
                    if chat_state["memory"]:  # what memory wrote about this message is looked at again
                        chat_state["memory"] = story_memory.mark_stale(chat_state["memory"], index)
                    # Update the message text, keep other fields
                    new_text = text_rules("saved", new_text, messages[index][0], edits_only=True)
                    reading = translation.reading_language(request.user)
                    if reading and messages[index][0] == "assistant" and translation.translation_of(messages[index]):
                        # They edited the translation they read: the English the story continues from follows it
                        shown = translation.display_text(messages[index], reading)
                        if new_text == shown:
                            return JsonResponse({"success": True, "text": new_text, "translated": True,
                                                 "watch": watch.page_state(request.user, chat_obj)})
                        try:
                            paired = translation.synchronize_edit(request.user, messages[index], new_text, reading,
                                                                  glossary=_glossary(request.user, character, chat_state))
                        except ai_client.AIError as e:
                            return JsonResponse({"success": False, "keep_draft": True,
                                                 "error": f"Couldn't update the English version, so nothing was saved: {e}"})
                        watch.note_signal(request.user, chat_obj, "edited", messages[index][2], paired[2])
                        messages[index] = paired
                        save_messages(messages)
                        return JsonResponse({"success": True, "text": new_text, "translated": True,
                                             "original": paired[2], "watch": watch.page_state(request.user, chat_obj)})
                    if messages[index][0] == "assistant" and messages[index][2] != new_text:
                        watch.note_signal(request.user, chat_obj, "edited", messages[index][2], new_text)
                        rec = chats.polish_of(messages[index])
                        if rec:  # they changed Bulba's polished version: ask what didn't work
                            watch.polish_rejected(request.user, chat_obj, index, "edited", rec, rec.get("habits"))
                    messages[index] = chats.set_text(messages[index], new_text)
                    html_objects.remember(chat_state["designs"], new_text, replace=True)  # their edit sets the look
                    save_messages(messages)
                    return JsonResponse({"success": True, "text": new_text,
                                         "watch": watch.page_state(request.user, chat_obj)})
                else:  # out of step with the page (a reply that failed and was never saved): reload it
                    return JsonResponse({"success": False, "resync": True,
                                         "error": "This chat changed since the page loaded. Reloading it."})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        elif action == "summary_translate":  # 🌐 in the summary panel: the pieces in the language they read
            reading = translation.reading_language(request.user)
            if not reading:
                return JsonResponse({"success": False, "error": "Your story language is English."})
            fresh = chats.read(chat_obj)
            cache = dict(fresh.get("translation_cache") or {})  # {fingerprint:language: text}, only for summaries
            out, changed = [], False
            try:
                for part in chat_state["summary_parts"]:
                    key = f"{translation.fingerprint(part['text'])}:{reading}"
                    if translation.already_in(part["text"], reading):  # an older summary written in it already
                        out.append(part["text"])
                        continue
                    if key not in cache:
                        cache[key] = translation.translate(request.user, part["text"], reading,
                                                           glossary=_glossary(request.user, character, chat_state))
                        changed = True
                    out.append(cache[key])
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            if changed:  # only this key changes in the file (the summary itself stays English)
                live = {f"{translation.fingerprint(p['text'])}:{reading}" for p in chat_state["summary_parts"]}
                fresh = chats.read(chat_obj)
                chats.write(chat_obj, {**fresh, "translation_cache": {k: v for k, v in cache.items() if k in live}})
            return JsonResponse({"success": True, "pieces": out, "language": translation.LANGUAGES[reading]})
        elif action == "translate":  # a reply (English) into the language they read, once it's written and polished
            reading = translation.reading_language(request.user)
            try:
                index = int(data.get("index"))
            except (TypeError, ValueError):
                return JsonResponse({"success": False, "error": "Invalid request data"})
            if not reading or not 0 <= index < len(messages) or messages[index][0] != "assistant":
                return JsonResponse({"success": False, "resync": not (0 <= index < len(messages)),
                                     "error": "Nothing to translate there."})
            done = translation.translation_of(messages[index])
            if done and done["language"] == reading:
                return JsonResponse({"success": True, "text": done["text"], "original": messages[index][2]})
            if translation.already_in(messages[index][2], reading):  # written in it before the workflow: as it is
                return JsonResponse({"success": True, "text": messages[index][2], "original": "", "same": True})
            source = messages[index][2]
            glossary = _glossary(request.user, character, chat_state)
            try:
                text = translation.translate(request.user, source, reading, glossary=glossary)
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            try:  # the letters, phone screens and the like in it: one more call, and they stay English if it fails
                extra_ops = translation.translate_extras(request.user, chats.game_of(messages[index]), reading, glossary)
            except ai_client.AIError as e:
                log.info("Story extras not translated: %s", e)
                extra_ops = []
            # The file as it is now (trackers or a summary may have been saved meanwhile): only this message changes
            fresh = chats.read(chat_obj)
            now = [tuple(m) for m in fresh.get("messages") or []]
            if not (0 <= index < len(now)) or now[index][2] != source:
                return JsonResponse({"success": False, "error": "The reply changed while it was being translated. "
                                                                 "Translate it again."})
            now[index] = translation.with_translation(now[index], text, reading, extra_ops)
            chats.write(chat_obj, {**fresh, "messages": now})
            return JsonResponse({"success": True, "text": text, "original": source,
                                 "extras_html": [extras.render(op) for op in translation.shown_extras(now[index], reading)
                                                 if extras.is_extra(op)]})

        # Handle delete action
        elif action == "delete":
            try:
                index = int(data.get("index"))
                if index == 0 and messages and messages[0][0] == "assistant":
                    return JsonResponse({"success": False, "error": "The opening message stays: edit it or swipe "
                                                                     "to another greeting instead."})

                if 0 <= index < len(messages):
                    # Delete message and all subsequent messages
                    messages = messages[:index]
                    # Summary pieces that covered deleted messages go; trackers rewind to before them
                    set_summary(chats.parts_within(chat_state["summary_parts"], len(messages)))
                    chat_state["trackers"], chat_state["tracker_history"] = chats.trackers_at(
                        chat_state["tracker_history"], chat_state["trackers"], len(messages))
                    if systems:  # story systems go back to before the deleted messages
                        chat_state["story"] = story.rewind(story_state(), len(messages))
                    save_messages(messages)
                    config = trackers.normalize_config(character.tracker_config, game_mode, "milestones" in extra_kinds,
            "keepsakes" in extra_kinds)
                    return JsonResponse({"success": True, "swipes": chats.version_info(messages),
                                         "summary": chat_state["summary"], "summary_upto": chat_state["summary_upto"],
                                         "summary_data": summary_payload(),
                                         "trackers": trackers.normalize_state(chat_state["trackers"], config),
                                         "story": story_payload()})
                else:  # the page shows a message the server never saved (a reply that failed): reload it
                    return JsonResponse({"success": False, "resync": True,
                                         "error": "This chat changed since the page loaded. Reloading it."})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        # --- A reply still being written (they left the page and came back): follow it, or stop it ---
        elif action == "follow":
            job = live_jobs.get(live_jobs.key(request.user, chat_obj, "reply"))
            if not job or job.done:
                return JsonResponse({"none": True, "done": bool(job)})
            response = StreamingHttpResponse(job.follow(), content_type="application/x-ndjson")
            response["Cache-Control"] = "no-cache"
            response["X-Accel-Buffering"] = "no"
            return response
        elif action == "stop_reply":
            job = live_jobs.get(live_jobs.key(request.user, chat_obj, "reply"))
            if job and not job.done:
                job.cancel = True
            return JsonResponse({"success": True})
        # --- "Write my message" that finished while they were away: its text, once ---
        elif action == "draft":
            job = live_jobs.get(live_jobs.key(request.user, chat_obj, "draft"))
            if not job:
                return JsonResponse({"state": "none"})
            if not job.done:
                return JsonResponse({"state": "running"})
            if data.get("take"):
                live_jobs.drop(live_jobs.key(request.user, chat_obj, "draft"))
            return JsonResponse({"state": "ready", **(job.result or {})})

        # --- Write my message (impersonate): the AI writes or expands the user's next message ---
        elif action == "expand":
            # Kept on the server too, so it lands in the box even if they left the page meanwhile (mainapp/live.py)
            draft_key = live_jobs.key(request.user, chat_obj, "draft")
            draft_job = live_jobs.start(draft_key, "draft")
            if draft_job is None:
                return JsonResponse({"success": False, "error": "Your message is already being written."})
            try:
                out = _write_mine(request, data, character, chat_obj, chat_state, messages, text_rules)
            except Exception as e:
                out = {"success": False, "error": f"Could not write it: {e}"}
            draft_job.finish(out)
            return JsonResponse(out)
        # --- 3. NEW: Spellcheck ---
        elif action == "spellcheck":
            text = data.get("text", "")
            if not text: return JsonResponse({"success": False})
            try:
                fixed = ai_client.complete(request.user, "writing_tools", [
                    {"role": "system", "content": "Correct grammar/spelling only. Output ONLY fixed text."},
                    {"role": "user", "content": text}])
                return JsonResponse({"success": True, "text": fixed})
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})

        # --- 4. NEW: Save Guides & Summary ---
        elif action == "save_guides":
            chat_state["context_guides"] = {"note": str(data.get("note") or "").strip()[:4000]}
            save_messages(messages) # Updates file
            return JsonResponse({"success": True})
        elif action == "voice":  # read one AI reply aloud (ElevenLabs), saved with that version of the reply
            from mainapp import voice
            key = get_elevenlabs_key(request.user)
            if not key:
                return JsonResponse({"success": False, "error": "Voices need an ElevenLabs key (Extras page)."})
            try:
                index = int(data.get("index"))
                message = messages[index]
            except (TypeError, ValueError, IndexError):
                return JsonResponse({"success": False, "error": "No such message."})
            if message[0] != "assistant":
                return JsonResponse({"success": False, "error": "Only the AI's replies are read aloud."})
            saved = chats.audio_of(message)
            if saved and not data.get("redo"):
                return JsonResponse({"success": True, "url": saved["url"], "cast": saved.get("cast", {})})
            try:
                audio, cast = voice.voice_reply(request.user, character, html_objects.strip(message[2]), chat_state["voices"],
                                                prompt_names(request.user, character, chat_state["persona"])["user"], key)
            except voice.VoiceError as e:
                return JsonResponse({"success": False, "error": str(e)})
            folder = os.path.join(settings.MEDIA_ROOT, "audio_files")
            os.makedirs(folder, exist_ok=True)
            name = f"{uuid.uuid4().hex}.mp3"
            with open(os.path.join(folder, name), "wb") as f:
                f.write(audio)
            old = (chats._extras(message).get("audio") or {}).get("url")
            if old and os.path.exists(os.path.join(folder, os.path.basename(old))):  # the outdated recording goes
                os.remove(os.path.join(folder, os.path.basename(old)))
            url = f"{settings.MEDIA_URL}audio_files/{name}"
            messages[index] = chats.with_audio(message, {"url": url, "text": message[2], "cast": cast})
            save_messages(messages)
            return JsonResponse({"success": True, "url": url, "cast": cast, "spending": ai_client.spending(request.user)})
        elif action == "ideas":  # Bulba's ideas: what to write next, or (directing) what could happen next
            mode = "director" if control.mode_of(presets.normalize(presets.get_active(request.user).data)) == "director" else "player"
            try:
                ideas = bulba_ideas(request.user, character, messages, mode, persona=chat_state["persona"],
                                    summary=chat_state.get("summary") or "")
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            return JsonResponse({"success": True, "ideas": ideas, "mode": mode, "spending": ai_client.spending(request.user)})
        elif action == "polish":  # Bulba's polish on the newest reply (the page asks right after it arrives)
            # now: they pressed "Fix this automatically" or 🧹 on a message (any reply, `index`): say why not
            now = bool(data.get("now"))
            again = bool(data.get("again"))  # "Rewrite it again": from the original, avoiding what they turned down
            try:
                index = int(data["index"]) if data.get("index") is not None else len(messages) - 1
            except (TypeError, ValueError):
                index = len(messages) - 1
            if again and 0 <= index < len(messages) and chats.polish_of(messages[index]):
                messages[index] = chats.with_polish(messages[index], chats.polish_of(messages[index])["original"], None)
                messages[index], _ = _cut_echo(messages[:index], messages[index])  # the copy stays out
                save_messages(messages)
            if now or again:
                reason = polish.why_not_now(request.user, chat_obj, messages, index)
                if reason:
                    return JsonResponse({"success": True, "changed": False, "reason": reason})
            elif index != len(messages) - 1 or not polish.due(request.user, chat_obj, messages) \
                    or (chats.polish_of(messages[-1]) and not chats.polish_of(messages[-1]).get("echo")):
                return JsonResponse({"success": True, "changed": False})
            original = messages[index][2]
            # 🧹 on a reply that's already polished: another pass over the polished text (each pass has its own
            # limits), the fixes added to the earlier ones and the model's original still kept for Undo. The same
            # for the automatic pass after a cut repeat of their message.
            rec_now = chats.polish_of(messages[index]) if 0 <= index < len(messages) else None
            earlier = rec_now if (now and not again) or (rec_now and rec_now.get("echo")) else None
            try:
                new_text, fixes = polish.polish(request.user, character, chat_obj, messages, _story_text(request.user, chat_state, len(messages)),
                                                index, full=now or again)  # (pressed by them: the whole check)
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            messages = load_messages()  # read again: they may have moved on while it worked
            if not fixes or index >= len(messages) or messages[index][0] != "assistant" \
                    or messages[index][2] != original:
                return JsonResponse({"success": True, "changed": False, "spending": ai_client.spending(request.user),
                                     "reason": ("Bulba found nothing more to change in that reply." if earlier else
                                                "Bulba found nothing to change in that reply.") if not fixes
                                     else "The reply changed meanwhile; nothing was replaced."})
            habits = polish.habits_of(request.user, fixes)
            rec = (polish.record(earlier["original"], (earlier.get("fixes") or []) + fixes,
                                 list(dict.fromkeys((earlier.get("habits") or []) + habits)))
                   if earlier else polish.record(original, fixes, habits))
            messages[index] = chats.with_polish(messages[index], new_text, rec)
            save_messages(messages)
            watch.recheck(request.user, chat_obj, messages)
            return JsonResponse({"success": True, "changed": True, "reply": new_text, "index": index,
                                 "polish": polish.page_payload(chats.polish_of(messages[index])),
                                 "spending": ai_client.spending(request.user)})
        elif action == "polish_undo":  # back to the reply as the model wrote it
            try:
                index = int(data.get("index"))
                rec = chats.polish_of(messages[index]) if 0 <= index < len(messages) else None
            except (TypeError, ValueError):
                rec = None
            if not rec:
                return JsonResponse({"success": False, "error": "Nothing to undo there."}, status=400)
            messages[index] = chats.with_polish(messages[index], rec["original"], None)
            save_messages(messages)
            if index == len(messages) - 1:
                watch.recheck(request.user, chat_obj, messages)
            watch.polish_rejected(request.user, chat_obj, index, "undid", rec, rec.get("habits"))  # ask what to do
            return JsonResponse({"success": True, "reply": rec["original"],
                                 "watch": watch.page_state(request.user, chat_obj)})
        elif action == "polish_feedback":  # 👍 / 👎 under "Bulba fixed N things"
            try:
                index = int(data.get("index"))
                rec = chats.polish_of(messages[index]) if 0 <= index < len(messages) else None
            except (TypeError, ValueError):
                rec = None
            if not rec or data.get("verdict") not in ("up", "down"):
                return JsonResponse({"success": False, "error": "Nothing to rate there."}, status=400)
            liked = data["verdict"] == "up"
            messages[index] = chats.with_polish(messages[index], messages[index][2],
                                                {**rec, "verdict": "liked" if liked else "disliked"})
            save_messages(messages)
            if liked:
                watch.polish_verdict(request.user, "liked")
            else:
                watch.polish_rejected(request.user, chat_obj, index, "disliked", rec, rec.get("habits"))
            return JsonResponse({"success": True, "watch": watch.page_state(request.user, chat_obj)})
        elif action == "watch":  # Bulba Watch reads the latest replies (the page asks after a reply)
            if watch.due(request.user, chat_obj, messages):
                writes = control.mode_of(presets.normalize(presets.get_active(request.user).data)) == "write"
                try:
                    watch.read(request.user, character, chat_obj, messages, writes_for_user=writes)
                except ai_client.AIError as e:
                    log.info("Bulba Watch skipped a read: %s", e)
            return JsonResponse({"success": True, "watch": watch.page_state(request.user, chat_obj)})
        elif action == "director_mode":  # a "Director mode?" note: switch at once, or undo it
            try:
                watch.switch_to_director(request.user, chat_obj, str(data.get("id") or ""), undo=bool(data.get("undo")))
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            return JsonResponse({"success": True, **_appearance(request.user),
                                 "watch": watch.page_state(request.user, chat_obj)})
        elif action == "watch_taste":  # the taste note's lines, corrected by them before Bulba words them
            try:
                watch.edit_taste_notice(request.user, chat_obj, str(data.get("id") or ""), data.get("lines"))
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            return JsonResponse({"success": True})
        elif action == "watch_note":  # a note: dismissed, "I don't mind this", or opened with Bulba
            if data.get("status") not in ("dismissed", "muted", "opened", "fix", "stop_fix"):
                return JsonResponse({"success": False, "error": "Unknown choice."}, status=400)
            try:
                watch.set_notice(request.user, chat_obj, str(data.get("id") or ""), data["status"])
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            return JsonResponse({"success": True, "watch": watch.page_state(request.user, chat_obj)})
        elif action == "director_switch":  # the pen menu's 🎭 switch: director mode on or off, no AI
            obj = presets.get_active(request.user)
            preset = presets.normalize(obj.data)
            now = control.mode_of(preset)
            if data.get("on"):
                if now != "director":
                    preset["extras"] = {**preset["extras"], "control_before": now}
                    preset = control.apply_to_preset(preset, "director")
                set_layout(request.user, "book")
            else:
                before = preset["extras"].get("control_before")
                preset = control.apply_to_preset(preset, before if before in ("dont", "write") else "dont")
                preset["extras"] = {k: v for k, v in preset["extras"].items() if k != "control_before"}
                set_layout(request.user, "chat")
            obj.data = preset
            obj.save(update_fields=["data", "time_update"])
            return JsonResponse({"success": True, "on": control.mode_of(preset) == "director",
                                 "layout": "book" if data.get("on") else "chat"})
        elif action == "mature":  # the pen menu's 18+ switch: edits the active preset directly (no AI)
            error = mature.switch(request.user, bool(data.get("on")), bool(data.get("adult")))
            if error:
                return JsonResponse({"success": False, "error": error})
            return JsonResponse({"success": True, "on": bool(data.get("on"))})
        elif action == "refusal_model":  # asked once: which model steps in when a reply is refused
            try:
                refusals.choose(request.user, str(data.get("model") or ""), ai_client.resolve(request.user, "chat")[1])
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            return JsonResponse({"success": True})
        elif action == "set_skin":  # the pen menu's chat style: this chat only ("" = the character's)
            skin = str(data.get("skin") or "")
            if skin not in CHAT_SKINS and skin not in chat_looks.READY and skin not in ("", "none", "custom") \
                    and not (skin.startswith("shelf:") and chat_looks.from_shelf(request.user, skin[6:])):
                return JsonResponse({"success": False, "error": "Unknown style."}, status=400)
            chat_state["skin"] = skin
            save_messages(messages)
            return JsonResponse({"success": True, "skin": chat_skin(character, skin)})
        elif action == "shelf":  # the pen menu's "Your looks": give one to this character, or take it off the shelf
            shelf_id = str(data.get("id") or "")
            found = chat_looks.from_shelf(request.user, shelf_id)
            if not found:
                return JsonResponse({"success": False, "error": "That look isn't on your shelf any more."}, status=400)
            if data.get("do") == "remove":
                chat_looks.drop(request.user, shelf_id)
                if chat_state.get("skin") == f"shelf:{shelf_id}":
                    chat_state["skin"] = ""
                    save_messages(messages)
            elif data.get("do") == "give":  # this character's own look from now on
                character.theme = {**(character.theme or {}), "look": found, "skin": "custom"}
                character.save(update_fields=["theme"])
                chat_state["skin"] = ""
                save_messages(messages)
            return JsonResponse({"success": True})
        elif action == "delete_thoughts":  # a reply's thinking block, gone (the reply stays)
            try:
                index = int(data.get("index"))
                message = messages[index]
            except (TypeError, ValueError, IndexError):
                return JsonResponse({"success": False, "error": "No such message."})
            messages[index] = chats.with_reasoning(message, "")
            save_messages(messages)
            return JsonResponse({"success": True})
        elif action == "look_adjust":  # the pen menu's "Adjust the look": a few colours, the background
            look = chat_looks.clean((character.theme or {}).get("look"))
            if not look or not isinstance(data.get("changes"), dict):
                return JsonResponse({"success": False, "error": "This character has no custom look yet."}, status=400)
            allowed = {"colors", "background", "picture", "veil"}
            changes = {k: v for k, v in data["changes"].items() if k in allowed}
            character.theme = {**(character.theme or {}), "look": chat_looks.merge(look, changes)}
            character.save(update_fields=["theme"])
            chat_looks.keep(request.user, character.theme["look"])  # the shelf keeps the newest version
            return JsonResponse({"success": True, "look": character.theme["look"]})
        elif action == "persona_hint_seen":  # "Who are you in the story?" is asked once per account
            settings_obj, _ = ChatSettings.objects.get_or_create(author=request.user)
            settings_obj.appearance = {**(settings_obj.appearance or {}), "persona_hint_seen": True}
            settings_obj.save(update_fields=["appearance"])
            return JsonResponse({"success": True})
        elif action == "thinking":  # 🧠 the pen menu: how much the chat model thinks before story replies
            _, chat_model = ai_client.resolve(request.user, "chat")
            try:
                samplers.set_thinking(request.user, str(data.get("level") or ""), chat_model)
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            return JsonResponse({"success": True, "level": samplers.thinking_now(request.user)})
        elif action == "forms_hint_seen":  # "your worldbook got better at Ukrainian" is shown once per account
            settings_obj, _ = ChatSettings.objects.get_or_create(author=request.user)
            settings_obj.appearance = {**(settings_obj.appearance or {}), "forms_hint_seen": True}
            settings_obj.save(update_fields=["appearance"])
            return JsonResponse({"success": True})
        elif action == "watch_settings":  # the first-time note's buttons, and "off in this chat"
            if "keep_on" in data:
                watch.intro_seen(request.user, bool(data["keep_on"]))
            if "chat_off" in data:
                watch.set_chat_off(chat_obj, bool(data["chat_off"]))
            if data.get("turn_on"):  # the pen menu's switch, turned on while Watch was off everywhere
                watch.set_on(request.user, True)
            return JsonResponse({"success": True, "watch": watch.page_state(request.user, chat_obj)})
        elif action in ("condense", "condense_undo"):  # one message, shortened for the AI (the screen keeps it whole)
            try:
                index = int(data.get("index"))
                if not 0 <= index < len(messages):
                    raise ValueError
            except (TypeError, ValueError):
                return JsonResponse({"success": False, "error": "No such message."}, status=400)
            text = ""
            if action == "condense":
                text = str(data.get("text") or "").strip()[:4000]  # their own edit, or a new one written now
                if not text:
                    try:
                        text = condense(request.user, character, messages[index], chat_state["persona"])
                    except ai_client.AIError as e:
                        return JsonResponse({"success": False, "error": str(e)})
            messages[index] = chats.with_condensed(messages[index], text)
            save_messages(messages)
            return JsonResponse({"success": True, "condensed": text, "spending": ai_client.spending(request.user)})
        elif action == "favourite":  # ⭐ star a message to read it again (or unstar it)
            try:
                index = int(data.get("index"))
                msg = messages[index]
            except (TypeError, ValueError, IndexError):
                return JsonResponse({"success": False, "error": "No such message."})
            text = speaker_colors.strip_tags(msg[2])
            chat_state["favourites"] = _fav_places(chat_state["favourites"], messages)
            had = [x for x in chat_state["favourites"] if x.get("i") == index]
            if msg[0] == "assistant":  # ⭐ its spoken lines become (or stop being) voice examples for the character
                favourites.remember(character, msg[2], starred=not (had or data.get("remove")))
            if had or data.get("remove"):
                chat_state["favourites"] = [x for x in chat_state["favourites"] if x.get("i") != index]
            else:
                names = prompt_names(request.user, character, chat_state["persona"])
                chat_state["favourites"] = (chat_state["favourites"] + [{
                    "i": index, "who": names["user"] if msg[0] == "user" else character.name, "role": msg[0],
                    "text": text[:20000], "at": datetime.now().strftime("%Y-%m-%d")}])[-FAVOURITES:]
            save_messages(messages)
            return JsonResponse({"success": True, "favourites": chat_state["favourites"], "starred": not had})
        elif action == "ai_saw":  # the pen menu's "What the AI saw": summary, pinned note, trackers, lore
            from .bulba import memory
            return JsonResponse({"success": True, **memory.what_the_ai_saw(chat_obj)})
        elif action == "note_ideas":  # "Be creative": Bulba writes two director's notes, a logical one and a bold one
            try:
                ideas = note_ideas(request.user, character, messages, _story_text(request.user, chat_state, len(messages)), chat_state["persona"])
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            return JsonResponse({"success": True, **ideas, "spending": ai_client.spending(request.user)})
        elif action == "word_note":  # Bulba turns a rough wish into a clear director's note
            try:
                note = word_note(request.user, character, messages, str(data.get("text") or ""),
                                 rewrite=bool(data.get("rewrite")), persona=chat_state["persona"])
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            return JsonResponse({"success": True, "note": note, "spending": ai_client.spending(request.user)})

        # ... inside chat view POST handler ...
        elif action == "toggle_tracker":  # the tracker rail's Stop tracking / ＋: for this character, as on its Trackers page
            tid = data.get("tracker")
            if tid not in trackers.TRACKERS_BY_ID:
                return JsonResponse({"success": False, "error": "No such tracker."}, status=400)
            raw = dict(character.tracker_config or {})
            switched = dict(raw.get("trackers") or {})
            switched[tid] = {**(switched.get(tid) if isinstance(switched.get(tid), dict) else {}), "on": bool(data.get("on"))}
            character.tracker_config = trackers.normalize_config({**raw, "trackers": switched})
            character.save(update_fields=["tracker_config"])
            page = _tracker_page_data(request.user, character, _synced(chat_state))
            return JsonResponse({"success": True, "config": page["config"], "specs": page["specs"], "state": page["state"]})
        elif action in ("update_trackers", "save_trackers", "clear_trackers"):
            config = trackers.normalize_config(character.tracker_config, game_mode, "milestones" in extra_kinds,
            "keepsakes" in extra_kinds)
            state = trackers.normalize_state(chat_state["trackers"], config)

            if action == "save_trackers":  # manual edits and locks from the panel
                state = trackers.normalize_state(
                    {"values": data.get("values"), "locks": data.get("locks"), "upto": state["upto"]}, config)
                if game_mode == "full":  # an edited inventory is the new starting point
                    game.set_base(chat_state, {k: state["values"].get(k, []) for k in game.OWNED_TRACKERS}, len(messages))
            elif action == "clear_trackers":
                state = {"values": {}, "locks": [], "upto": len(messages)}
                if game_mode == "full":
                    game.set_base(chat_state, game.empty_state(), len(messages))
            else:
                only = [t for t in data.get("only") or [] if isinstance(t, str)] or None
                with_story = not only and story.needs_ai(systems)  # meters and the story clock ride on this call
                if not trackers.ai_trackers(config) and not with_story:
                    return JsonResponse({"success": False, "error": "No trackers are turned on for this character."})
                # Messages since the last run (at least the last 4, at most 16)
                upto = state["upto"] if isinstance(state["upto"], int) else 0
                recent = messages[min(upto, len(messages)):]
                recent = (messages[-4:] if len(recent) < 4 else recent)[-16:]
                user_name = prompt_names(request.user, character, chat_state["persona"])["user"]  # the persona, never the login
                named = [(user_name if m[0] == "user" else character.name, html_objects.shrink(m[2])) for m in recent]
                def tracker_request(named):
                    built = trackers.update_messages(config, state, named, character.name, user_name, only,
                                                     rules=presets.job_prompt(request.user, "tracker_rules",
                                                                              {"char": character.name, "user": user_name})
                                                     + translation.tracker_language_rule(request.user))
                    if with_story:
                        built[0]["content"] += "\n\n" + story.prompt_section(systems, story_state())
                    return built

                # Within the tracker model's window: the oldest messages go first (the latest scene matters most),
                # then a single very long message keeps its end
                window = samplers.job_window(request.user, "trackers")
                size = lambda built: sum(samplers.approx_tokens(m["content"]) for m in built)
                request_messages = tracker_request(named)
                while len(named) > 1 and size(request_messages) > window:
                    named = named[1:]
                    request_messages = tracker_request(named)
                if size(request_messages) > window:
                    rest = size(request_messages) - samplers.approx_tokens(named[0][1])
                    named = [(named[0][0], samplers.cut_to(named[0][1], window - rest))]
                    request_messages = tracker_request(named)
                if size(request_messages) > window:
                    return JsonResponse({"success": False, "error": "The trackers hold more than the tracker model can "
                                         "read at once. Clear some entries, or pick a model with a larger window on "
                                         "the Connections page."})
                try:
                    reply_text = ai_client.complete(request.user, "trackers", request_messages,
                                                    temperature=0.2, response_format={"type": "json_object"})
                    update = trackers.parse_update(reply_text)
                except (ai_client.AIError, ValueError) as e:
                    return JsonResponse({"success": False, "error": str(e)})
                if with_story:  # held until they reply to this reply (only kept scenes count)
                    last = messages[-1] if messages else None
                    if last and last[0] == "assistant":
                        story.stage(story_state(), update, len(messages), last[2])
                update.pop("_story", None)
                if story.of_type(systems, "clock") and isinstance(update.get("world"), dict):
                    update["world"] = {k: v for k, v in update["world"].items() if k not in ("date", "time")}
                changed = trackers.apply_update(config, state, update, only)
                if not only:
                    state["upto"] = len(messages)
            if systems:  # with a story clock, the World tracker's date and time always show it
                story.sync_world(story_state(), systems, state)

            chat_state["trackers"] = state
            chat_state["tracker_history"] = chats.add_snapshot(chat_state["tracker_history"], state, len(messages))
            save_messages(messages)
            return JsonResponse({"success": True, "state": state, "changed": changed if action == "update_trackers" else [],
                                 "story": story_payload()})

        # --- Summary: pieces that each cover a range of messages ---
        elif action in ("memory", "memory_mode", "memory_run", "memory_edit", "memory_redo", "memory_settings"):
            # Story memory (mainapp/story_memory.py): the Summary panel's Story memory tab
            names = prompt_names(request.user, character, chat_state["persona"])
            try:
                if action == "memory_mode":
                    if data.get("mode") not in ("memory", "manual"):
                        raise ValueError("Pick memory or manual.")
                    chat_state["summary_mode"] = data["mode"]
                elif action == "memory_settings":
                    task = ai_client.get_task_setting(request.user, "memory")
                    if data.get("every"):
                        task.interval = max(1, min(100, int(data["every"])))
                    if isinstance(data.get("automatic"), bool):
                        task.mode = task.MODE_AUTO if data["automatic"] else task.MODE_MANUAL
                    task.save()
                elif action == "memory_run":  # an update: the new messages, or a chunk of an older chat (catch-up)
                    chunk = story_memory.CATCH_UP_CHUNK if data.get("catch_up") else None
                    if data.get("quiet") and not story_memory.due(request.user, chat_state["memory"], len(messages)):
                        return JsonResponse({"success": True, "skipped": True,
                                             **story_memory.page_payload(chat_state["memory"], request.user, chat_mode())})
                    try:
                        memory = story_memory.update(request.user, character, chat_state["memory"], messages, names,
                                                     chunk=chunk)
                        memory = story_memory.roll_arcs(request.user, memory)
                    except ai_client.AIError as e:
                        raise ValueError(str(e))
                    chat_state["memory"] = memory
                elif action == "memory_edit":
                    chat_state["memory"] = story_memory.edit(chat_state["memory"], data)
                elif action == "memory_redo":
                    try:
                        chat_state["memory"] = story_memory.redo_milestone(request.user, chat_state["memory"], messages,
                                                                           names, str(data.get("id") or ""))
                    except ai_client.AIError as e:
                        raise ValueError(str(e))
            except (ValueError, TypeError) as e:
                return JsonResponse({"success": False, "error": str(e) or "That didn't work."})
            if action != "memory":
                save_messages(messages)
            payload = story_memory.page_payload(chat_state["memory"], request.user, chat_mode())
            return JsonResponse({"success": True, **payload, "total": len(messages),
                                 "left": max(0, len(messages) - story_memory.clean(chat_state["memory"])["upto"]),
                                 "spending": ai_client.spending(request.user)})
        elif action in ("linkable_chats", "link_chat", "unlink_chat", "freeze_link"):  # 🔗 other chats this one remembers
            from .models import Chat
            if action == "linkable_chats":
                taken = {x.get("chat_id") for x in chat_state["linked"]}
                return JsonResponse({"success": True, "linked": linked_now(request.user, chat_state["linked"]), "max": LINKED_CHATS,
                                     "chats": [c for c in _linkable_chats(request.user, chat_obj) if c["id"] not in taken]})
            if action == "unlink_chat":
                chat_state["linked"] = [x for x in chat_state["linked"] if x.get("chat_id") != data.get("chat_id")]
            elif action == "freeze_link":  # ❄ keep it as it is now / ▶ follow that chat again
                now = linked_now(request.user, chat_state["linked"])
                for i, x in enumerate(chat_state["linked"]):
                    if x.get("chat_id") == data.get("chat_id"):
                        chat_state["linked"][i] = {**now[i], "live": not data.get("freeze"),
                                                   "at": datetime.now().strftime("%Y-%m-%d")}
            else:
                if len(chat_state["linked"]) >= LINKED_CHATS:
                    return JsonResponse({"success": False, "error": f"Up to {LINKED_CHATS} chats: take one out first."})
                other = Chat.objects.filter(id=data.get("chat_id"), character__author=request.user).select_related("character").first()
                if other is None or other.id == chat_obj.id:
                    return JsonResponse({"success": False, "error": "That chat is gone."})
                live = data.get("how") == "live"
                try:
                    if live:
                        text, how = _what_a_chat_has(chats.read(other))
                        if not text:
                            return JsonResponse({"success": False, "error": "That chat has no story memory or summary yet. "
                                                 "Pick “Summarize it anew” instead."})
                    else:
                        text, how = _link_chat(request.user, other, data.get("how"))
                except ai_client.AIError as e:
                    return JsonResponse({"success": False, "error": str(e)})
                if not text:
                    return JsonResponse({"success": False, "error": "That chat has nothing to remember yet."})
                chat_state["linked"] = [x for x in chat_state["linked"] if x.get("chat_id") != other.id] + [
                    {"chat_id": other.id, "character": other.character.name, "title": other.title, "text": text.strip()[:16000],
                     "how": how, "live": live, "at": datetime.now().strftime("%Y-%m-%d")}]
            save_messages(messages)
            return JsonResponse({"success": True, "linked": linked_now(request.user, chat_state["linked"])})

        elif action in ("summarize", "summary_edit", "summary_delete", "summary_rerun", "summary_pause"):
            parts = list(chat_state["summary_parts"])
            total = len(messages)

            def piece_index():
                i = data.get("piece")
                if not isinstance(i, int) or not 0 <= i < len(parts):
                    raise ValueError("No such summary piece.")
                return i

            try:
                if action == "summary_pause":
                    chat_state["summary_paused"] = bool(data.get("paused"))
                elif action == "summary_edit":
                    i = piece_index()
                    text = (data.get("text") or "").strip()
                    if not text:
                        raise ValueError("A summary piece can't be empty. Delete it instead.")
                    parts[i] = {**parts[i], "text": text}
                elif action == "summary_delete":
                    parts.pop(piece_index())
                else:
                    if action == "summary_rerun":
                        i = piece_index()
                        start, stop = parts[i]["from"], parts[i]["to"]
                        parts.pop(i)
                    elif data.get("mode") == "regen":  # everything again, as one piece
                        start, stop, parts = 0, total, []
                    else:
                        # From the first message no piece covers, up to `to` (default: all)
                        start = data.get("from", chats.first_uncovered(parts, total))
                        gap_end = min([p["from"] for p in parts if isinstance(start, int) and p["from"] >= start] + [total])
                        stop = data.get("to", gap_end)
                    if not (isinstance(start, int) and isinstance(stop, int) and 0 <= start < stop <= total):
                        raise ValueError("Nothing new to summarize yet." if start == total else "That range doesn't work.")
                    if any(p["from"] < stop and start < p["to"] for p in parts):
                        raise ValueError("Part of that range is already summarized.")
                    if stop - start < 2 and data.get("mode") == "regen":
                        raise ValueError("Not enough history.")
                    earlier = chats.summary_text([p for p in parts if p["to"] <= start])
                    try:
                        new_parts = _summarize_pieces(request.user, messages[start:stop], start, earlier)
                    except ai_client.AIError as e:
                        raise ValueError(str(e))
                    parts = sorted(parts + new_parts, key=lambda p: p["from"])
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)})

            set_summary(parts)
            save_messages(messages)
            return JsonResponse({"success": True, **summary_payload()})

        # --- Branches: a new chat with the messages up to here ---
        elif action in ("branch_info", "branch"):
            try:
                count = int(data.get("index")) + 1
            except (TypeError, ValueError):
                count = 0
            if not 1 <= count <= len(messages):
                return JsonResponse({"success": False, "error": "No such message."})
            parts = chats.parts_within(chat_state["summary_parts"], count)
            tracker_state, tracker_history = chats.trackers_at(
                chat_state["tracker_history"], chat_state["trackers"], count)
            if action == "branch_info":
                _, summary_model = ai_client.resolve(request.user, "summary")
                return JsonResponse({"success": True, "count": count, "summary": chats.summary_text(parts),
                                     "summary_upto": chats.summary_upto(parts), "summary_model": summary_model,
                                     "has_trackers": bool((tracker_state or {}).get("values")),
                                     "milestones": story_memory.milestone_count(chat_state["memory"], count)})

            summary_mode = data.get("summary_mode", "transfer")
            if summary_mode == "rerun":
                try:
                    parts = _summarize_pieces(request.user, messages[:count], 0)
                except ai_client.AIError as e:
                    return JsonResponse({"success": False, "error": str(e)})
            elif summary_mode == "transfer":
                edited = data.get("summary_text")
                if isinstance(edited, str) and edited.strip() != chats.summary_text(parts).strip():
                    # An edited summary becomes one piece covering what the pieces covered
                    parts = ([{"text": edited.strip(), "from": 0, "to": chats.summary_upto(parts) or count}]
                             if edited.strip() else [])
            else:
                parts = []
            if data.get("trackers_mode") == "clear":
                tracker_state, tracker_history = {}, []

            branch_data = {
                "messages": messages[:count],
                "summary": chats.summary_text(parts),
                "summary_upto": chats.summary_upto(parts),
                "summary_parts": parts,
                "trackers": tracker_state,
                "tracker_history": tracker_history,
                "context_guides": chat_state["context_guides"],
                "current_bg": chat_state["current_bg"],
                "current_music": chat_state["current_music"],
            }
            # 🧠 story memory: the milestones up to here come along (a scene cut in half is marked to look at again)
            if data.get("memory_mode", "keep") == "keep" and story_memory.milestone_count(chat_state["memory"], count):
                branch_data["memory"] = story_memory.trim_to(chat_state["memory"], count)
                branch_data["summary_mode"] = "memory"
            elif chat_state.get("summary_mode"):
                branch_data["summary_mode"] = chat_state["summary_mode"]
            title = f"{chat_obj.title} ⑂ {chat_obj.branches.count() + 1}"[:200]
            branch = chats.create(character, title, branch_data, parent=chat_obj, branch_point=count)
            return JsonResponse({"success": True, "go_to": branch.id})

        # --- 5. NEW: Regenerate/Continue Logic ---
        elif action == "regenerate":
            # The old reply is only replaced once the new one arrives (and is kept as a swipe)
            if messages and messages[-1][0] == "assistant":
                regen_from = messages.pop()
                # the trackers go back to before the reply being rewritten (the new one updates them again)
                chat_state["trackers"], chat_state["tracker_history"] = chats.trackers_at(
                    chat_state["tracker_history"], chat_state["trackers"], len(messages))
                watch.note_signal(request.user, chat_obj, "rewritten", regen_from[2])
                rec = chats.polish_of(regen_from)
                if rec:  # a polished reply thrown away: did the polish miss? (the card shows with the new reply)
                    watch.polish_rejected(request.user, chat_obj, len(messages), "regenerated", rec, rec.get("habits"))

        elif action == "swipe":
            if not messages or messages[-1][0] != "assistant":
                return JsonResponse({"success": False, "error": "Only the AI's last reply can be swiped."})
            try:
                messages[-1] = chats.choose_version(messages[-1], int(data.get("to")))
            except (TypeError, ValueError, IndexError):
                return JsonResponse({"success": False, "error": "No such version."})
            # another version of the reply: the trackers go back to before it, then update from the one shown
            chat_state["trackers"], chat_state["tracker_history"] = chats.trackers_at(
                chat_state["tracker_history"], chat_state["trackers"], len(messages) - 1)
            swipe_config = trackers.normalize_config(character.tracker_config, game_mode, "milestones" in extra_kinds,
                                                     "keepsakes" in extra_kinds)
            if chat_state["memory"]:
                chat_state["memory"] = story_memory.mark_stale(chat_state["memory"], len(messages) - 1)
            save_messages(messages)
            _, _, text, emotion, char_count = messages[-1][:5]
            emo1, _, emo2 = (emotion or "neutral").partition("|")
            reading = translation.reading_language(request.user)
            return JsonResponse({
                "success": True, "reply": _shown(messages[-1], reading), "emotion": emotion, "char_count": char_count,
                "original": text if reading and _shown(messages[-1], reading) != text else "",
                "untranslated": bool(reading and not translation.translation_of(messages[-1])
                                     and not translation.already_in(text, reading)),
                "reasoning": chats.reasoning_of(messages[-1]),
                "game": [game.describe(op) for op in chats.game_of(messages[-1]) if not extras.is_extra(op)],
                "extras_html": [extras.render(op) for op in translation.shown_extras(messages[-1], reading)
                                if extras.is_extra(op)],
                "game_trackers": game_trackers(),
                "photo_url": _photo(character, "photo", emo1),
                "photo_second": _photo(character, "photo_second", emo2 or "neutral")
                if (character.is_mult or char_count >= 2) else None,
                "swipes": chats.version_info(messages),
                "polish": polish.page_payload(chats.polish_of(messages[-1])),
                "directed": chats.directed_of(messages[-1]),
                "trackers": trackers.normalize_state(chat_state["trackers"], swipe_config),
                "trackers_due": bool(trackers.ai_trackers(swipe_config))
                and ai_client.get_task_setting(request.user, "trackers").mode == ai_client.get_task_setting(request.user, "trackers").MODE_AUTO,
            })

        # --- 5. CONTINUE: the AI carries on its last reply, with the same preset, lore and summary ---
        elif action == "continue":
            if not messages or messages[-1][0] != "assistant":
                return JsonResponse({"success": False, "error": "Can only continue the AI's last message."})
            last_text = messages[-1][2]
            try:
                worldbook_slug = (character.worldbook.slug if character.worldbook
                                  and character.worldbook.author == request.user else None)
                prompt = build_ai_request(request.user, character, chat=chat_obj, worldbook_slug=worldbook_slug,
                                          message=None, guidance="",
                                          persistent_guides=chat_state["context_guides"],
                                          summary=_story_text(request.user, chat_state, len(messages)))
                preset = presets.normalize(presets.get_active(request.user).data)
                _, chat_model = ai_client.resolve(request.user, "chat")
                names = prompt_names(request.user, character, chat_state["persona"])
                history = _history(messages)
                history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, request.user), history, names)
                # The unfinished reply is the last message; the preset's continue nudge comes after it
                nudge = preset["utility"]["continue_nudge"].strip() or presets.UTILITY_DEFAULTS["continue_nudge"]
                # Gemini and the newest Claude don't continue a reply the request ends on (OpenRouter moves system
                # messages out): they write a new one. A user turn asks them plainly.
                nudge_role = "user" if str(chat_model).startswith(("google/", "anthropic/")) else "system"
                history.append({"role": nudge_role, "content": nudge})
                built, _ = recall.assemble_with_recall(
                    presets.assemble, preset, prompt_slots(request.user, character, prompt, chat_state["persona"]),
                    history, names, chat_model, generation="continue")
                english = translation.english_note(request.user)
                new_chunk = ai_client.complete(request.user, "chat", built["messages"] + ([english] if english else []),
                                               **built["params"])
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})

            new_chunk = _only_new(last_text, (new_chunk or "").rstrip())
            if new_chunk is None:
                return JsonResponse({"success": False, "error": "The model wrote the reply over again instead of "
                                                                 "continuing it, so nothing was added. Press Continue again."})
            if not new_chunk.strip():
                return JsonResponse({"success": False, "error": "The model had nothing to add. The reply stays as it is."})
            # Only the new part is cleaned of the known habits: what they already read stays word for word
            habits = polish.approved(request.user)
            if habits and not watch.chat_data(chat_obj).get("off"):
                try:
                    new_chunk, _fixed = polish.polish_text(request.user, character, chat_obj, new_chunk,
                                                           polish.others_before(messages, len(messages)),
                                                           _story_text(request.user, chat_state, len(messages)), habits)
                except ai_client.AIError as e:
                    log.info("Polish skipped for a continuation: %s", e)
            if new_chunk and not new_chunk[0].isspace() and new_chunk[0] not in ".,;:!?)…'\"" and not last_text.endswith((" ", "\n")):
                new_chunk = " " + new_chunk
            full_text = text_rules("saved", last_text + new_chunk, "assistant")
            reading = translation.reading_language(request.user)
            before = translation.translation_of(messages[-1]) if reading else None
            messages[-1] = chats._with(chats.set_text(messages[-1], full_text), "polish", None)  # its old Undo no longer fits
            shown = full_text
            if before and before["language"] == reading:
                # Read in another language: only the new part is translated; the translation they read stays
                try:
                    added = translation.translate(request.user, new_chunk.strip(), reading,
                                                  glossary=_glossary(request.user, character, chat_state))
                    shown = before["text"].rstrip() + ("\n\n" if new_chunk.startswith("\n") else " ") + added
                    messages[-1] = translation.with_translation(messages[-1], shown, reading, before.get("extras"))
                except ai_client.AIError as e:
                    log.info("Continuation not translated: %s", e)
                    shown = full_text
            save_messages(messages)
            return JsonResponse({"success": True, "reply": shown, "translated": shown != full_text,
                                 "original": full_text if shown != full_text else "",
                                 "polish_due": False})  # the new part is cleaned already; the rest stays
        elif action == "chat_persona":  # who the user is in this chat only; empty name = their usual persona
            name = str(data.get("name") or "").strip()[:100]
            chat_state["persona"] = ({"name": name, "description": str(data.get("description") or "").strip()[:8000]}
                                     if name else {})
            save_messages(messages)
            return JsonResponse({"success": True, "persona": chat_state["persona"],
                                 "name": prompt_names(request.user, character, chat_state["persona"])["user"]})
        elif action == "persona_to_account":  # this chat's persona becomes their usual one (the profile's)
            name = str(data.get("name") or "").strip()[:100]
            if not name:
                return JsonResponse({"success": False, "error": "Give the persona a name first."}, status=400)
            request.user.persona_name = name
            request.user.persona_description = str(data.get("description") or "").strip()[:8000]
            request.user.save(update_fields=["persona_name", "persona_description"])
            chat_state["persona"] = {}  # the chat now follows the usual persona, which is this one
            save_messages(messages)
            return JsonResponse({"success": True, "persona": {}, "name": name})
        elif action == "appearance" and "layout" in data:  # chat bubbles or chapters
            try:
                set_layout(request.user, data.get("layout"))
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            if data.get("layout") == "book":  # the look without director mode: Bulba offers the rest
                watch.offer_director_for_book(request.user, chat_obj)
            return JsonResponse({"success": True, **_appearance(request.user),
                                 "watch": watch.page_state(request.user, chat_obj)})
        elif action == "speech":  # speech colours (pen menu): the way, the cast's colours, theirs, tone marks
            theme = dict(character.theme or {})
            if data.get("mode") in speaker_colors.MODES:
                theme["speech"] = data["mode"]
                if data["mode"] == "story" and "cast" not in data:  # the character is in its own cast from the start
                    theme["speech_cast"] = speaker_colors.with_characters(theme, character)
            if "cast" in data:
                theme["speech_cast"] = speaker_colors.clean(data.get("cast"))
            if "you" in data:
                theme["you_color"] = speaker_colors.name_of(data.get("you"))
            if "tones" in data:
                theme["speech_tones"] = bool(data.get("tones"))
            character.theme = theme
            character.save(update_fields=["theme"])
            return JsonResponse({"success": True, "speech": speaker_colors.settings(character),
                                 **_appearance(request.user, character)})
        elif action == "appearance":  # the app colour (a palette name or its shade), kept on the character
            color = str(data.get("dialogue_color") or "")
            if color == "preset":  # older pages: "the preset's colours" is now the story-colours way
                character.theme = {**(character.theme or {}), "speech": "story"}
            else:
                name = speaker_colors.name_of(color)
                if not name and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    return JsonResponse({"success": False, "error": "Pick a colour."}, status=400)
                character.theme = {**(character.theme or {}), "dialogue_color": speaker_colors.PALETTE[name][0] if name else color}
            character.save(update_fields=["theme"])
            return JsonResponse({"success": True, **_appearance(request.user, character)})
        elif action == "save_theme":  # this chat's background or music becomes the character's default
            theme = dict(character.theme or {})
            if data.get("type") == "bg":
                theme["bg"] = str(data.get("url") or "")[:500]
            elif data.get("type") == "music":
                url = str(data.get("url") or "")[:500]
                theme["music"] = {"url": url, "name": str(data.get("name") or "")[:200]} if url else {}
            else:
                return JsonResponse({"success": False, "error": "Unknown kind."}, status=400)
            character.theme = theme
            character.save(update_fields=["theme"])
            return JsonResponse({"success": True, "theme": theme})
        elif action == "music_follow":  # let the music follow the scene (built-in tracks), or not
            chat_state["music_follow"] = {"on": bool(data.get("on")), "since": MUSIC_EVERY}
            save_messages(messages)
            return JsonResponse({"success": True, "on": chat_state["music_follow"]["on"]})
        elif action == "scene_music":  # pick the built-in track that fits the latest reply (one tiny call)
            follow = chat_state["music_follow"]
            if not follow.get("on") or follow.get("since", 0) < MUSIC_EVERY or not messages:
                return JsonResponse({"success": True, "music": None})
            try:
                pick = scene_music(request.user, messages, chat_state["current_music"].get("name", ""))
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            follow["since"] = 0
            changed = bool(pick and pick["name"] != chat_state["current_music"].get("name"))
            if changed:
                chat_state["current_music"] = pick
            save_messages(messages)
            return JsonResponse({"success": True, "music": pick if changed else None})
        elif action == "save_media":
            m_type = data.get("type")
            url = data.get("url")
            name = data.get("name")

            if m_type == "bg":
                chat_state["current_bg"] = url
            elif m_type == "music":
                if url:
                    chat_state["current_music"] = {"url": url, "name": name}
                else:
                    chat_state["current_music"] = {} # Clear/Stop music

            save_messages(messages)
            return JsonResponse({"success": True})
        # Handle regular chat message
        if action in ["chat", "regenerate", "continue"]:
            if action in ("chat", "regenerate") and live_jobs.running(live_jobs.key(request.user, chat_obj, "reply")):
                return JsonResponse({"error": "The last reply is still being written. Wait for it, or press Stop."},
                                    status=409)
            user_message = data.get("message", "").strip()
            guidance = data.get("guidance", "")

            if action == "continue":
                guidance = "CONTINUE the last response exactly where it ended. Do not repeat text. Flow naturally and logically finish it."

            # A director's note can be sent on its own: the story goes on with no message from them
            note_only = action == "chat" and not user_message and bool(guidance.strip())
            note = guidance.strip()[:2000] if action == "chat" else ""  # saved as a message of its own, after theirs
            redo = guidance.strip() if action == "regenerate" else ""  # a redo instruction from the pen menu
            directed = redo  # shown above the new reply: what steered it, when it isn't a message in the chat
            if action == "regenerate" and messages and chats.is_note(messages[-1]):
                guidance = "\n".join(filter(None, [messages[-1][2], redo]))  # regenerate keeps the note in mind
            elif action == "regenerate" and not redo and regen_from is not None and chats.directed_of(regen_from):
                guidance = directed = chats.directed_of(regen_from)  # older chats kept the note on the reply
            if (action == "chat" and (user_message or note_only)) or action == "regenerate":
                # Regenerate re-answers the existing last user message, so only chat adds one
                story_notes = []
                if action == "chat" and systems:  # they went on from the last reply: what it changed now counts
                    story_notes = story.commit(story_state(), systems, messages)
                    story.sync_world(chat_state["story"], systems, chat_state["trackers"])
                    story.snapshot(chat_state["story"], len(messages) + (1 if user_message else 0) + (1 if note else 0))
                if action == "chat" and messages and messages[-1][0] == "assistant":
                    rec = chats.polish_of(messages[-1])
                    if rec and not rec.get("verdict"):  # they went on from a polished reply: a quiet yes
                        messages[-1] = chats.with_polish(messages[-1], messages[-1][2], {**rec, "verdict": "kept"})
                        watch.polish_verdict(request.user, "kept")
                if action == "chat" and user_message:
                    user_message = text_rules("saved", user_message, "user")
                    messages.append(("user", datetime.now().strftime("%H:%M"), user_message, "neutral", 1))
                    watch.on_user_message(request.user, chat_obj, user_message)  # their reply pace
                if note:
                    messages.append(chats.as_note(("user", datetime.now().strftime("%H:%M"), note, "neutral", 1)))
                if action == "chat":  # steering more than playing? Bulba offers director mode
                    watch.note_steering(request.user, chat_obj, "note" if guidance.strip() else "play")

                lore_report = None
                context_dropped = 0

                # --- Prepare history for API ---
                api_messages = []

                # (A card's own system prompt goes through the preset, see prompt_slots and presets.assemble)
                # Add conversation history (story extras the model showed come back as short descriptions, so it
                # remembers them; director's notes framed as directions, the newest one in its own slot)
                api_messages = _history(messages, note_slot=True)

                try:
                    worldbook = None
                    if character.worldbook and character.worldbook.author == request.user:
                        worldbook = character.worldbook

                    if worldbook:
                        worldbook_slug = worldbook.slug
                    else:
                        worldbook_slug = None

                    # if action in ["chat", "regenerate"]:
                    prompt = build_ai_request(
                        request.user,
                        character,
                        chat=chat_obj,
                        worldbook_slug=worldbook_slug,
                        message=(user_message or None) if action == "chat" else None,
                        guidance=guidance,                             # <--- INJECTION 1
                        persistent_guides=chat_state["context_guides"],# <--- INJECTION 2
                        summary=_story_text(request.user, chat_state, len(messages)),
                        story_values=story_state() if systems else None)
                    lore_report = prompt.get("LoreReport")


                    # --- Build the request from the active preset ---
                    preset = presets.normalize(presets.get_active(request.user).data)
                    _, chat_model = ai_client.resolve(request.user, "chat")
                    own_model = chat_model
                    # A refused reply rewritten on the model they picked to step in: just this reply, with
                    # settings made for that model (the chat model stays what it is)
                    stand_in = str(data.get("model") or "")
                    if action != "regenerate" or stand_in not in [o["id"] for o in refusals.options(own_model)]:
                        stand_in = ""
                    if stand_in:
                        chat_model = stand_in
                    names = prompt_names(request.user, character, chat_state["persona"])
                    history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, request.user), api_messages, names)
                    if control.mode_of(preset) == "director":  # each direction says what it means (see control.py)
                        history = control.frame_directions(history, names)
                    built, recalled = recall.assemble_with_recall(
                        presets.assemble, preset, prompt_slots(request.user, character, prompt, chat_state["persona"]),
                        history, names, chat_model, generation="regenerate" if action == "regenerate" else "normal")
                    context_dropped = built["dropped"]
                    chat_state["out_of_view"] = context_dropped  # (the summary panel offers to summarize these)
                    chat_state["last_recall"] = recalled  # shown in "What the AI saw"
                    # Dice and inventory: the model gets tools and the current state (the reply works on a copy)
                    game_state = game.current_state(chat_state, messages)
                    built = game.add_to_request(built, game_mode, game_state, names, extra_kinds,
                                                tables=story.of_type(systems, "table"))
                    if stand_in:
                        built = {**built, "params": {**built["params"], "model": stand_in}}
                    # 🔁 a detail the last replies keep coming back to (a street lamp, the rain): leave it out this time
                    plain = [m for m in messages if isinstance(m, (list, tuple)) and len(m) > 2 and not chats.is_note(m)]
                    stale = fresh_details.repeated(
                        [m[2] for m in plain if m[0] == "assistant"],
                        theirs=[m[2] for m in plain if m[0] == "user"][-fresh_details.WINDOW:],
                        names=[character.name, character.second_name or "", names.get("user", ""), names.get("char", "")])
                    built = {**built, "messages": fresh_details.add_before_note(built["messages"], fresh_details.note(stale))}
                    built = {**built, "messages": favourites.insert_before_chat(built["messages"], favourites.note(character))}
                    texture_note = texture.for_reply(request.user, [m[2] for m in plain[-4:]])  # 🧵 real specifics
                    built = {**built, "messages": fresh_details.add_before_note(built["messages"], texture_note)}
                    from mainapp.bulba import polish as polish_mod  # 🛡 the habits to keep out, before it writes
                    built = {**built, "messages": fresh_details.add_before_note(built["messages"], polish_mod.avoid_line(request.user))}
                    english = translation.english_note(request.user)  # read in another language: written in English
                    if english:
                        built = {**built, "messages": built["messages"] + [english]}
                    if speaker_colors.settings(character)["mode"] == "story":  # near the end, where MiMo listens
                        built = {**built, "messages": speaker_colors.remind(built["messages"])}
                    if thinking.needs_leash(chat_model, samplers.thinking_now(request.user)):  # MiMo: think briefly, then write
                        leashed, leash_params = thinking.leash(built["messages"], built["params"])
                        built = {**built, "messages": leashed, "params": leash_params}
                    game_ops = []
                    # Stream when the page asks for it and the preset allows it
                    streaming = bool(data.get("stream")) and preset["options"].get("streaming", True)
                    if not streaming and use_tools:
                        pieces = list(game.stream_reply(request.user, built["messages"], built["params"], game_state))
                        game_ops = [p for p in pieces if isinstance(p, game.GameEvent)]
                        reply = "".join(p for p in pieces if isinstance(p, str) and not isinstance(
                            p, (ai_client.Reasoning, game.GameEvent)))
                        reasoning = "".join(p for p in pieces if isinstance(p, ai_client.Reasoning)).strip()
                    elif not streaming:
                        message, _ = ai_client.complete_message(request.user, "chat", built["messages"], **built["params"])
                        reply = message.get("content") or ""
                        reasoning = (message.get("reasoning") or message.get("reasoning_content") or "").strip()
                    if not streaming:  # thinking written inside the reply (<thinking>...</thinking>) goes in the box too
                        inline, reply = thinking.split(reply)
                        reasoning = "\n\n".join(t for t in (reasoning, inline) if t)

                except ai_client.AIError as e:
                    # Keep the user's message so they can press Regenerate (and the old reply, if regenerating)
                    if regen_from:
                        messages.append(regen_from)
                    save_messages(messages)
                    return JsonResponse({"error": str(e)}, status=502)
                except Exception as e:
                    log.exception("Error building the prompt")
                    if regen_from:
                        messages.append(regen_from)
                    save_messages(messages)
                    return JsonResponse({"error": f"Something went wrong while building the prompt: {e}"}, status=500)

                def music_due():
                    follow = chat_state["music_follow"]
                    if not follow.get("on"):
                        return False
                    follow["since"] = follow.get("since", MUSIC_EVERY) + 1
                    save_messages(messages)
                    return follow["since"] >= MUSIC_EVERY

                def finish_reply(reply, reasoning="", ops=()):
                    """Emotion, saving, voice and the summary/tracker flags, once the reply is complete."""
                    if refusals.is_refusal(reply):  # not a story reply: never saved; the page offers a stand-in
                        if regen_from is not None:
                            messages.append(regen_from)
                        save_messages(messages)
                        return {"refused": True, "already": bool(stand_in), "text": reply[:300],
                                "model": refusals.name_of(stand_in or own_model),
                                "stand_in": refusals.stand_in_for(request.user, own_model),
                                "options": refusals.options(own_model)}
                    if not str(reply or "").strip() and not [o for o in ops if extras.is_extra(o)]:
                        # Nothing came back (the model thought and stopped, or only called tools): not saved
                        if regen_from is not None:
                            messages.append(regen_from)
                        save_messages(messages)
                        return {"error": "The reply came back empty. Press Regenerate (↻) to try again; if it keeps "
                                         "happening, switch some extras off on the Extras page.", "empty": True}
                    reply = text_rules("saved", reply, "assistant")
                    reasoning = text_rules("saved", reasoning, "reasoning").strip() if reasoning else ""
                    # A tool call the model wrote as text (note_milestone(...)): the extra, not the code
                    first_n = max([o.get("n") or 0 for o in ops if extras.is_extra(o)] + [0]) + 1
                    raw_reply = reply
                    reply, written_calls = game.salvage_calls(reply, first_n=first_n)
                    written_leak = watch.leaked(raw_reply) if reply != raw_reply else ""  # tidied, but Watch notes it
                    ops = list(ops) + [game.GameEvent(o) for o in written_calls]
                    reply = extras.place(reply, ops)  # each story extra's marker, where it goes in the text
                    char_count = 1
                    emotion_char_1 = "neutral"
                    emotion_char_2 = "neutral"
                    emotion_user = "neutral"
                    valid_emotions = ["neutral", *SPRITE_EMOTIONS]
                    pictured_user = _user_pictured(request.user, chat_state["persona"])

                    # --- Classify emotion (optional, can be turned off on the Connections page) ---
                    try:
                        if not ai_client.is_enabled(request.user, "emotion"):
                            raise ai_client.AIError("emotion detection is turned off")
                        valid_emotions = sprite_mod.emotions(character)  # the nine, and this character's own moods

                        # Prompt asks LLM who is speaking (1, 2, or both) and their emotions
                        second = character.second_name or "the other character"
                        classification_system_prompt = (
                            f"You are an analysis tool. The main character is named '{character.name}'"
                            + (f"; the second is '{second}'" if character.is_mult else "") + ".\n"
                            "Analyze the last message and determine who is speaking.\n"
                            "Rules:\n"
                            f"1. If ONLY '{character.name}' is speaking (or acting), set 'speaking' to '1'.\n"
                            f"2. If ONLY '{second}' is speaking (or acting), set 'speaking' to '2'.\n"
                            "3. If BOTH characters are speaking, set 'speaking' to 'both'.\n"
                            "4. Determine the emotion for the speaking character(s) from this list: "
                            f"{json.dumps(valid_emotions)}.\n"
                            + (f"5. Also give 'emotion_user': how {names['user']} (the user's character) most "
                               "likely feels right now, from their last message and this reply.\n" if pictured_user else "")
                            + "Return ONLY a JSON object with this format:\n"
                            '{ "speaking": "1" or "2" or "both", "emotion_1": "...", "emotion_2": "..."'
                            + (', "emotion_user": "..."' if pictured_user else "") + ' }'
                        )
                        last_user = next((m[2] for m in reversed(messages) if m[0] == "user"), "")
                        class_text = ai_client.complete(request.user, "emotion", [
                            {"role": "system", "content": classification_system_prompt},
                            {"role": "user", "content": (f"{names['user']}'s last message:\n{last_user[:1500]}\n\n"
                                                         f"The reply:\n{reply}") if pictured_user else reply}],
                            max_tokens=100, temperature=0.0, response_format={"type": "json_object"})
                        class_data = json.loads(class_text)

                        speaker = str(class_data.get("speaking", "1")).lower()
                        emotion_char_1 = class_data.get("emotion_1", "neutral")
                        emotion_char_2 = class_data.get("emotion_2", "neutral")
                        emotion_user = class_data.get("emotion_user", "neutral")

                        # Logic: Determine layout (char_count)
                        # 1 = Main Only, 2 = Both, 3 = Second Only
                        if character.is_mult:
                            if speaker == "both": char_count = 2
                            elif speaker == "2": char_count = 3
                            else: char_count = 1
                        else:
                            char_count = 1

                    except Exception as e:
                        log.info("Emotion check skipped: %s", e)  # off, or the helper model didn't answer
                        emotion_char_1 = "neutral"

                    # Store emotions as "happy|sad" string ("happy|sad|calm" with their own picture's mood)
                    if emotion_user not in valid_emotions:
                        emotion_user = "neutral"
                    final_emotion_str = f"{emotion_char_1}|{emotion_char_2}" + (f"|{emotion_user}" if pictured_user else "")
                    new_message = chats.with_game(chats.with_reasoning(
                        ("assistant", datetime.now().strftime("%H:%M"), reply, final_emotion_str, char_count), reasoning),
                        [dict(op) for op in ops if op.get("type") != "notice"])
                    if directed:  # shown above the reply: what steered it (a note is a message of its own instead)
                        new_message = chats.with_directed(new_message, directed[:1000])
                    new_message, reply = _cut_echo(messages, new_message)  # their message copied back: cut it
                    messages.append(chats.add_version(regen_from, new_message) if regen_from else new_message)

                    photo_url = _photo(character, "photo", emotion_char_1)
                    photo_second = (_photo(character, "photo_second", emotion_char_2)
                                    if (character.is_mult or char_count >= 2) else None)
                    photo_user = _photo(request.user, "persona_photo", emotion_user) if pictured_user else None
                    html_objects.remember(chat_state["designs"], reply)  # the first look of each kind of object

                    save_messages(messages)
                    watch.on_reply_done(request.user, chat_obj, messages, character.name,  # free checks, pace clock
                                        leak=written_leak)

                    # Automatic summary: tell the page to run one in the background
                    summary_task = ai_client.get_task_setting(request.user, "summary")
                    summarized = chat_state["summary_upto"] or 0
                    using_memory = chat_mode() == "memory"
                    summary_due = (not using_memory and summary_task.mode == summary_task.MODE_AUTO
                                   and not chat_state["summary_paused"] and len(messages) - summarized >= summary_task.interval)
                    # Story memory: the page asks for the update in the background (mainapp/story_memory.py)
                    memory_due = using_memory and story_memory.due(request.user, chat_state["memory"], len(messages))

                    # Trackers: same idea, if any tracker is on for this character
                    tracker_task = ai_client.get_task_setting(request.user, "trackers")
                    tracked = (chat_state["trackers"] or {}).get("upto") or 0
                    trackers_due = ((bool(trackers.ai_trackers(trackers.normalize_config(character.tracker_config, game_mode, "milestones" in extra_kinds,
            "keepsakes" in extra_kinds))) or story.needs_ai(systems))
                                    and tracker_task.mode == tracker_task.MODE_AUTO
                                    and len(messages) - tracked >= tracker_task.interval)

                    return {
                        "reply": reply,
                        "reasoning": reasoning,
                        "game": [game.describe(op) for op in ops if not extras.is_extra(op)],
                        "extras_html": [extras.render(op) for op in ops if extras.is_extra(op)],
                        "game_trackers": game_trackers(),
                        "emotion": final_emotion_str,
                        "photo_url": photo_url,
                        "photo_second": photo_second,
                        "photo_user": photo_user,
                        "char_count": char_count,
                        "voice": bool(get_elevenlabs_key(request.user)),
                        "lore": lore_report,
                        "summary_due": summary_due,
                        "memory_due": memory_due,
                        "trackers_due": trackers_due,
                        "music_due": music_due(),  # the music follows the scene: the page asks for a pick
                        "watch_due": watch.due(request.user, chat_obj, messages),  # Bulba Watch reads, in the background
                        "polish_due": polish.due(request.user, chat_obj, messages),  # the page asks for the polish next
                        "watch": watch.page_state(request.user, chat_obj),
                        "context_dropped": context_dropped,
                        "swipes": chats.version_info(messages),
                        "spending": ai_client.spending(request.user),
                        "directed": chats.directed_of(messages[-1]),
                        "polish": polish.page_payload(chats.polish_of(messages[-1])),  # a cut repeat of their message
                        "story": story_payload(),
                        "story_notes": story_notes,
                    }

                if not streaming:
                    return JsonResponse(finish_reply(reply, reasoning, game_ops))

                def stream_reply():
                    """NDJSON lines: {"type": "delta", "text"} ..., then {"type": "done", ...} or {"type": "error"}."""
                    parts, thoughts, finished = [], [], False
                    inline = thinking.Splitter()  # thinking the model writes inside its reply

                    def keep_partial():
                        # Keep whatever arrived (Stop button, closed tab or a broken stream)
                        text = extras.place(text_rules("saved", "".join(parts), "assistant").strip(), game_ops)
                        if text:
                            partial = chats.with_game(chats.with_reasoning(
                                ("assistant", datetime.now().strftime("%H:%M"), text, "neutral|neutral", 1),
                                "".join(thoughts).strip()), [dict(op) for op in game_ops if op.get("type") != "notice"])
                            messages.append(chats.add_version(regen_from, partial) if regen_from else partial)
                        elif regen_from:
                            messages.append(regen_from)  # nothing new arrived: keep the old reply
                        save_messages(messages)

                    try:
                        try:
                            source = (game.stream_reply(request.user, built["messages"], built["params"], game_state)
                                      if use_tools else
                                      ai_client.stream(request.user, "chat", built["messages"], **built["params"]))
                            for chunk in source:
                                if isinstance(chunk, game.GameEvent):
                                    game_ops.append(chunk)
                                    event = ({"type": "extra", "html": extras.render(chunk)} if extras.is_extra(chunk)
                                             else {"type": "game", "line": game.describe(chunk)})
                                    yield json.dumps(event, ensure_ascii=False) + "\n"
                                    continue
                                if isinstance(chunk, ai_client.ToolCalls):
                                    continue
                                pieces = ([("thinking", chunk)] if isinstance(chunk, ai_client.Reasoning)
                                          else inline.feed(chunk))
                                for kind, piece in pieces:
                                    (thoughts if kind == "thinking" else parts).append(piece)
                                    yield json.dumps({"type": "thinking" if kind == "thinking" else "delta", "text": piece},
                                                     ensure_ascii=False) + "\n"
                            for kind, piece in inline.finish():
                                (thoughts if kind == "thinking" else parts).append(piece)
                                if kind == "text":
                                    yield json.dumps({"type": "delta", "text": piece}, ensure_ascii=False) + "\n"
                        except ai_client.AIError as e:
                            keep_partial()
                            finished = True
                            yield json.dumps({"type": "error", "error": str(e), "kept": bool("".join(parts).strip())}) + "\n"
                            return
                        payload = finish_reply("".join(parts), "".join(thoughts).strip(), game_ops)
                        finished = True
                        yield json.dumps({"type": "done", **payload}, ensure_ascii=False) + "\n"
                    except GeneratorExit:
                        if not finished:
                            keep_partial()
                        raise

                # Written in the background, so leaving the page doesn't stop it (mainapp/live.py); this page and
                # any page opened later follow along
                job = live_jobs.start(live_jobs.key(request.user, chat_obj, "reply"), "reply")
                if job is None:
                    return JsonResponse({"error": "The last reply is still being written. Wait for it, or press Stop."},
                                        status=409)
                live_jobs.run_in_background(job, stream_reply(), unwatched=after_unwatched)
                response = StreamingHttpResponse(job.follow(), content_type="application/x-ndjson")
                response["Cache-Control"] = "no-cache"
                response["X-Accel-Buffering"] = "no"  # don't let proxies hold the stream back
                return response

    # --- GET request ---
    if messages and messages[-1][0] == "assistant":
        # Handle tuple size differences safely (old vs new messages)
        msg_tuple = messages[-1]
        last_emotion_str = msg_tuple[3] if len(msg_tuple) >= 4 else "neutral"
        char_count = msg_tuple[4] if len(msg_tuple) >= 5 else 1
    else:
        last_emotion_str = "neutral|neutral"
        char_count = 2 if character.is_mult else 1

    # 2. Parse "emo1|emo2" string
    if "|" in last_emotion_str:
        parts = last_emotion_str.split("|")
        emo1 = parts[0]
        emo2 = parts[1] if len(parts) > 1 else "neutral"
    else:
        # Backward compatibility
        emo1 = last_emotion_str
        emo2 = "neutral"

    # 3. Helper to get URL with explicit Fallback
    def get_valid_photo_url(char_obj, prefix, emo):
        # A. Try specific emotion
        attr_name = f"{prefix}_{emo}"
        if hasattr(char_obj, attr_name):
            field = getattr(char_obj, attr_name)
            if field and field.name:  # Check if file actually exists
                return field.url

        # B. Fallback to Neutral
        neutral_name = f"{prefix}_neutral"
        if hasattr(char_obj, neutral_name):
            field = getattr(char_obj, neutral_name)
            if field and field.name:
                return field.url

        return None

    # 4. Get the URLs
    photo_url = get_valid_photo_url(character, "photo", emo1)

    # Only load second photo if needed (optimization)
    if character.is_mult or char_count >= 2:
        photo_second = get_valid_photo_url(character, "photo_second", emo2)
    else:
        photo_second = None
    # Their own picture (persona), in the mood of the last exchange
    emo_user = last_emotion_str.split("|")[2] if last_emotion_str.count("|") >= 2 else "neutral"
    photo_user = (_photo(request.user, "persona_photo", emo_user if emo_user in SPRITE_EMOTIONS else "neutral")
                  if _user_pictured(request.user, chat_state["persona"]) else None)

    user_avatar = None
    if hasattr(request.user, 'photo') and request.user.photo:
        user_avatar = request.user.photo.url

    sync_game_trackers(messages)
    reading = translation.reading_language(request.user)  # profile → Story language: replies shown translated
    context = {
        # The template shows the version on screen, and its thoughts (if the model sent any)
        "messages": [(m[0], m[1], _shown(m, reading), m[3], m[4]) + (chats.reasoning_of(m),
                                     [game.describe(op) for op in chats.game_of(m) if not extras.is_extra(op)],
                                     [extras.render(op) for op in translation.shown_extras(m, reading) if extras.is_extra(op)],
                                     (chats.audio_of(m) or {}).get("url", ""),
                                     polish.dumps(chats.polish_of(m)) if chats.polish_of(m) else "",
                                     chats.directed_of(m), chats.condensed_of(m), chats.is_note(m),
                                     # read in another language: the English it was written in, or "to translate"
                                     m[2] if reading and _shown(m, reading) != m[2] else "",
                                     bool(reading and m[0] == "assistant" and not chats.is_note(m)
                                          and not translation.translation_of(m)
                                          and not translation.already_in(m[2], reading)))
                     for m in messages],
        "reading_language": reading or "",
        "reading_language_name": translation.LANGUAGES.get(reading or "", ""),
        "voice_on": bool(get_elevenlabs_key(request.user)),
        "swipes": chats.version_info(messages),
        "spending": ai_client.spending(request.user),
        "appearance": _appearance(request.user, character),
        "speech": (speaker_colors.fill_cast(character) or True) and speaker_colors.settings(character),
        "speech_page": speaker_colors.page_data(),
        "lore_terms": _lore_terms(character),  # 📖 lore terms highlighted in replies
        "favourites": _fav_places(chat_state["favourites"], messages),  # ⭐ (where each one is now)
        "speech_css": speaker_colors.css(),
        "bulba_ideas": extras.ideas_on(request.user),
        "bulba_url": reverse("bulba_chat", kwargs={"chat_id": chat_obj.id}),
        "watch_data": watch.page_state(request.user, chat_obj),
        "persona_hint": _persona_hint(request.user, chat_state["persona"]),
        "preset_hint": _preset_hint(request.user),
        "forms_hint": (not _persona_hint(request.user, chat_state["persona"])) and _forms_hint(request.user, character),
        "theme_weather": theme_weather(character, chat_state.get("current_bg") or ""),
        "skin": chat_skin(character, chat_state.get("skin") or ""),
        "chat_skin_choice": chat_state.get("skin") or "",
        "character_skin": (character.theme or {}).get("skin") if (character.theme or {}).get("skin") in (*CHAT_SKINS, *chat_looks.READY, "custom") else "",
        "chat_skins": CHAT_SKINS,
        **_look_context(request.user, character, chat_state),
        "thinking_options": samplers.thinking_options(ai_client.resolve(request.user, "chat")[1]),
        "thinking_now": samplers.thinking_now(request.user),
        "character_skin_name": CHAT_SKINS.get((character.theme or {}).get("skin") or "", "")
                               or chat_looks.READY_LABELS.get((character.theme or {}).get("skin") or "", "")
                               or ("✨ " + chat_looks.clean((character.theme or {}).get("look"))["name"]
                                   if (character.theme or {}).get("skin") == "custom" and chat_looks.clean((character.theme or {}).get("look")) else ""),
        "mature_on": mature.is_on(presets.normalize(presets.get_active(request.user).data)),
        "director_on": control.mode_of(presets.normalize(presets.get_active(request.user).data)) == "director",
        "display_rules": {
            "rules": [r for r in regex_rules.for_chat(presets.normalize(presets.get_active(request.user).data), character, request.user)
                      if r["enabled"] and r["mode"] == "display"],
            "names": prompt_names(request.user, character, chat_state["persona"])},
        "chat_persona": chat_state["persona"],
        "usual_persona": {"name": getattr(request.user, "persona_name", "") or "",
                          "description": getattr(request.user, "persona_description", "") or ""},
        "character": character,
        "photo_url": photo_url,
        "photo_second": photo_second,
        "photo_user": photo_user,
        "user_name_shown": prompt_names(request.user, character, chat_state["persona"])["user"],
        "char_count": char_count,
        "photo_neutral": photo_url,
        "summary": chat_state["summary"],
        "summary_upto": chat_state["summary_upto"],
        "summary_data": summary_payload(),
        "memory_data": {**story_memory.page_payload(chat_state["memory"], request.user, chat_mode()), "total": len(messages),
                        "left": max(0, len(messages) - story_memory.clean(chat_state["memory"])["upto"])},
        "context_guides": json.dumps(chat_state["context_guides"]),
        "pinned_note_json": json.dumps(pinned_note(chat_state["context_guides"])),
        # The chat's own background and music, else the character's theme
        "current_bg": chat_state["current_bg"] or (character.theme or {}).get("bg", ""),
        "current_music": json.dumps(chat_state["current_music"] or (character.theme or {}).get("music") or {}),
        "music_follow": bool(chat_state["music_follow"].get("on")),
        "user_avatar": user_avatar,
        "trackers_data": {**_tracker_page_data(request.user, character, _synced(chat_state)), "story": story_payload()},
        "stream_replies": presets.normalize(presets.get_active(request.user).data)["options"]["streaming"],
        # Work still going on the server since they left (mainapp/live.py): the page picks it up
        "live_reply": live_jobs.running(live_jobs.key(request.user, chat_obj, "reply")),
        "live_draft": bool(live_jobs.get(live_jobs.key(request.user, chat_obj, "draft"))),
        "chat": chat_obj,
        "chat_list": chats.summary_list(character, chat_obj.id),
    }

    return render(request, "mainapp/chat_page.html", context)


DIALOGUE_DEFAULT = "#e594f2"


def _appearance(user, character=None):
    """How chats look. A character's own dialogue colour (its theme) wins over the user's usual one."""
    settings_obj = ChatSettings.objects.filter(author=user).first()
    look = dict(settings_obj.appearance or {}) if settings_obj else {}
    color = ((character.theme or {}).get("dialogue_color") if character is not None else None) \
        or look.get("dialogue_color") or DIALOGUE_DEFAULT
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):  # "preset" (older): the story-colours way, see speaker_colors
        color = DIALOGUE_DEFAULT
    # "book": replies read as chapters and the user's messages fold away (director mode); "chat": bubbles
    layout = look.get("layout") if look.get("layout") in LAYOUTS else "chat"
    out = {"dialogue_color": color, "dialogue_light": speaker_colors.light_of(color), "layout": layout}
    if character is not None:
        s = speaker_colors.settings(character)
        out.update({"speech_mode": s["mode"], "you_color": s["you"]})
    return out


LAYOUTS = ("chat", "book")


def set_layout(user, layout):
    if layout not in LAYOUTS:
        raise ValueError("Unknown layout.")
    settings_obj, _ = ChatSettings.objects.get_or_create(author=user)
    settings_obj.appearance = {**(settings_obj.appearance or {}), "layout": layout}
    settings_obj.save(update_fields=["appearance"])


def pinned_note(guides):
    """The chat's pinned note. Older chats kept four "World state" fields; they read as one note."""
    guides = guides if isinstance(guides, dict) else {}
    if guides.get("note"):
        return guides["note"]
    labels = (("situation", "Situation"), ("clothes", "Outfits"), ("state", "Physical state"), ("thinking", "Thoughts"))
    return "\n".join(f"{label}: {guides[key]}" for key, label in labels if guides.get(key))


# The fixed frame of each job; the instructions in between are the preset's (presets.JOB_DEFAULTS)
WORD_NOTE_PROMPT = ("You help someone steer their roleplay with an AI. They give you a rough wish for {what}; you "
                    "write it as a director's note the roleplay model will follow. {rules} Reply with the note only.")


CONDENSE_TAIL = " Reply with the condensed message only."


def condense(user, character, message, persona=None):
    """A short version of one message for the AI (one call on the summary model)."""
    names = prompt_names(user, character, persona)
    who = names["user"] if message[0] == "user" else character.name
    text = ai_client.complete(user, "summary", [
        {"role": "system", "content": presets.job_prompt(user, "condense", names) + CONDENSE_TAIL},
        {"role": "user", "content": f"{who}'s message:\n\n{samplers.cut_to(message[2], samplers.job_window(user, 'summary') - 500, keep='start')}"}],
        max_tokens=1500, temperature=0.2)
    text = (text or "").strip()
    if not text:
        raise ai_client.AIError("The model sent back nothing. Try again.")
    return text


MUSIC_EVERY = 3  # replies between two music picks when the music follows the scene


def scene_music(user, messages, current=""):
    """The built-in track that fits the latest reply, or None to keep the current one (a tiny call)."""
    tracks = media_library.built_in("music")
    if not tracks:
        return None
    options = "\n".join(f"{i + 1}. {t['name']}" for i, t in enumerate(tracks))
    recent = "\n\n".join(html_objects.shrink(str(m[2]))[:1200] for m in messages[-2:])
    answer = ai_client.complete(user, "emotion", [
        {"role": "system", "content": "You pick background music for a roleplay scene. Read the latest messages and "
                                      "answer with the number of the track that fits the mood and setting best. "
                                      f"The current track is “{current or 'none'}”: answer 0 to keep it unless the "
                                      "scene's mood or setting clearly changed. Answer with the number only."},
        {"role": "user", "content": f"Tracks:\n{options}\n\nLatest messages:\n{recent}"}],
        max_tokens=100, temperature=0)  # room for a model that thinks first
    m = re.search(r"\d+", answer or "")
    n = int(m.group(0)) if m else 0
    return tracks[n - 1] if 1 <= n <= len(tracks) else None


NOTE_IDEAS_PROMPT = ("You help someone direct their roleplay with an AI. Read the chat. {rules} "
                     "Answer only with JSON: {{\"logical\": \"...\", \"creative\": \"...\"}}")


def bulba_quick(user, messages, max_tokens=1500, **params):
    """A small call on Bulba's model. That model thinks before it answers, and the thinking counts toward
    max_tokens: a tight limit can leave the answer empty. So the limit has room, and an empty answer gets one
    retry with more room and without response_format (some providers return nothing in JSON mode)."""
    text = ai_client.complete(user, "bulba", messages, max_tokens=max_tokens, **params)
    if (text or "").strip():
        return text
    log.warning("Bulba's model sent an empty answer (max_tokens=%s); retrying once", max_tokens)
    params.pop("response_format", None)
    return ai_client.complete(user, "bulba", messages, max_tokens=max_tokens * 2, **params) or ""


def _note_fields(text):
    """The two notes from the answer: JSON, or a cut-off JSON, or plain "logical: ... creative: ..." lines."""
    from .bulba import watch as watch_mod
    data = watch_mod._parse(text)
    ideas = {k: str(data.get(k) or "").strip().strip('"')[:600] for k in ("logical", "creative")}
    for key in ("logical", "creative"):
        if not ideas[key]:
            m = re.search(rf'"?{key}"?\s*[:=]\s*"?(.+?)(?:"\s*[,}}]|\n|$)', text or "", re.I | re.S)
            ideas[key] = m.group(1).strip().strip('"')[:600] if m else ""
    return ideas


def note_ideas(user, character, messages, summary="", persona=None):
    """Two director's notes written from scratch (one small call on the Bulba model)."""
    names = prompt_names(user, character, persona)
    recent = [m for m in messages if m[0] in ("user", "assistant")][-6:]
    if not recent:
        raise ai_client.AIError("Start the story first: there's nothing to direct yet.")
    transcript = "\n\n".join(f"{names['user'] if m[0] == 'user' else character.name}: {html_objects.shrink(m[2])[:1500]}" for m in recent)
    text = bulba_quick(user, [
        {"role": "system", "content": NOTE_IDEAS_PROMPT.format(rules=presets.job_prompt(user, "note_ideas", names))
                                      + "\n\n" + writing_quality.helper_taste(user)},
        {"role": "user", "content": (f"The story so far: {summary[:2000]}\n\n" if summary else "")
                                    + f"The latest messages (latest last):\n\n{transcript}"}],
        temperature=0.8, response_format={"type": "json_object"})
    ideas = _note_fields(text)
    if not any(ideas.values()):
        log.warning("Be creative: no notes in the answer: %r", (text or "")[:300])
        raise ai_client.AIError("Bulba couldn't come up with anything this time. Try again.")
    return ideas


IDEAS_PROMPT = {"player": "You help someone who is stuck in a roleplay with an AI. Read the chat.",
                "director": "You help someone who directs a roleplay with an AI from outside the story. Read the chat."}
IDEAS_STYLE = ("Plain words, no 'ensure', 'immersive', 'vivid', 'delve', no capitals for emphasis, no exclamation "
               "marks. Answer with JSON only: {\"ideas\": [\"...\", \"...\", \"...\"]}")


def story_voice(user):
    """The point of view, tense and speech format chosen for the story (the preset's Basics block), keyed like
    the basics form: {"pov": "third", "tense": "past", "format": "asterisks"}."""
    from mainapp.bulba.agent import BASICS
    block = next((b for b in presets.normalize(presets.get_active(user).data)["blocks"]
                  if b.get("name") == "Basics" and b.get("kind") == "prompt" and b.get("enabled")), None)
    text = (block or {}).get("content") or ""
    return {key: value for key in ("pov", "tense", "format") for value, line in (BASICS[key][1] or {}).items()
            if line and line in text}


IDEAS_VOICE = {"second": "Write them in second person for {{user}} (\"You ask about the vials\").",
               "third": "Write them in third person, with {{user}}'s name (\"{{user}} asks about the vials\").",
               "first": "{{char}} narrates in first person, so write {{user}}'s ideas in third person, with their "
                        "name (\"{{user}} asks about the vials\")."}


def ideas_voice(user, messages, names):
    """How the player ideas are written: like their own messages when they've written some, else in the story's
    point of view; never "I" for them unless they write that way themselves."""
    voice = story_voice(user)
    if any(m[0] == "user" and not chats.is_note(m) for m in messages):
        line = ("Write them the way {{user}}'s recent messages are written (same person, tense and style); if "
                "those use \"I\", so can you, otherwise never \"I\" for {{user}}.")
    else:
        line = (IDEAS_VOICE.get(voice.get("pov"), IDEAS_VOICE["third"]) + " Never \"I\" for {{user}}.")
    if voice.get("tense") == "present":
        line += " Present tense."
    elif voice.get("tense") == "past":
        line += " Past tense."
    if voice.get("format") == "asterisks":
        line += " Actions in *asterisks*, speech in double quotes."
    return line.replace("{{user}}", names["user"]).replace("{{char}}", names["char"])


def bulba_ideas(user, character, messages, mode, persona=None, summary=""):
    """Three ideas for what to write next ("player") or what could happen next ("director"), on Bulba's model."""
    names = prompt_names(user, character, persona)
    recent = [m for m in messages if m[0] in ("user", "assistant")][-8:]
    transcript = "\n\n".join(f"{names['user'] if m[0] == 'user' else character.name}: {html_objects.shrink(m[2])[:1500]}" for m in recent)
    system = (IDEAS_PROMPT[mode] + " " + presets.job_prompt(user, "ideas_" + mode, names)
              + (" " + ideas_voice(user, messages, names) if mode == "player" else "") + "\n\n"
              + writing_quality.helper_taste(user) + "\n\n" + IDEAS_STYLE)
    about = f"{character.name}: {(character.description or '')[:1500]}"
    story = f"The story so far (summary): {summary[:2000]}\n\n" if summary else ""
    text = bulba_quick(user, [
        {"role": "system", "content": system},
        {"role": "user", "content": f"{about}\n\n{story}The chat (latest last):\n\n{transcript}"}],
        max_tokens=2000, temperature=0.8)
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        ideas = json.loads(match.group(0))["ideas"] if match else []
    except (ValueError, KeyError, TypeError):
        ideas = []
    ideas = [str(i).strip()[:400] for i in ideas if str(i).strip()][:3]
    if not ideas:
        raise ai_client.AIError("Bulba came up empty. Try again.")
    return ideas


def word_note(user, character, messages, wish, rewrite=False, persona=None):
    """Bulba's quick help with a director's note (one small call on the Bulba model)."""
    wish = wish.strip()[:1000]
    if not wish:
        raise ai_client.AIError("Write what you'd like first, in your own words.")
    names = prompt_names(user, character, persona)
    recent = [m for m in messages if m[0] in ("user", "assistant")][-6:]
    transcript = "\n\n".join(f"{names['user'] if m[0] == 'user' else character.name}: {html_objects.shrink(m[2])[:1500]}" for m in recent)
    what = "a new version of the last reply" if rewrite else "the next reply"
    system = (WORD_NOTE_PROMPT.format(what=what, rules=presets.job_prompt(user, "director_note", names))
              + "\n\n" + writing_quality.helper_taste(user))
    text = bulba_quick(user, [
        {"role": "system", "content": system},
        {"role": "user", "content": f"The chat so far (latest last):\n\n{transcript}\n\nTheir wish: {wish}"}],
        temperature=0.4)
    text = (text or "").strip().strip('"')
    if not text:
        raise ai_client.AIError("Bulba couldn't word it this time. Try again.")
    return text


WEATHERS = ("rain", "snow", "fog", "storm", "clear")
# Chat styles: bubbles, buttons and one light effect (static mainapp/css/chat_skins.css), per character
CHAT_SKINS = {"parchment": "📜 Parchment", "neon": "🌆 Neon", "lab": "🧪 Lab", "romance": "🌸 Romance"}


def chat_skin(character, chat_choice=""):
    """The style a chat shows: its own pick ("none" = plain), else the character's, else plain (""). A look from
    their shelf is "shelf:<id>"."""
    has_look = bool(chat_looks.clean((character.theme or {}).get("look")))
    if chat_choice == "none":
        return ""
    if str(chat_choice).startswith("shelf:") and character.author and chat_looks.from_shelf(character.author, chat_choice[6:]):
        return chat_choice
    if chat_choice in CHAT_SKINS or chat_choice in chat_looks.READY or (chat_choice == "custom" and has_look):
        return chat_choice
    skin = (character.theme or {}).get("skin")
    return skin if skin in CHAT_SKINS or skin in chat_looks.READY or (skin == "custom" and has_look) else ""


def _look_context(user, character, chat_state):
    """The chat page's custom look (mainapp/chat_looks.py), when one is on: the character's own ("custom") or a ready
    one (Purpl...). Its styles, fonts and moving parts; `own_look` for the pen menu's chip and Adjust box."""
    own = chat_looks.clean((character.theme or {}).get("look"))
    if own and not any(chat_looks._same(i["look"], own) for i in chat_looks.shelf(user)):
        chat_looks.keep(user, own)  # a look made before the shelf existed goes on it
    skin = chat_skin(character, chat_state.get("skin") or "")
    if skin in chat_looks.READY:
        look = chat_looks.clean(chat_looks.READY[skin])
    elif skin.startswith("shelf:"):
        look = chat_looks.from_shelf(user, skin[6:])
    else:
        look = own if skin == "custom" else None
    out = {"own_look": own, "ready_looks": chat_looks.READY_LABELS, "look": look, "adjustable": skin == "custom",
           "skin_class": "custom" if look else skin,
           "shelf": [i for i in chat_looks.shelf(user) if not (own and chat_looks._same(i["look"], own))]}
    if not look:
        return out
    names = prompt_names(user, character, chat_state.get("persona"))
    pictures = media_library.built_in("backgrounds")
    if (character.theme or {}).get("bg"):
        pictures = [{"name": f"{character.name}'s own background", "url": character.theme["bg"]}] + pictures
    return {**out, "look_css": chat_looks.css(look, character.name, names["user"]),
            "look_fonts": chat_looks.fonts_url(look), "look_data": chat_looks.page_data(look),
            "look_pictures": pictures, "look_backgrounds": chat_looks.BACKGROUNDS}


def theme_weather(character, background=""):
    """The weather a chat opens with until the World tracker says otherwise: the theme's, else a guess from the
    background's name ("Rainy" → rain). "" when there's nothing to go on."""
    theme = character.theme or {}
    if theme.get("weather") in WEATHERS:
        return "" if theme["weather"] == "clear" else theme["weather"]
    name = (str(background or theme.get("bg") or "")).lower()
    for word, weather in (("storm", "storm"), ("thunder", "storm"), ("rain", "rain"), ("snow", "snow"),
                          ("blizzard", "snow"), ("fog", "fog"), ("mist", "fog")):
        if word in name:
            return weather
    return ""


def _preset_hint(user):
    """The one-time preset note for the chat page (preset_upgrade.py); never breaks the page."""
    from mainapp import preset_upgrade
    try:
        return preset_upgrade.pending(user)
    except Exception:
        logging.getLogger(__name__).exception("Preset upgrade check failed")
        return None


@login_required
def preset_upgrade_action(request):
    """The chat page's preset note: switch, keep mine, undo, rebuild for the new model, not now."""
    from mainapp import preset_upgrade
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    action, user = data.get("action"), request.user
    if action == "switch":
        new = preset_upgrade.switch(user, mark="chosen")
        return JsonResponse({"ok": bool(new), "text": f"Switched to “{new.name}”. Your old preset is still in the list."
                             if new else "Couldn't switch: check your connection first."})
    if action == "undo":
        return JsonResponse({"ok": preset_upgrade.undo(user), "text": "Back to your previous preset."})
    if action == "rebuild":
        obj = preset_upgrade.rebuild(user)
        if not obj:
            return JsonResponse({"ok": False, "text": "Couldn't rebuild: check your connection first."})
        return JsonResponse({"ok": True, "text": f"Rebuilt for your current model: “{obj.name}”."
                             + preset_upgrade.carried_text(getattr(obj, "carried", {}))})
    if action == "undo_rebuild":
        return JsonResponse({"ok": preset_upgrade.undo_rebuild(user), "text": "Back as it was."})
    if action in ("keep", "later"):
        preset_upgrade.decline(user, str(data.get("kind") or ""), str(data.get("pair") or ""))
        return JsonResponse({"ok": True})
    return JsonResponse({"error": "Unknown action."}, status=400)


def _persona_hint(user, chat_persona):
    """True once: they have no persona (none on the account, none in this chat) and haven't been asked yet."""
    if getattr(user, "persona_name", "") or (chat_persona or {}).get("name"):
        return False
    obj = ChatSettings.objects.filter(author=user).first()
    return not (obj and (obj.appearance or {}).get("persona_hint_seen"))


def _forms_hint(user, character):
    """The worldbook URL, once per account: the character's worldbook is in a language that changes words
    (Ukrainian, Polish...), so "🥔 Add word forms" can catch the forms that change inside a word."""
    obj = ChatSettings.objects.filter(author=user).first()
    if obj and (obj.appearance or {}).get("forms_hint_seen"):
        return ""
    wb = character.worldbook
    if wb is None or wb.author_id != user.id:
        return ""
    from mainapp import lorebook
    try:
        return reverse("worldbook_detail", args=[wb.slug]) if lorebook.inflected(load_worldbook(wb)) else ""
    except Exception:  # an unreadable book: nothing to suggest
        return ""


def _shown(message, reading):
    """The text a message shows: its translation in the language they read, else what was written."""
    return translation.display_text(message, reading) if reading else message[2]


def _only_new(last_text, chunk):
    """What a Continue really added. A model that wrote the reply over (it starts like the reply did) gives None;
    one that repeated the last bit before going on loses the repeat."""
    if not chunk:
        return ""
    head = last_text.strip()[:60]
    if len(head) >= 20 and chunk.strip().startswith(head):
        return None
    last, start = last_text.rstrip(), chunk.lstrip()
    for k in range(min(len(last), len(start), 400), 29, -1):  # the longest bit of the ending it repeated first
        if start.startswith(last[-k:]):
            return start[k:]
    return chunk


def _glossary(user, character, chat_state):
    """Names the translation keeps as they are."""
    names = prompt_names(user, character, (chat_state or {}).get("persona"))
    return {n: n for n in (names["char"], names["user"]) if n}


def prompt_names(user, character, chat_persona=None):
    """{{char}} and {{user}}: this chat's persona name, else the usual persona name, else the account name."""
    return {"char": character.name or "Character",
            # Who they are in the story: the chat's persona, else their usual one, else their name; the login only
            # when there's none of those (the user's call)
            "user": (chat_persona or {}).get("name") or getattr(user, "persona_name", None) or user.name
                    or user.username or "Stranger"}


def prompt_slots(user, character, prompt, chat_persona=None):
    """Text for the preset's slots (markers), from the character, persona and build_ai_request."""
    extra = prompt.get("SystemPrompts", {})
    return {
        "char_description": character.description or "",
        # Creator's notes are for people reading the card, never sent to the model
        "char_personality": character.personality or "",
        "examples": cards.format_examples(character.example_dialogue),
        "card_system_prompt": character.system_prompt or "",
        "card_post_history": character.post_history_instructions or "",
        "scenario": character.scenario or "",
        "persona": ((chat_persona or {}).get("description") if (chat_persona or {}).get("name")
                    else getattr(user, "persona_description", None)) or "",
        "lore": extra.get("WorldInfo", ""),
        "summary": extra.get("StorySummary", ""),
        "trackers": extra.get("StoryState", ""),
        "world_context": extra.get("WorldContext", ""),
        "director_note": extra.get("DirectorNote", ""),
        "char_depth_prompt": cards.depth_prompt(character),
    }


def build_chat_request(user, chat_obj, preset=None, character=None, drop_last_reply=True, generation="normal",
                       tail=(), model=None):
    """
    The request a chat would send for its next AI reply (or, with drop_last_reply, to re-answer the last user
    message), optionally with another preset or an edited character. Used by Bulba to rewrite a reply with a
    proposed change. `tail`: extra turns after the chat (an impersonation request). Returns presets.assemble()'s result.
    """
    character = character or chat_obj.character
    data = chats.read(chat_obj)
    messages = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    guidance = ""
    if drop_last_reply and messages and messages[-1][0] == "assistant":
        guidance = chats.directed_of(messages[-1])
        messages = messages[:-1]
    if drop_last_reply and not tail and messages and chats.is_note(messages[-1]):
        guidance = messages[-1][2]  # same newest-note slot as Regenerate

    summary = story_memory.story_text(user, data, chats.summary_text(chats.summary_parts(data, len(messages))), len(messages))
    worldbook_slug = character.worldbook.slug if character.worldbook and character.worldbook.author == user else None
    prompt = build_ai_request(user, character, chat=chat_obj, worldbook_slug=worldbook_slug, message=None,
                              guidance=guidance, persistent_guides=data.get("context_guides") or {}, summary=summary)
    preset = presets.normalize(preset or presets.get_active(user).data)
    persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    names = prompt_names(user, character, persona)
    history = _history(messages, note_slot=bool(guidance) and not tail)
    history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, user), history, names)
    if control.mode_of(preset) == "director" and not tail:
        history = control.frame_directions(history, names)
    history += list(tail)
    if not model:  # (another model only when comparing models: the request is shaped for that one)
        _, model = ai_client.resolve(user, "chat")
    if tail:  # an extra request at the end (impersonation): no recall, its words aren't the scene's
        return presets.assemble(preset, prompt_slots(user, character, prompt, persona), history, names, model,
                                generation=generation)
    built = recall.assemble_with_recall(presets.assemble, preset, prompt_slots(user, character, prompt, persona),
                                      history, names, model, generation=generation)[0]
    english = translation.english_note(user)
    if english:
        built = {**built, "messages": built["messages"] + [english]}
    return built


def _tracker_page_data(user, character, raw_state):
    """Everything the chat page's tracker HUD and panel need."""
    kinds = extras.kinds_for(user)
    config = trackers.normalize_config(character.tracker_config, game.mode_for(user, character),
                                       "milestones" in kinds, "keepsakes" in kinds)
    task = ai_client.get_task_setting(user, "trackers")
    return {
        "panels": trackers.PANELS,
        "specs": [trackers.tracker_spec(t["id"], config) for t in trackers.TRACKERS],
        "config": config,
        "state": trackers.normalize_state(raw_state, config),
        "schedule": {"mode": task.mode, "interval": task.interval},
        "setup_url": reverse("tracker_setup", args=[character.slug]),
        "character_name": character.name,
    }


def _preset_summary(obj):
    data = presets.normalize(obj.data)
    return {"id": obj.id, "name": obj.name, "active": obj.is_active,
            "blocks": sum(1 for b in data["blocks"] if b["kind"] != "header"),
            "enabled": sum(1 for b in data["blocks"] if b["enabled"] and b["kind"] != "header"),
            "updated": obj.time_update.strftime("%Y-%m-%d %H:%M")}


def _preset_preview(user, preset, character):
    """What the active chat with `character` would send right now with `preset`."""
    chat = chats.current(character)
    chat_file = chats.read(chat)
    worldbook_slug = character.worldbook.slug if character.worldbook and character.worldbook.author == user else None
    prompt = build_ai_request(user, character, chat=chat, worldbook_slug=worldbook_slug,
                              persistent_guides=chat_file.get("context_guides") or {},
                              summary=chat_file.get("summary") or "")
    history = [{"role": "assistant" if m[0] == "assistant" else "user", "content": m[2]}
               for m in chat_file.get("messages", []) if isinstance(m, (list, tuple)) and len(m) > 2]
    history.append({"role": "user", "content": "(your next message)"})
    try:
        _, model = ai_client.resolve(user, "chat")
    except ai_client.NoConnection:
        model = ""
    names = prompt_names(user, character)
    history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, user), history, names)
    built = presets.assemble(preset, prompt_slots(user, character, prompt), history, names, model)
    return {"messages": built["preview"], "params": built["params"], "notes": built["notes"],
            "variables": built["variables"], "model": model}


@login_required
def preset_list(request):
    from .models import Preset
    presets.get_active(request.user)  # makes sure the default exists

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        action = data.get("action")
        obj = Preset.objects.filter(user=request.user, id=data.get("id")).first()
        if action == "save_my_rules":  # the user's own text rules, run with every preset (no preset needed)
            return JsonResponse({"rules": regex_rules.save_user_rules(request.user, data.get("rules"))})

        if action == "import":
            try:
                preset, suggested = presets.from_any(data.get("data"))
            except (ValueError, TypeError, AttributeError) as e:
                return JsonResponse({"error": str(e)}, status=400)
            obj = Preset.objects.create(user=request.user, data=preset,
                                        name=presets.unique_name(request.user, data.get("name") or suggested))
        elif action == "new_default":
            fresh, name = presets.first_preset(request.user)
            obj = Preset.objects.create(user=request.user, data=fresh, name=presets.unique_name(request.user, name))
        elif action == "use_starter":
            try:
                obj = starters.apply(request.user, data.get("starter"), mode=data.get("control"), extensions=data.get("extensions") or [])
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
        elif obj is None:
            return JsonResponse({"error": "Preset not found."}, status=404)
        elif action == "activate":
            presets.activate(obj)
        elif action == "rename":
            obj.name = presets.unique_name(request.user, data.get("name"), exclude_id=obj.id)
            obj.save(update_fields=["name"])
        elif action == "duplicate":
            obj = Preset.objects.create(user=request.user, data=obj.data,
                                        name=presets.unique_name(request.user, f"{obj.name} copy"))
        elif action == "delete":
            if Preset.objects.filter(user=request.user).count() <= 1:
                return JsonResponse({"error": "You need at least one preset."}, status=400)
            was_active = obj.is_active
            obj.delete()
            if was_active:
                presets.activate(Preset.objects.filter(user=request.user).first())
            obj = presets.get_active(request.user)
        elif action == "save":  # block on/off switches and options
            preset = presets.normalize(obj.data)
            enabled = data.get("enabled") if isinstance(data.get("enabled"), dict) else {}
            for block in preset["blocks"]:
                if block["id"] in enabled:
                    block["enabled"] = bool(enabled[block["id"]])
            if data.get("post_processing") in presets.POST_PROCESSING:
                preset["options"]["post_processing"] = data["post_processing"]
            obj.data = preset
            obj.save(update_fields=["data", "time_update"])
        elif action == "save_full":  # the editor: blocks, utility prompts, options
            current = presets.normalize(obj.data)
            if not isinstance(data.get("blocks"), list) or len(data["blocks"]) > 2000:
                return JsonResponse({"error": "Invalid block list."}, status=400)
            edited = presets.normalize({**current, "blocks": data["blocks"],
                                        "utility": data.get("utility", current["utility"]),
                                        "options": data.get("options", current["options"]),
                                        "regex": data.get("regex", current["regex"])})
            # Samplers are edited on their own page; SillyTavern extras are never edited here
            edited["samplers"], edited["extras"] = current["samplers"], current["extras"]
            obj.data = edited
            obj.save(update_fields=["data", "time_update"])
        elif action == "test_rule":  # one text rule over sample text, without saving anything
            rule = regex_rules.normalize_rule(data.get("rule"))
            if rule is None:
                return JsonResponse({"error": "That isn't a text rule."}, status=400)
            problem = regex_rules.check(rule)
            names = {"char": "Character", "user": cards.user_name(request.user)}
            result = "" if problem else regex_rules.run_rule(rule, str(data.get("text") or ""), names)
            return JsonResponse({"result": result, "problem": problem})
        elif action == "import_rules":
            rules = regex_rules.from_import(data.get("data"))
            if not rules:
                return JsonResponse({"error": "No regex scripts found in that file."}, status=400)
            return JsonResponse({"rules": rules})
        elif action == "preview":
            character = Character.objects.filter(author=request.user, slug=data.get("character")).first()
            if character is None:
                return JsonResponse({"error": "Pick one of your characters to preview with."}, status=400)
            return JsonResponse(_preset_preview(request.user, presets.normalize(obj.data), character))
        else:
            return JsonResponse({"error": "Unknown action."}, status=400)

        return JsonResponse({"status": "ok", "selected": obj.id,
                             "presets": [_preset_summary(p) for p in Preset.objects.filter(user=request.user)],
                             "preset": {"id": obj.id, "name": obj.name, **presets.normalize(obj.data)}})

    selected = Preset.objects.filter(user=request.user, id=request.GET.get("id")).first() \
        or presets.get_active(request.user)
    return render(request, "mainapp/presets.html", {"preset_page": {
        "presets": [_preset_summary(p) for p in Preset.objects.filter(user=request.user)],
        "preset": {"id": selected.id, "name": selected.name, **presets.normalize(selected.data)},
        "markers": presets.MARKERS,
        "utility_labels": presets.UTILITY_LABELS,
        "job_defaults": presets.JOB_DEFAULTS,
        "macro_help": presets.MACRO_HELP,
        "post_processing": presets.POST_PROCESSING,
        "characters": [{"slug": c.slug, "name": c.name} for c in Character.objects.filter(author=request.user)],
        "starters": starters.for_page(_chat_model(request.user)),
        "experience_control": control.mode_of(presets.normalize(selected.data)),
        "starter_of": (presets.normalize(selected.data)["extras"].get("starter") or {}).get("id"),
        "my_rules": regex_rules.user_rules(request.user),
    }})


def _chat_model(user):
    try:
        return ai_client.resolve(user, "chat")[1]
    except ai_client.NoConnection:
        return ""


@login_required
def preset_export(request, preset_id):
    from .models import Preset
    obj = get_object_or_404(Preset, user=request.user, id=preset_id)
    preset = presets.normalize(obj.data)
    if request.GET.get("format") == "sillytavern":
        payload, suffix = presets.to_sillytavern(preset), "_sillytavern"
    else:
        payload, suffix = presets.to_native(preset, obj.name), ""
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{slugify(obj.name) or "preset"}{suffix}.json"'
    return response


@login_required
def sampler_settings(request):
    """Samplers of the active preset: each one can be switched off (= model default)."""
    preset_obj = presets.get_active(request.user)
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        preset_obj.data = {**preset_obj.data, "samplers": samplers.normalize(data)}
        preset_obj.save(update_fields=["data", "time_update"])
        return JsonResponse({"status": "ok", "samplers": preset_obj.data["samplers"]})

    try:
        _, model = ai_client.resolve(request.user, "chat")
    except ai_client.NoConnection:
        model = ""
    return render(request, "mainapp/samplers.html", {
        "preset_name": preset_obj.name,
        "sampler_data": {
            "specs": samplers.SAMPLERS,
            "values": samplers.normalize(preset_obj.data.get("samplers")),
            "model": model,
            "profile": model_profiles.public(model_profiles.for_model(model)),
            "status": model_profiles.sampler_status(model, samplers.normalize(preset_obj.data.get("samplers"))),
            "known_models": model_profiles.known_names(),
        },
    })


@login_required
def tracker_setup(request, slug):
    """Per-character tracker setup: which trackers are on, custom fields, layout."""
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        if not isinstance(data, dict):
            return JsonResponse({"error": "Invalid request."}, status=400)
        if "systems" not in data:  # an older page without the story systems section: keep them
            data["systems"] = (character.tracker_config or {}).get("systems") or []
        config = trackers.normalize_config(data)
        if story.of_type(config["systems"], "event") and not story.of_type(config["systems"], "clock"):
            return JsonResponse({"error": "Events need a story clock: add one, or remove the events."}, status=400)
        dropped = len([s for s in data.get("systems") or [] if s]) - len(config["systems"])
        if dropped > 0:
            return JsonResponse({"error": "An event needs what happens, and a random table needs at least one "
                                          "result (and there can be 12 systems at most). Fill them in or remove them."}, status=400)
        character.tracker_config = config
        character.save(update_fields=["tracker_config"])
        return JsonResponse({"status": "ok", "config": character.tracker_config})

    ask = (f"Design a custom tracker for {character.name}'s story with me: ask what it should follow, then propose "
           "it with its look, colour, what raises and lowers it, and levels.")
    return render(request, "mainapp/tracker_setup.html", {
        "character": character,
        "bulba_custom_url": reverse("chat", kwargs={"slug": character.slug}) + "?" + urlencode({"bulba_ask": ask}),
        "setup_data": {
            "panels": trackers.PANELS,
            "trackers": trackers.TRACKERS,
            "config": trackers.normalize_config(character.tracker_config),
            "field_types": trackers.FIELD_TYPES,
            "game_modes": game.MODE_LABELS,
            "game_default": game.MODE_LABELS[game.user_default(request.user)],
            "game_default_mode": game.user_default(request.user),
            "milestones_by_app": "milestones" in extras.kinds_for(request.user),
            "scrapbook_by_app": "keepsakes" in extras.kinds_for(request.user),
            "character_name": character.name,
        },
    })


@login_required
def worldbook_create(request):
    if request.method != "POST":
        return render(request, "mainapp/worldbook_create.html")

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid JSON"}, status=400)

    # Optional import: our own export, a SillyTavern lorebook or a character card
    imported = data.get("import")
    try:
        book = normalize_book(imported) if imported else normalize_book({})
    except (ValueError, TypeError) as e:
        return JsonResponse({"status": "error", "message": f"Could not read the imported file: {e}"}, status=400)

    title = (data.get("title") or book["title"] or "Untitled").strip()
    book["title"] = title
    book["description"] = (data.get("description") or book["description"] or "").strip()

    base_slug = slugify(title) or "worldbook"
    slug, n = base_slug, 2
    while Worldbook.objects.filter(slug=slug).exists():
        slug, n = f"{base_slug}-{n}", n + 1

    wb = Worldbook(title=title, slug=slug, description=book["description"], author=request.user)
    save_worldbook(wb, book)
    return JsonResponse({"status": "ok", "url": wb.get_absolute_url(), "count": len(book["entries"])})


@login_required
def worldbook_detail(request, slug):
    wb = get_object_or_404(Worldbook, slug=slug, author=request.user)

    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        book = save_worldbook(wb, data)
        return JsonResponse({"status": "ok", "count": len(book["entries"]), "book": book})

    return render(request, "mainapp/worldbook_detail.html", {
        "worldbook": wb,
        "worldbook_json": load_worldbook(wb),
        "defaults": {"settings": LORE_DEFAULT_SETTINGS, "entry": LORE_DEFAULT_ENTRY},
    })


WORD_FORMS_PROMPT = (
    "You help with a roleplay lorebook. Each entry has keywords; an entry is used when one of them appears in the "
    "chat. The app already catches a word with a different ending (дракон → дракона, драконів; Фортеця → Фортеці), "
    "but not a word that changes inside (Київ → Києва, Києві; Lwów → Lwowie; кінь → коня). For each entry, list the "
    "forms of its keywords that a story would use and that change inside the word: grammatical cases, plural, "
    "the common adjective (Київ → київський). Same language as the keyword. Skip keywords in English or other "
    "languages that barely change, regex keywords (/.../), and forms that only add or swap an ending. Don't invent "
    "new names or synonyms. Answer with JSON only: {\"forms\": {\"<entry id>\": [\"form\", ...]}}; leave out "
    "entries with nothing to add.")


def word_forms(user, book):
    """{uid: [new keys]}: forms the keys take inside the word, without the ones the flexible endings already catch."""
    from mainapp.lorebook import _key_pattern
    entries = [e for e in book["entries"] if e["keys"] and not e["constant"]][:120]
    asked = {str(e["uid"]): [k for k in e["keys"] if not k.startswith("/")] for e in entries}
    asked = {uid: keys for uid, keys in asked.items() if keys}
    if not asked:
        return {}
    text = ai_client.complete(user, "bulba", [{"role": "system", "content": WORD_FORMS_PROMPT},
                                              {"role": "user", "content": json.dumps(asked, ensure_ascii=False)}],
                              timeout=120, temperature=0.2)
    match = re.search(r"\{.*\}", text or "", re.S)
    try:
        forms = json.loads(match.group(0)).get("forms", {}) if match else {}
    except (ValueError, AttributeError):
        raise ai_client.AIError("Bulba's answer wasn't readable. Try again.")
    out = {}
    for e in entries:
        keys = asked.get(str(e["uid"]), [])
        new = []
        for form in forms.get(str(e["uid"])) or []:
            form = str(form).strip()[:60]
            if not form or form.startswith("/") or form.lower() in [k.lower() for k in e["keys"] + new]:
                continue
            caught = any(_key_pattern(k, False, True, True).fullmatch(form.replace("’", "'")) for k in keys)
            if not caught:
                new.append(form)
        if new:
            out[e["uid"]] = new[:10]
    return out


# 🥔 Word forms and Expand run in the background when the page asks. While one runs, the cache knows; a finished
# one is saved with their settings (it survives restarts) and waits until they add it or dismiss it.
BOOK_JOB_SECONDS = 3600  # how long a running job may take before it counts as lost


def _book_job_key(user, slug, kind):
    return f"bookjob:{user.id}:{slug}:{kind}"


def _stored_jobs(user):
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).first()
    return dict((obj.appearance or {}).get("book_jobs") or {}) if obj else {}


def _store_job(user, name, job):
    from mainapp.models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    jobs = dict((obj.appearance or {}).get("book_jobs") or {})
    if job is None:
        jobs.pop(name, None)
    else:
        jobs[name] = job
    obj.appearance = {**(obj.appearance or {}), "book_jobs": jobs}
    obj.save(update_fields=["appearance"])


def _book_job(request, slug, kind, data, run):
    """GET: the job's state (?clear=1 after they added or dismissed it). POST with background: start `run` in a
    thread (unless one is running). Else None: the caller runs it now."""
    import threading
    import time as time_mod
    from django.core.cache import cache
    from django.db import connection
    user, key, name = request.user, _book_job_key(request.user, slug, kind), f"{slug}:{kind}"
    if request.method == "GET":
        if request.GET.get("clear"):
            _store_job(user, name, None)
            return JsonResponse({"status": "none"})
        running = cache.get(key)
        if running:
            return JsonResponse({"status": "running", "seconds": int(time_mod.time() - running["started"])})
        return JsonResponse(_stored_jobs(user).get(name) or {"status": "none"})
    if not data.get("background"):
        return None
    if cache.get(key):
        return JsonResponse({"status": "running"})
    cache.set(key, {"started": time_mod.time()}, BOOK_JOB_SECONDS)
    _store_job(user, name, None)  # a new run replaces what was waiting

    def work():
        try:
            job = {"status": "done", "result": run()}
        except (ai_client.AIError, ValueError) as e:
            job = {"status": "error", "error": str(e)}
        except Exception as e:  # never leave it "running" forever
            log.exception("Worldbook job failed")
            job = {"status": "error", "error": f"Something went wrong ({e.__class__.__name__})."}
        try:
            _store_job(user, name, {**job, "time": time_mod.time()})
        finally:
            cache.delete(key)
            connection.close()
    threading.Thread(target=work, daemon=True).start()
    return JsonResponse({"status": "running"})


def _book_request(request, slug):
    get_object_or_404(Worldbook, slug=slug, author=request.user)
    if request.method == "GET":
        return {}, None
    if request.method != "POST":
        return None, JsonResponse({"error": "POST only"}, status=405)
    try:
        return json.loads(request.body.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError):
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)


@login_required
def worldbook_forms(request, slug):
    """🥔 Add word forms: Bulba's suggestions for the editor to show; nothing is saved here."""
    data, error = _book_request(request, slug)
    if error:
        return error
    user = request.user
    book = normalize_book(data.get("book") or {})

    def run():
        forms = word_forms(user, book)
        return {"forms": forms, "note": "" if forms else "Nothing to add: the keywords already cover their forms."}
    background = _book_job(request, slug, "forms", data, run)
    if background is not None:
        return background
    try:
        return JsonResponse(run())
    except ai_client.AIError as e:
        return JsonResponse({"error": str(e)}, status=502)


@login_required
def worldbook_expand(request, slug):
    """🥔 Expand: more keywords, more lore, missing entries (the whole book, or one entry); nothing is saved here."""
    from mainapp.bulba import expand
    data, error = _book_request(request, slug)
    if error:
        return error
    user = request.user
    book = normalize_book(data.get("book") or {})
    what = tuple(w for w in (data.get("what") or ["keys", "lore", "new"]) if w in ("keys", "lore", "new")) or ("keys",)
    uid = data.get("uid")

    def run():
        return expand.expand(user, book, what, int(uid) if uid is not None else None)
    background = _book_job(request, slug, "expand", data, run)
    if background is not None:
        return background
    try:
        return JsonResponse(run())
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    except ai_client.AIError as e:
        return JsonResponse({"error": str(e)}, status=502)


@login_required
def worldbook_test(request, slug):
    """Dry run: which entries would fire for the given messages, and why."""
    get_object_or_404(Worldbook, slug=slug, author=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    # Uses the book as currently shown in the editor, so unsaved edits can be tested
    book = normalize_book(data.get("book") or {})
    messages = [m for m in data.get("messages", []) if isinstance(m, str) and m.strip()]
    result = activate(book, messages, notes_text=str(data.get("note") or "")[:4000])
    return JsonResponse({
        "report": result["report"],
        "notes": result["notes"],
        "tokens_used": result["tokens_used"],
        "prompt": format_for_prompt(result["entries"]),
    })


@login_required
def worldbook_export(request, slug):
    wb = get_object_or_404(Worldbook, slug=slug, author=request.user)
    book = load_worldbook(wb)
    if request.GET.get("format") == "sillytavern":
        payload, suffix = to_sillytavern(book), "_sillytavern"
    else:
        payload, suffix = book, ""
    response = HttpResponse(json.dumps(payload, ensure_ascii=False, indent=2),
                            content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="{wb.slug}{suffix}.json"'
    return response


@login_required
def worldbook_delete(request, slug):
    wb = get_object_or_404(Worldbook, slug=slug, author=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    users = list(wb.characters.values_list("name", flat=True))
    if users:
        return JsonResponse({"error": "This worldbook is still attached to: " + ", ".join(users)
                             + ". Detach it from those characters first."}, status=400)
    if wb.json_file:
        wb.json_file.storage.delete(wb.json_file.name)
    wb.delete()
    return JsonResponse({"status": "ok"})


@login_required
def worldbook_list(request):
    worldbooks = list(Worldbook.objects.filter(author=request.user))
    for wb in worldbooks:
        wb.entry_count = len(load_worldbook(wb)["entries"])
    return render(request, "mainapp/worldbook_list.html", {"worldbooks": worldbooks})



@login_required
def character_delete(request, slug):
    """Deletes one of their characters with its chats and files (POST); its worldbook stays."""
    from users import account
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    name = character.name
    account.delete_character(character)
    return JsonResponse({"success": True, "name": name, "url": reverse("characters_list")})


class CharactersList(LoginRequiredMixin, ListView):
    model = Character
    template_name = 'mainapp/character_list.html'
    context_object_name = 'characters'
    title_page = "Characters List"
    # paginate_by = 3

    def get_queryset(self):
        # Only your own characters, the ones you played most recently first
        from django.db.models import Count, F, Max
        return (Character.objects.filter(author=self.request.user)
                .annotate(last_played=Max("chats__time_update"), chat_count=Count("chats"))
                .order_by(F("last_played").desc(nulls_last=True), "-id"))

    def get_context_data(self, **kwargs):
        from mainapp.models import TagPost
        context = super().get_context_data(**kwargs)
        context["all_tags"] = sorted(set(TagPost.objects.filter(tags__author=self.request.user)
                                         .values_list("tag", flat=True)), key=str.lower)
        return context


class CharacterBaseView(LoginRequiredMixin):
    template_name = "mainapp/add_character.html"
    title_page = None  # child sets this

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_eleven_key"] = bool(get_elevenlabs_key(self.request.user))
        if self.title_page:
            context["title_page"] = self.title_page
        return context


class AddCharacter(CharacterBaseView, CreateView):
    form_class = AddCharacterForm
    title_page = "Add Character"
    success_url = reverse_lazy('characters_list')

    def get_success_url(self):
        if self.request.GET.get("next") == "quick":  # made from the Quick setup page: back there, with it picked
            return reverse("quick_setup") + f"?character={self.object.slug}"
        return super().get_success_url()


    def form_valid(self, form):
        a = form.save(commit=False)
        a.author = self.request.user
        # Формуємо slug: username + "-" + slugified name
        username = self.request.user.username
        base = f"{username}-{slugify(a.name) or 'character'}"
        a.slug, n = base, 2
        while Character.objects.filter(slug=a.slug).exists():  # same name twice gets -2, -3...
            a.slug, n = f"{base}-{n}", n + 1
        a.save()
        return super().form_valid(form)


class UpdateCharacter(CharacterBaseView, UpdateView):
    model = Character
    form_class = AddCharacterForm
    title_page = "Edit Character"
    slug_field = "slug"
    slug_url_kwarg = "slug"


    # --- Обмежуємо queryset лише персонажами залогіненого користувача ---
    def get_queryset(self):
        return Character.objects.filter(author=self.request.user)

    # --- Після успішного збереження редіректимо на чат ---
    def form_valid(self, form):
        character = form.save()
        return redirect(reverse('chat', kwargs={'slug': character.slug}))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["card_rules"] = regex_rules.card_rules(self.object)  # the card's own text rules, switchable
        context["card_note"] = cards.depth_prompt(self.object)  # sent near the latest message
        return context


@login_required
def character_rule(request, slug):
    """Switch one of a card's own text rules on or off."""
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8"))
        regex_rules.set_card_rule(character, str(data.get("id")), bool(data.get("enabled")))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    except KeyError:
        return JsonResponse({"error": "No such rule on this card."}, status=404)
    return JsonResponse({"status": "ok", "rules": regex_rules.card_rules(character)})


@login_required
def character_sections(request, slug):
    """The card as sections (mainapp/card_sections.py): read, save, sort an old card into sections ("Upgrade
    this card"), let Bulba fill the empty ones, write the appearance from the picture, or go back to one box."""
    from mainapp import card_sections
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method == "GET":
        data = card_sections.clean(character.sections) if character.sections else None
        return JsonResponse({"sections": data, "costs": card_sections.costs(data) if data else None,
                             "routes": {k: v[0] for k, v in card_sections.ROUTES.items()},
                             "labels": {k: list(v) for k, v in card_sections.labels("simulation").items()},
                             "description_tokens": card_sections.tokens(character.description)})
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    action = data.get("action")
    sent = card_sections.clean(data.get("sections")) if data.get("sections") else None

    def answer(record, saved=False, **more):
        return JsonResponse({"sections": record, "costs": card_sections.costs(record), "saved": saved,
                             "description": card_sections.compose(record), **more,
                             "spending": ai_client.spending(request.user)})
    try:
        if action == "structure":  # Upgrade this card: sorted, shown, saved only when they press Save
            return answer(card_sections.structure(request.user, character))
        if action == "new":
            kind = data.get("kind") if data.get("kind") in card_sections.KINDS else "character"
            names = (character.name, character.second_name or "") if kind == "ensemble" else (character.name,)
            return answer(card_sections.empty(kind, names if kind != "simulation" else ("",)))
        if action == "fill" and sent:
            return answer(card_sections.fill_empty(request.user, sent, words=int(data.get("words") or 80)))
        if action == "picture" and sent:
            i = int(data.get("person") or 0)
            if not 0 <= i < len(sent["people"]):
                return JsonResponse({"error": "No such person on this card."}, status=400)
            photo = character.photo_second_neutral if i == 1 and character.photo_second_neutral else character.photo_neutral
            if data.get("image"):  # a picture they chose just now (a data URL)
                url = str(data["image"])
                if not url.startswith("data:image/"):
                    return JsonResponse({"error": "That isn't a picture."}, status=400)
                import base64
                url, _ = bulba_vision.prepare(base64.b64decode(url.split(",", 1)[1]))
            elif photo:
                with photo.open("rb") as f:
                    url, _ = bulba_vision.prepare(f.read())
            else:
                return JsonResponse({"error": "Add a neutral picture first (Sprites below), or choose one."}, status=400)
            text, who = card_sections.appearance_from_picture(request.user, sent["people"][i]["name"] or character.name, url)
            sent["people"][i]["sections"]["appearance"]["text"] = text
            return answer(sent, looked=who)
        if action == "save" and sent:
            card_sections.apply(character, sent)
            character.save()
            return answer(card_sections.clean(character.sections), saved=True)
        if action == "plain":  # back to one text box: the composed text stays as the description
            character.sections = {}
            character.save(update_fields=["sections"])
            return JsonResponse({"sections": None, "saved": True, "description": character.description})
    except ai_client.AIError as e:
        return JsonResponse({"error": str(e)}, status=502)
    except ValueError as e:
        return JsonResponse({"error": str(e) or "Bulba's answer didn't make sense. Try again."}, status=502)
    return JsonResponse({"error": "Unknown action."}, status=400)


@login_required
def character_quick(request, slug):
    """The quick view in a chat: the character's card at a glance (picture, who they are, how they look, their
    temperament) and, from this chat's story memory, where the relationship stands and who they've met."""
    from mainapp import card_sections
    from mainapp.models import Chat
    from mainapp.templatetags.custom_filters import blurb, card_look
    character = get_object_or_404(Character, slug=slug, author=request.user)
    chat_obj = Chat.objects.filter(id=request.GET.get("chat") or 0, character=character).first()
    data = chats.read(chat_obj) if chat_obj else {}
    persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    names = prompt_names(request.user, character, persona)
    fill = lambda t: (t or "").replace("{{char}}", character.name).replace("{{user}}", names["user"])
    look = card_look(character)
    sections = card_sections.clean(character.sections) if character.sections else None
    people = []
    if sections:
        for p in sections["people"]:
            sec = p["sections"]
            text = lambda k: fill(sec[k]["text"]) if sec[k]["on"] else ""
            route = card_sections.ROUTES[p["temperament"]["route"]]
            people.append({"name": p["name"] or character.name, "identity": text("identity"), "appearance": text("appearance"),
                           "personality": text("personality"), "voice": text("voice"), "goals": text("goals"),
                           "temperament": text("temperament"), "pace": card_sections.PACES[p["temperament"]["pace"]],
                           "route": route[0], "start": p["temperament"]["start"]})
    shared = {card_sections.labels(sections["kind"])[k][0]: fill(v["text"]) for k, v in sections["shared"].items()
              if v["on"] and v["text"]} if sections else {}
    memory = story_memory.clean(data.get("memory")) if chat_obj else story_memory.empty()
    who = {character.name.lower(), *(p["name"].lower() for p in people)}
    rels = [{**{k: r.get(k) for k in ("from", "to", "stage", "trust", "warmth", "tension")},
             "route": card_sections.ROUTES.get(r.get("route"), card_sections.ROUTES["basic"])[0],
             "ladder": card_sections.ROUTES.get(r.get("route"), card_sections.ROUTES["basic"])[1],
             "last": (r.get("history") or [{}])[-1].get("why", "")}
            for r in memory["relationships"] if r["from"].lower() in who or r["to"].lower() in who]
    rels.sort(key=lambda r: (names["user"].lower() not in (r["from"].lower(), r["to"].lower())))
    last = next((m for m in reversed(memory["milestones"]) if m.get("summary")), None)
    return JsonResponse({
        "name": character.name, "tagline": fill(blurb(character)), "look": look,
        "photo": character.photo_neutral.url if character.photo_neutral else "",
        "second_photo": character.photo_second_neutral.url if character.photo_second_neutral else "",
        "kind": look["kind"], "people": people, "shared": shared,
        "about": "" if sections else fill(character.description)[:900],
        "relationships": rels[:4], "user": names["user"],
        "met": [{"name": p["name"], "identity": p.get("identity", "")} for p in memory["people"]
                if p.get("kind", "person") == "person" and p["name"].lower() not in who][-8:],
        "now": {"title": last.get("title", ""), "where": last.get("where", ""), "summary": last.get("summary", "")[:400]} if last else None,
        "memory_on": bool(chat_obj) and story_memory.chat_mode(request.user, data, len(data.get("messages") or [])) == "memory",
        "edit_url": reverse("character", args=[character.slug]),
    })


SPRITE_EMOTIONS = ["happy", "sad", "angry", "surprised", "scared", "confused", "calm", "scheming"]


@login_required
def eleven_voices(request):
    """The user's ElevenLabs voices, for the voice pickers (the key stays on the server)."""
    from mainapp import voice
    key = get_elevenlabs_key(request.user)
    if not key:
        return JsonResponse({"error": "No ElevenLabs key yet (Extras page)."}, status=400)
    try:
        return JsonResponse({"voices": voice.list_voices(key)})
    except voice.VoiceError as e:
        return JsonResponse({"error": str(e)}, status=502)


@login_required
def image_model_list(request):
    """Image models for the picture maker, with the one used by default."""
    models = ai_client.image_models()
    return JsonResponse({"models": models, "default": ai_client.default_image_model(models)})


def _make_sprite(request, obj, prefix, who, looks, base_name):
    """One mood picture with the image model, saved on `obj` as f"{prefix}_{emotion}": the neutral one from the
    words in `looks`, the others from the neutral picture. Used for characters and for their persona."""
    from django.core.files.base import ContentFile
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    emotion = data.get("emotion")
    extra = False
    if emotion not in SPRITE_EMOTIONS + ["neutral"]:
        emotion = sprite_mod.clean_name(emotion)
        if not emotion or prefix not in ("photo", "photo_second"):  # an extra mood: characters only
            return JsonResponse({"error": "Unknown mood."}, status=400)
        extra = True
    neutral = getattr(obj, f"{prefix}_neutral")
    reference, kind = None, "image/png"
    if emotion == "neutral":  # the first picture, from the words (no picture to start from)
        looks = "\n".join(t for t in (*looks, str(data.get("hint") or "")[:600]) if str(t or "").strip())
        if not looks.strip():
            return JsonResponse({"error": "Write the description first (how they look helps most), "
                                          "or upload a picture."}, status=400)
        prompt = (f"A character portrait of {who}, for a visual-novel style chat: one person, waist up, facing the "
                  f"viewer, a calm neutral expression, a simple background that suits them. Draw them as this "
                  f"description says (appearance first; leave out anything that isn't visible):\n{looks}\n"
                  "Illustrated, consistent and clean. No text, no borders, no extra people.")
    else:
        if not neutral:
            return JsonResponse({"error": "Add a neutral picture first (upload one, or make it from the description "
                                          "with the button above); the moods are made from it."}, status=400)
        with neutral.open("rb") as f:
            reference = f.read()
        kind = "image/png" if reference.startswith(b"\x89PNG") else "image/webp" if reference[:4] == b"RIFF" else "image/jpeg"
        prompt = (f"This is {who}. Make a new picture of exactly the same character: same face, hair, body, outfit, "
                  f"art style, framing, lighting and background. Only the expression and body language change: show "
                  f"them {emotion}. No text, no borders, no extra people.")
    note = " ".join(str(data.get("note") or "").split())[:500]
    if note:  # ↻ a redo with their words: what was wrong last time isn't obvious to the image model
        prompt += f"\nTheir note for this picture (follow it exactly; it fixes what was wrong in the last try): {note}"
    model = data.get("model") or None
    if model:
        known = [m["id"] for m in ai_client.image_models()]
        if known and model not in known:
            return JsonResponse({"error": "OpenRouter doesn't list that image model."}, status=400)
    try:
        image, cost = ai_client.generate_image(request.user, prompt, reference, kind, model=model)
    except ai_client.AIError as e:
        return JsonResponse({"error": str(e)}, status=502)
    ext = "jpg" if image[:3] == b"\xff\xd8\xff" else "webp" if image[:4] == b"RIFF" else "png"
    if extra:  # one of the character's own moods
        try:
            url = sprite_mod.save(obj, emotion, image, ext, second=prefix == "photo_second")
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"status": "ok", "emotion": emotion, "url": url, "cost": cost,
                             "spending": ai_client.spending(request.user)})
    field = getattr(obj, f"{prefix}_{emotion}")
    if field:
        field.storage.delete(field.name)
    field.save(f"{slugify(base_name) or 'character'}-{emotion}.{ext}", ContentFile(image), save=False)
    obj.save()
    return JsonResponse({"status": "ok", "field": f"{prefix}_{emotion}", "url": field.url, "cost": cost,
                         "spending": ai_client.spending(request.user)})


@login_required
def character_moods(request, slug):
    """The character's extra moods (mainapp/sprites.py). GET: what there is. POST (multipart): emotion + picture
    [+ second] to add one; JSON {"remove": emotion[, "second"]} to take one away."""
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method == "POST":
        if request.FILES.get("picture"):
            upload = request.FILES["picture"]
            if upload.size > 15 * 1024 * 1024:
                return JsonResponse({"error": "That picture is over 15 MB."}, status=400)
            ext = (os.path.splitext(upload.name)[1].lower().lstrip(".") or "png")[:5]
            try:
                sprite_mod.save(character, request.POST.get("emotion"), upload.read(), ext,
                                second=request.POST.get("second") == "1")
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
        else:
            body = _json_body(request) or {}
            sprite_mod.remove(character, body.get("remove"), second=bool(body.get("second")))
    return JsonResponse({"first": sprite_mod.extras(character), "second": sprite_mod.extras(character, True),
                         "suggested": sprite_mod.SUGGESTED, "max": sprite_mod.MAX_EXTRA})


@login_required
def character_sprite(request, slug):
    """Makes one mood picture from the character's neutral picture with Nano Banana (OpenRouter)."""
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        second = bool(json.loads(request.body.decode("utf-8")).get("second"))
    except (ValueError, UnicodeDecodeError, AttributeError):
        second = False
    prefix = "photo_second" if second else "photo"
    who = character.name if not second else (character.second_name or f"the second character of {character.name}")
    looks = (str(character.description or "")[:2500], str(character.personality or "")[:600])
    return _make_sprite(request, character, prefix, who, looks, character.name)


@login_required
def persona_sprite(request):
    """The same for their persona: pictures of them in stories (profile page, or Bulba after the persona)."""
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    user = request.user
    if request.FILES.get("file"):  # 📤 their own picture for one mood (any mood, not only neutral)
        mood = request.POST.get("emotion") or ""
        if mood not in ["neutral"] + SPRITE_EMOTIONS:
            return JsonResponse({"error": "Which mood?"}, status=400)
        upload = request.FILES["file"]
        if upload.size > 15 * 1024 * 1024:
            return JsonResponse({"error": "That picture is over 15 MB."}, status=400)
        from PIL import Image, UnidentifiedImageError
        try:
            Image.open(upload).verify()
        except (UnidentifiedImageError, OSError, SyntaxError):
            return JsonResponse({"error": "That file isn't a picture."}, status=400)
        upload.seek(0)
        field = getattr(user, f"persona_photo_{mood}")
        field.save(f"persona-{user.id}-{mood}-{upload.name[-40:]}", upload, save=False)
        user.save(update_fields=[f"persona_photo_{mood}"])
        return JsonResponse({"url": field.url, "field": f"persona_photo_{mood}"})
    who = user.persona_name or "the user's character"
    return _make_sprite(request, user, "persona_photo", who, (str(user.persona_description or "")[:2500],),
                        user.persona_name or user.username)


MAX_CARD_BYTES = 20 * 1024 * 1024


@login_required
def character_import(request):
    """A SillyTavern card (.png or .json, V1/V2/V3) becomes a new character."""
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    upload = request.FILES.get("card")
    if not upload:
        return JsonResponse({"error": "Pick a .png or .json card first."}, status=400)
    if upload.size > MAX_CARD_BYTES:
        return JsonResponse({"error": "That file is over 20 MB, too big for a character card."}, status=400)
    try:
        character = cards.import_file(request.user, upload.read(), upload.name)
    except cards.CardError as e:
        return JsonResponse({"error": str(e)}, status=400)

    notes = []
    if character.alternate_greetings:
        n = len(character.alternate_greetings)
        notes.append(f"{n} alternate greeting{'s' if n != 1 else ''}: swipe the first message to pick one.")
    if character.worldbook:
        notes.append(f"Its lore is now the worldbook “{character.worldbook.title}”.")
    card_rules = regex_rules.card_rules(character)
    if card_rules:
        notes.append(f"It comes with {len(card_rules)} text rule{'s' if len(card_rules) != 1 else ''} "
                     "(regex scripts); they run in its chats.")
    if character.system_prompt or character.post_history_instructions:
        notes.append("The card has its own instructions; they take the place of your preset's main prompt "
                     "(see Advanced on the character's page).")
    edit_url = reverse("character", kwargs={"slug": character.slug})
    if not character.photo_neutral:  # a .json card, or a card without art: straight to where pictures go
        notes.append("It came without a picture: add one in the Sprites section, or make it from the description.")
    return JsonResponse({"status": "ok", "name": character.name, "notes": notes,
                         "url": (reverse("chat", kwargs={"slug": character.slug}) if character.photo_neutral
                                 else edit_url + "#spritesSection"),
                         "edit_url": reverse("character", kwargs={"slug": character.slug})})


@login_required
def character_export(request, slug):
    character = get_object_or_404(Character, slug=slug, author=request.user)
    filename = slugify(character.name) or "character"
    if request.GET.get("format") == "json":
        response = HttpResponse(json.dumps(cards.to_card(character), ensure_ascii=False, indent=2),
                                content_type="application/json")
        response["Content-Disposition"] = f'attachment; filename="{filename}.json"'
    else:
        response = HttpResponse(cards.to_png(character), content_type="image/png")
        response["Content-Disposition"] = f'attachment; filename="{filename}.png"'
    return response


def page_not_found(request, exception):
    return HttpResponseNotFound("<h1>Page not found.</h1>")


# In mainapp/views.py

MEDIA_EXTS = ('.png', '.jpg', '.jpeg', '.webp', '.gif', '.mp3', '.wav', '.ogg', '.m4a')


def user_media_dir(user, kind):
    """(folder on disk, URL prefix) for one person's own uploads ("backgrounds" or "music"). Each person has their
    own folder, so nobody sees anyone else's files and two files with the same name never overwrite each other.
    (Older uploads in the shared custom/ folder stay reachable by their URL but aren't listed for anyone.)"""
    folder = os.path.join(settings.MEDIA_ROOT, kind, "custom", f"u{user.id}")
    os.makedirs(folder, exist_ok=True)
    return folder, f"{settings.MEDIA_URL}{kind}/custom/u{user.id}/"


def unique_upload_name(base, ext):
    return f"{slugify(base)[:60] or 'file'}-{uuid.uuid4().hex[:6]}{ext.lower()}"


@login_required
def get_media_resources(request):
    bg_dir = os.path.join(settings.MEDIA_ROOT, "backgrounds")
    music_dir = os.path.join(settings.MEDIA_ROOT, "music")
    os.makedirs(bg_dir, exist_ok=True)
    os.makedirs(music_dir, exist_ok=True)

    def get_files(kind):
        """The files every install shares (put in the main folder by whoever runs the app), then this person's own."""
        files, directory = [], os.path.join(settings.MEDIA_ROOT, kind)
        for f in os.listdir(directory):
            if f.lower().endswith(MEDIA_EXTS) and os.path.isfile(os.path.join(directory, f)):
                files.append({"name": f, "url": f"{settings.MEDIA_URL}{kind}/{f}"})
        mine, url = user_media_dir(request.user, kind)
        for f in sorted(os.listdir(mine)):
            if f.lower().endswith(MEDIA_EXTS):
                files.append({"name": f"Mine: {f}", "url": url + f})
        return sorted(files, key=lambda x: x['name'])

    if request.method == "POST" and request.FILES:
        try:
            file_type = request.POST.get("type")
            if "file" in request.FILES:
                f = request.FILES["file"]
                kind = "backgrounds" if file_type == "bg" else "music"
                allowed = (".png", ".jpg", ".jpeg", ".webp", ".gif") if file_type == "bg" else (".mp3", ".ogg", ".wav", ".m4a")
                base, ext = os.path.splitext(os.path.basename(f.name))
                if ext.lower() not in allowed:
                    return JsonResponse({"success": False, "error": f"That file type can't be used here ({', '.join(allowed)})."})
                if f.size > 25 * 1024 * 1024:
                    return JsonResponse({"success": False, "error": "That file is over 25 MB."})
                folder, url = user_media_dir(request.user, kind)
                name = unique_upload_name(base, ext)
                with open(os.path.join(folder, name), 'wb') as dest:
                    for chunk in f.chunks():
                        dest.write(chunk)
                return JsonResponse({"success": True, "url": url + name, "name": f"Mine: {name}"})
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    # Return lists for GET requests
    return JsonResponse({
        # Built-in ones ship with the app (static/defaults/), so every install has them
        "backgrounds": media_library.built_in("backgrounds") + get_files("backgrounds"),
        "music": media_library.built_in("music") + media_library.radio_for_picker() + get_files("music")
    })


# ---------------------------------------------------------------------------
# Bulba, the setup assistant
# ---------------------------------------------------------------------------

def _lore_terms(character):
    """📖 The character's lorebook as a glossary for the chat page ([] without one)."""
    from . import lorebook
    if not character.worldbook_id:
        return []
    try:
        return lorebook.glossary(lorebook.load_worldbook(character.worldbook))
    except Exception:
        return []


def _has_chatted(user):
    """They have a story chat or a messenger chat: set up, whichever way they got there."""
    from .models import Chat, MessengerThread
    return Chat.objects.filter(character__author=user).exists() or MessengerThread.objects.filter(user=user).exists()


def _bulba_state(session):
    from .bulba import agent, editing, lore, progress
    profile = agent.target_profile(session)
    character = lore.target_character(session)
    return {
        # the 📎 form starts on "The character's picture" while they have none (a picture sent then is theirs)
        "needs_portrait": bool(character and not character.photo_neutral),
        "id": session.id, "stage": session.stage, "stages": agent.STAGES,
        "progress": progress.progress(session, agent.STAGES) if session.mode == "setup" else None,
        # already chatting (the quick setup, or set up before): the guided steps fold away instead of nagging
        "already_set_up": session.mode == "setup" and session.stage != "done" and _has_chatted(session.user),
        "spent": round(session.spent, 4), "budget": session.budget, "month": ai_client.spending(session.user),
        "chat": _bulba_chat_link(session) if session.mode == "setup" else None,
        "mode": session.mode,
        "chat_with": session.chat.character.name if session.mode == "chat" and session.chat_id else "",
        "model": agent.shown_name(profile) if profile else session.target_model,
        "preferences": [p for p in session.preferences if p.get("status") not in ("rejected", "superseded")],
        "proposals": [{**{k: p.get(k) for k in ("id", "kind", "title", "status", "result", "edited")},
                       "summary": _shown_summary(session, p), "editable": editing.fields(p),
                       **({"preview": _theme_preview(p)} if p["kind"] == "theme" else {})} for p in session.proposals],
    }


def _theme_preview(p):
    """What a theme card shows besides its words: the background picture, the music to play, the colour."""
    t = (p.get("payload") or {}).get("theme") or {}
    bg, music = t.get("background") or {}, t.get("music") or {}
    return {"bg": bg.get("url", ""), "bg_name": bg.get("name", ""), "music": music.get("url", ""),
            "music_name": music.get("name", ""), "color": t.get("dialogue_color", ""), "weather": t.get("weather", ""),
            "skin": t.get("skin", ""), "skin_name": CHAT_SKINS.get(t.get("skin", ""), ""),
            # story colours: a sample line per speaker, in their colour
            "speech": t.get("speech", ""),
            "lines": [[who, speaker_colors.PALETTE[c][0]] for who, c in
                      [*(t.get("speech_cast") or {}).items(), *([["You", t["you_color"]]] if t.get("you_color") else [])]
                      if c in speaker_colors.PALETTE]}


def _bulba_chat_link(session):
    """The character Bulba made (the newest applied one), to start chatting from the page."""
    for p in reversed(session.proposals):
        if p["kind"] == "character" and p["status"] == "applied" and (p.get("result") or {}).get("slug"):
            character = Character.objects.filter(author=session.user, slug=p["result"]["slug"]).first()
            if character:
                return {"name": character.name, "url": reverse("chat", kwargs={"slug": character.slug}),
                        "edit_url": reverse("character", kwargs={"slug": character.slug}) + "#spritesSection"}
    return None


def _shown_summary(session, proposal):
    """Proposal text as the user reads it: {{user}} is their name, {{char}} the character's (or "the character")."""
    char = (proposal.get("payload") or {}).get("name") if proposal["kind"] == "character" else "the character"
    user = cards.user_name(session.user)
    return [cards.fill_names(line, char or "the character", user) for line in proposal.get("summary") or []]


def _bulba_session(user, restart=False):
    """The user's current Bulba conversation for their chat model, started if needed. None if Bulba can't help."""
    from .bulba import agent
    from .models import BulbaSession
    try:
        _, chat_model = ai_client.resolve(user, "chat")
    except ai_client.NoConnection:
        return None
    profile = model_profiles.for_style(chat_model)  # an unknown model: its closest relative's knowledge
    if profile is None:
        return None
    session = BulbaSession.objects.filter(user=user, active=True, mode="setup").first()
    if session and not restart and session.target_model != profile["id"]:
        logging.getLogger(__name__).info("Setup conversation %s restarted: the chat model changed (%s -> %s)",
                                         session.id, session.target_model, profile["id"])
    if session and (restart or session.target_model != profile["id"]):
        session.active = False
        session.save(update_fields=["active"])
        session = None
    if session is None:
        session = BulbaSession(user=user, target_model=profile["id"])
        agent.opening(session)
        session.save()
    return session


def _bulba_chat_session(user, chat_obj, restart=False):
    """Bulba's conversation about one chat (opened from the chat page). None if Bulba can't help."""
    from .bulba import doctor
    from .models import BulbaSession
    try:
        _, chat_model = ai_client.resolve(user, "chat")
    except ai_client.NoConnection:
        return None
    profile = model_profiles.for_style(chat_model)
    session = BulbaSession.objects.filter(user=user, active=True, mode="chat", chat=chat_obj).first()
    if session and restart:
        session.active = False
        session.save(update_fields=["active"])
        session = None
    if session is None:
        session = BulbaSession(user=user, target_model=profile["id"] if profile else "", mode="chat", chat=chat_obj)
        doctor.opening(session)
        session.save()
    return session


def _bulba_texting_session(user, thread, restart=False):
    """Bulba's conversation about one messenger chat (opened from its header in the Screen Hub)."""
    from .bulba import texting
    from .models import BulbaSession
    session = BulbaSession.objects.filter(user=user, active=True, mode="texting", thread=thread).first()
    if session and restart:
        session.active = False
        session.save(update_fields=["active"])
        session = None
    if session is None:
        try:
            _, chat_model = ai_client.resolve(user, "chat")
        except ai_client.NoConnection:
            return None
        profile = model_profiles.for_style(chat_model)
        session = BulbaSession(user=user, target_model=profile["id"] if profile else "", mode="texting", thread=thread,
                               focus=thread.characters.first())
        texting.opening(session)
        session.save()
    return session


def _bulba_for_request(request, restart=False):
    """The setup conversation, or the one about a chat when the page passes ?chat=<id> (?thread=<id>: a
    messenger chat)."""
    from .models import Chat
    if request.GET.get("thread"):
        thread = MessengerThread.objects.filter(id=request.GET.get("thread"), user=request.user).first()
        if thread is None:
            raise Http404("No such chat.")
        return _bulba_texting_session(request.user, thread, restart)
    chat_id = request.GET.get("chat")
    if chat_id:
        chat_obj = Chat.objects.filter(id=chat_id, character__author=request.user).first()
        if chat_obj is None:
            raise Http404("No such chat.")
        return _bulba_chat_session(request.user, chat_obj, restart)
    return _bulba_session(request.user, restart)


@login_required
@xframe_options_sameorigin  # shown beside the Quick setup form (?embed=1); only this site may frame it
def bulba_page(request):
    if not ai_client.has_connection(request.user):
        return redirect("users:welcome")
    route = request.GET.get("route")
    if route == "fast":  # the quick way is its own page now (Bulba can still be asked from every part of it)
        return redirect("quick_setup")
    session = _bulba_session(request.user)
    if session and route == "full" and len(session.events) == 1:  # picked on the welcome tour's last step
        from .bulba import agent
        try:
            agent.take_route(session, route)
            session.save()
        except ValueError:  # no ready setup for this model: Bulba's opening asks as usual
            pass
    from .models import BulbaSession
    # Bulba's conversations inside chats live on those chats' pages; list them so they're easy to find
    in_chats = [{"title": f"{b.chat.character.name} · {b.chat.title}", "events": len(b.events),
                 "url": reverse("chat", kwargs={"slug": b.chat.character.slug}) + f"?chat={b.chat.id}&bulba=1"}
                for b in BulbaSession.objects.filter(user=request.user, active=True, mode="chat")
                .select_related("chat__character").order_by("-time_update")[:8] if b.chat_id and len(b.events) > 1]
    return render(request, "mainapp/bulba.html", {
        "bulba_data": {"state": _bulba_state(session), "events": session.events,
                       "basics_form": basics_mod.form()} if session else None,
        "known_models": model_profiles.known_names(),
        "in_chats": in_chats,
        "embed": request.GET.get("embed") == "1",  # beside the Quick setup form
    })


@login_required
def quick_setup(request):
    """The quick way in: a short form (writing style, chat memory, who you are, your character, and the extras
    and worldbooks under Additional). Every part explains itself and can be handed to Bulba instead."""
    from users.views import _extras_page_state, set_chat_context
    if not ai_client.has_connection(request.user):
        return redirect("users:welcome")
    _, chat_model = ai_client.resolve(request.user, "chat")
    profile = model_profiles.for_style(chat_model) or {}  # an unknown model: its closest relative's ready setups
    ready = starters.ready_for(profile.get("id", "")) if profile else []
    active = presets.get_active(request.user)
    active_starter = (presets.normalize(active.data)["extras"].get("starter") or {}).get("id", "")
    if request.method == "POST":
        try:
            data = json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({"error": "Invalid request."}, status=400)
        user = request.user
        if data.get("starter") and data["starter"] != active_starter:
            if data["starter"] not in [r["id"] for r in ready]:
                return JsonResponse({"error": "Pick one of the writing styles shown."}, status=400)
            starters.apply_ready(user, data["starter"], mode=data.get("control") if data.get("control") in experiences.CONTRACTS else None)
        try:
            context = int(data.get("chat_context") or 0)
        except (TypeError, ValueError):
            context = 0
        if context:
            set_chat_context(user, max(4096, min(2_000_000, context)))
        if isinstance(data.get("mature"), bool) and data["mature"] != mature.is_on(presets.normalize(presets.get_active(user).data)):
            error = mature.switch(user, data["mature"], adult_confirmed=data["mature"])
            if error:
                return JsonResponse({"error": error}, status=400)
        if "persona_name" in data:
            user.persona_name = str(data.get("persona_name") or "").strip()[:100]
            user.persona_description = str(data.get("persona_description") or "").strip()[:8000]
            user.save(update_fields=["persona_name", "persona_description"])
        if data.get("display_language") in translation.LANGUAGES and data["display_language"] != user.display_language:
            user.display_language = data["display_language"]
            user.save(update_fields=["display_language"])
            if translation.reading_language(user):  # the old "Write the whole story in X." would fight it
                translation.drop_language_rule(user)
        if any(k in data for k in QUICK_BASICS):
            _save_quick_basics(user, {k: data.get(k) for k in QUICK_BASICS})
        if isinstance(data.get("modules"), dict):  # the optional story modules (experiences.py)
            active = presets.get_active(user)
            try:
                custom = data.get("custom_object")
                updated = experiences.set_modules(presets.normalize(active.data), data["modules"],
                                                  (model_profiles.for_style(chat_model) or {}).get("id", ""),
                                                  custom=custom if isinstance(custom, str) else None)
            except ValueError as e:
                return JsonResponse({"error": str(e)}, status=400)
            if not mature.is_on(updated):  # 18+ modules only with adult scenes allowed
                updated = experiences.set_modules(updated, {k: False for k in experiences.ADULT})
            active.data = updated
            active.save(update_fields=["data"])
        character = Character.objects.filter(author=user, slug=str(data.get("character") or "")).first()
        url = reverse("chat", kwargs={"slug": character.slug}) if character else None
        return JsonResponse({"status": "ok", "url": url})
    state = _extras_page_state(request.user)
    characters = list(Character.objects.filter(author=request.user).order_by("-time_update")[:12])
    picked = request.GET.get("character") or (characters[0].slug if characters else "")
    if request.GET.get("status"):  # the page refreshes its sections after Bulba applies something beside it
        return JsonResponse(_quick_status(request.user, picked, characters))
    return render(request, "mainapp/quick.html", {
        "status": _quick_status(request.user, picked, characters),
        "languages": translation.LANGUAGES, "basics": (qb := _quick_basics(request.user)),
        "questions": _quick_questions(qb, QUICK_MAIN), "more_questions": _quick_questions(qb, QUICK_MORE),
        "line_voices": [{"value": v, "label": l} for v, l in basics_mod.question("voice")["options"]
                        if v != "any" and f"voice_{v}" not in experiences.catalog()["modules"]],
        "model_name": (f"{chat_model}, borrowed from {profile['name']} (its closest relative; not tested on yours)"
                       if profile.get("_borrowed") else f"{chat_model} (no notes for it yet: plain presets for any model)"
                       if profile.get("_generic") else profile.get("name") or chat_model),
        "ready": ready, "active_starter": active_starter,
        "active_name": active.name, "characters": characters, "picked": picked,
        "mature_on": mature.is_on(presets.normalize(active.data)),
        "module_groups": _module_groups(presets.normalize(active.data)),
        "quick_data": {"window": state.get("window"), "prices": state.get("prices")},
    })


# Quick setup's Basics: point of view, tense, speech and actions (Bulba's own wording, agent.BASICS), kept as one
# "Basics" block in the active preset; the story language is the profile's (translation workflow)
QUICK_BASICS = ("pov", "tense", "format", "interior", "pacing", "initiative", "invention", "genres",
                "voice", "author", "keep_out", "length", "control")
# length goes in the preset's Reply length block, control is the Your character contract; the rest are Basics lines
BASICS_LINES = ("pov", "tense", "format", "interior", "pacing", "initiative", "invention", "genres",
                "voice", "author", "keep_out")  # written by mainapp/basics.py, the same lines Bulba's form writes


def _module_groups(preset):
    """Quick setup's optional story modules, grouped (voices as one pick), with what the active preset has on."""
    groups = {}
    for m in experiences.module_states(preset):
        groups.setdefault(m["group"], []).append(m)
    order = ["characters", "world", "story", "prose", "collaboration", "voice", "objects", "mature"]
    return [{"key": g, "label": experiences.GROUP_LABELS.get(g, g), "modules": groups[g]} for g in order if g in groups]


QUICK_MAIN = ("pov", "tense", "length", "control", "format", "interior")
QUICK_MORE = ("pacing", "initiative", "invention", "genres", "author", "keep_out")


def _quick_questions(current, keys):
    """Quick setup's questions, worded exactly as Bulba's basics form asks them (mainapp/basics.py)."""
    out = []
    for key in keys:
        f = basics_mod.question(key)
        if not f:
            continue
        q = {"key": key, "label": f["label"], "hint": f.get("hint", ""), "help": f.get("help", ""),
             "current": current.get(key, "") or ("flexible" if key == "length" else "")}
        if f.get("multi"):
            kinds, names = set(f.get("kinds") or []), dict(f.get("groups") or [])
            group = (lambda v: "kind" if v in kinds else "mood") if names else (lambda v: "")
            # mood chips first, then kinds of story, each under its own small heading; 18+ ones last
            q["multi"] = sorted([{"value": v, "label": l, "adult": False, "group": group(v)} for v, l in f["multi"]],
                                key=lambda o: o["group"] == "kind") + \
                         [{"value": v, "label": l, "adult": True, "group": "kind" if names else ""} for v, l in f.get("adult") or []]
            q["group_names"] = names
            q["current"] = current.get(key) or []
        elif "options" in f:
            q["options"] = [{"value": v, "label": l} for v, l in f["options"] if v != "any"]
            q["empty"] = "" if key in ("length", "control") else "As the story has it"
        else:
            q["text"], q["placeholder"] = True, f.get("placeholder", "")
        out.append(q)
    return out


def _quick_basics(user):
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).first()
    saved = ((obj.appearance or {}).get("quick_basics") if obj else None) or {}
    out = {"display_language": user.display_language or "en", **{k: saved.get(k, "") for k in QUICK_BASICS}}
    out["genres"] = saved.get("genres") or []
    from mainapp import basics
    from mainapp.bulba import control
    data = presets.normalize(presets.get_active(user).data)
    out.update({k: v for k, v in basics.read(data).items() if k in BASICS_LINES})  # what the preset says now,
    out["control"] = control.mode_of(data)                                         # whichever form set it
    return out


def _save_quick_basics(user, picks):
    from mainapp.bulba.agent import BASICS
    from mainapp.models import ChatSettings
    from mainapp import basics
    sent = {k: v for k, v in picks.items() if v is not None}
    answers = {}  # Basics lines: an answer replaces its own line; "As the story has it" ("") removes it
    for k in BASICS_LINES:
        if k not in sent:
            continue
        v = sent[k]
        if k == "genres":
            answers[k] = [g for g in (v if isinstance(v, list) else []) if g in BASICS[k][1]]
        elif BASICS[k][1] is None:
            answers[k] = str(v or "").strip()[:300]
        else:
            answers[k] = v if v in BASICS[k][1] else ""
    picks = {k: v for k, v in sent.items() if k not in BASICS_LINES and isinstance(v, str) and v in (BASICS[k][1] or {})}
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    obj.appearance = {**(obj.appearance or {}), "quick_basics": {**{k: v for k, v in picks.items() if k != "control"},
                                                                 **answers}}
    obj.save(update_fields=["appearance"])
    active = presets.get_active(user)
    data = presets.normalize(active.data)
    from mainapp.bulba import control
    if picks.get("control") and picks["control"] != control.mode_of(data):
        data = control.apply_to_preset(data, picks["control"])
        if picks["control"] == "director":
            set_layout(user, "book")
    length_set = bool(picks.get("length")) and experiences.set_length(data, picks["length"])
    if answers.get("genres") and not mature.is_on(data):  # adult genres only with adult scenes allowed
        answers["genres"] = [g for g in answers["genres"] if g not in ("smut", "dead_dove")]
    basics.set_answers(data, answers)
    if not (answers or length_set or picks.get("control")):
        return
    active.data = data
    active.save(update_fields=["data"])


def _quick_status(user, picked, characters):
    """What's set now, per section of Quick setup (shown with ✓, refreshed after Bulba applies something)."""
    from users.views import _extras_state
    active = presets.get_active(user)
    ex = _extras_state(user)
    character = next((c for c in characters if c.slug == picked), None)
    theme = (character.theme or {}) if character else {}
    extras_bits = []
    if ex["summary"]["mode"] == "auto":
        extras_bits.append(f"summaries every {ex['summary']['interval']} messages")
    if ex["trackers"]["mode"] == "auto":
        extras_bits.append(f"trackers every {ex['trackers']['interval']} messages")
    if ex["sprites"]:
        extras_bits.append("mood pictures")
    if ex["story_extras"]:
        extras_bits.append(", ".join(extras.KINDS[k].lower() for k in ex["story_extras"]))
    if ex["game"] != "off":
        extras_bits.append("dice" if ex["game"] == "dice" else "dice and inventory")
    look = []
    if theme.get("bg"):
        look.append(os.path.splitext(os.path.basename(str(theme["bg"])))[0].replace("-", " ").replace("_", " "))
    if (theme.get("music") or {}).get("name"):
        look.append("music: " + theme["music"]["name"])
    if theme.get("skin") in CHAT_SKINS:
        look.append(CHAT_SKINS[theme["skin"]])
    wb = character.worldbook if character and character.worldbook_id else None
    return {
        "style": active.name,
        "persona_name": user.persona_name or "", "persona_description": user.persona_description or "",
        "characters": [{"slug": c.slug, "name": c.name, "photo": c.photo_neutral.url if c.photo_neutral else ""}
                       for c in characters],
        "picked": picked, "character_name": character.name if character else "",
        "extras": "; ".join(extras_bits),
        "look": " · ".join(look),
        "worldbook": (f"“{wb.title}” ({len(load_worldbook(wb)['entries'])} entries)" if wb else ""),
        "worldbook_url": reverse("worldbook_detail", args=[wb.slug]) if wb else "",
    }


@login_required
@xframe_options_sameorigin  # shown inside Bulba's card (an iframe); without this the browser refuses it
def bulba_look_preview(request, pid):
    """A small mock chat in a proposed custom look, shown inside Bulba's card before they press Apply."""
    from mainapp.models import BulbaSession
    proposal = None
    for session in BulbaSession.objects.filter(user=request.user).order_by("-id")[:20]:
        proposal = next((p for p in session.proposals or [] if p.get("id") == pid and p.get("kind") == "chat_look"), None)
        if proposal:
            break
    if proposal is None:
        raise Http404("No such look.")
    look = chat_looks.clean(proposal["payload"].get("look"))
    character = Character.objects.filter(author=request.user, id=proposal["payload"].get("character_id")).first()
    name = character.name if character else "Character"
    you = prompt_names(request.user, character, None)["user"] if character else "You"
    return render(request, "mainapp/look_preview.html", {
        "look": look, "look_css": chat_looks.css(look, name, you), "look_fonts": chat_looks.fonts_url(look),
        "look_data": chat_looks.page_data(look), "name": name, "you": you,
        "photo": character.photo_neutral.url if character and character.photo_neutral else "",
    })


@login_required
def bulba_explain(request):
    """What's this? Bulba explains one thing they clicked (or asked about) on a page."""
    from .bulba import explain
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    if not isinstance(data, dict):
        return JsonResponse({"error": "Invalid request."}, status=400)
    if not ai_client.has_connection(request.user):
        return JsonResponse({"error": "Bulba needs your OpenRouter or NanoGPT key first (the welcome page)."}, status=400)
    try:
        return JsonResponse({"text": explain.explain(request.user, data)})
    except ai_client.AIError as e:
        return JsonResponse({"error": str(e)}, status=502)


@login_required
@xframe_options_sameorigin
def bulba_chat_page(request, chat_id):
    """Bulba about one chat, shown in a side panel on the chat page."""
    from .models import Chat
    chat_obj = get_object_or_404(Chat, id=chat_id, character__author=request.user)
    session = _bulba_chat_session(request.user, chat_obj)
    return render(request, "mainapp/bulba.html", {
        "bulba_data": {"state": _bulba_state(session), "events": session.events,
                       "basics_form": basics_mod.form()} if session else None,
        "known_models": model_profiles.known_names(),
        "embed": True, "chat_obj": chat_obj,
    })


@login_required
@xframe_options_sameorigin
def bulba_texting_page(request, thread_id):
    """Bulba about one messenger chat, shown in a side panel in the Screen Hub."""
    thread = get_object_or_404(MessengerThread, id=thread_id, user=request.user)
    session = _bulba_texting_session(request.user, thread)
    return render(request, "mainapp/bulba.html", {
        "bulba_data": {"state": _bulba_state(session), "events": session.events,
                       "basics_form": basics_mod.form()} if session else None,
        "known_models": model_profiles.known_names(),
        "embed": True, "thread_obj": thread,
    })


@login_required
def bulba_api(request):
    """One Bulba action at a time per conversation: a phone that lost the connection mid-turn and sent again
    would otherwise run two turns on the same conversation, and the one saved last would erase the other's cards."""
    from django.core.cache import cache
    if request.method != "POST":
        return _bulba_api(request)
    key = f"bulba-busy:{request.user.id}:{request.GET.get('chat') or ('t' + request.GET['thread'] if request.GET.get('thread') else 'setup')}"
    if not cache.add(key, 1, BULBA_TURN_SECONDS):
        return JsonResponse({"error": "Bulba is still working on your last message. Give it a moment, then try "
                                      "again (the page shows the answer when it's ready).", "busy": True}, status=409)
    try:
        response = _bulba_api(request)
    finally:
        cache.delete(key)
    if response.status_code == 400:  # a card from an older version of the conversation: show the current one
        try:
            error = json.loads(response.content).get("error", "")
        except ValueError:
            error = ""
        if error.startswith("No such proposal"):
            return JsonResponse({"error": "That card was out of date (Bulba's conversation moved on in the "
                                          "meantime). The page will refresh to show the latest.", "stale": True},
                                status=409)
    return response


BULBA_TURN_SECONDS = 330  # longer than any turn can take (gunicorn stops a request at 300)


def _bulba_api(request):
    from .bulba import actions, agent, editing, progress
    from .models import BulbaSession
    if request.method == "GET":  # what Bulba is doing right now (the page asks while a turn runs)
        filters = {"mode": "chat", "chat_id": request.GET["chat"]} if request.GET.get("chat") else {"mode": "setup"}
        session = BulbaSession.objects.filter(user=request.user, active=True, **filters).first()
        from django.core.cache import cache
        busy = cache.get(f"bulba-busy:{request.user.id}:{request.GET.get('chat') or 'setup'}") is not None
        out = {"activity": session.activity if session else "", "busy": busy}
        if request.GET.get("full") and session:  # the page lost the connection mid-turn: what's there now
            out.update(events=session.events, state=_bulba_state(session))
        return JsonResponse(out)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    if request.FILES.get("card"):  # a card they already have, from the upload box
        return _bulba_card_upload(request)
    if request.FILES.get("preset"):  # a preset they already have (SillyTavern or ours), from the upload box
        return _bulba_preset_upload(request)
    if request.FILES.get("picture"):  # the character's picture, a mood, or a background
        return _bulba_picture_upload(request)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    action = data.get("action")
    session = _bulba_for_request(request, restart=(action == "restart"))
    if session is None:
        return JsonResponse({"error": "Bulba only knows the models on the welcome page. Pick one of those first."}, status=400)

    events = []
    if action == "restart":
        events = session.events
    elif action == "say":
        session.beside_quick = bool(data.get("beside_quick")) and session.mode == "setup"
        events = agent.run_turn(session, data.get("text"))
    elif action in ("retry_failed", "remove_failed"):  # a message Bulba couldn't answer: again, or gone
        try:
            if action == "retry_failed":
                agent.retry_failed(session)
            else:
                agent.remove_failed(session)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        session.activity = ""
        session.save()
        return JsonResponse({"events": session.events, "replace": True, "state": _bulba_state(session)})
    elif action == "route":  # the opening's full setup or fast route (no AI needed)
        try:
            events = agent.take_route(session, str(data.get("route") or ""))
        except (ValueError, actions.ProposalError) as e:
            return JsonResponse({"error": str(e)}, status=400)
    elif action == "skip":  # the panel's Skip button: on to the next stage
        try:
            skipped, moved = agent.skip_stage(session)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        label, nxt = progress.STAGES[skipped][0], progress.STAGES[session.stage][0]
        events = agent.run_turn(
            session, None, action_note=f"Skipped: {label}",
            model_note=f"Skipped: {label}. They pressed Skip. Start the next stage ({session.stage}: {nxt}) with "
                       "its first question; don't go back to the skipped one unless they ask")
        # The new stage's mark goes right after the "Skipped" line, before Bulba's message
        session.events.insert(len(session.events) - len(events) + 1, moved)
        events.insert(1, moved)
    elif action == "note":  # a Bulba Watch note they opened in a chat: Bulba explains it and proposes a fix
        from .bulba import watch
        if session.mode != "chat" or not session.chat_id:
            return JsonResponse({"error": "Notes belong to a chat."}, status=400)
        try:
            note = watch.set_notice(request.user, session.chat, str(data.get("id") or ""), "opened")
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        session.activity = ""
        events = agent.run_turn(session, None, action_note=f"Bulba Watch: {note['title']}",
                                model_note=watch.for_bulba(note))
        session.save()
        return JsonResponse({"events": events, "state": _bulba_state(session),
                             "watch": watch.page_state(request.user, session.chat)})
    elif action == "extras_form":  # the extras in one form: applied at once (Undo on the card)
        part = data.get("part") if data.get("part") in ("story", "memory") else "setup"
        answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
        form_event = next((e for e in reversed(session.events) if e.get("type") == "extras_form"
                           and e.get("part") == part), None)
        if form_event is None:
            return JsonResponse({"error": "There's no form to answer."}, status=400)
        payload, summary = agent.form_payload(part, answers)
        tracker_pick = agent.form_trackers(session, answers) if part == "story" else None
        if not payload and not tracker_pick:
            return JsonResponse({"error": "Nothing picked."}, status=400)
        shown, note, proposal = [], "", None
        if payload:
            title = {"setup": "Extras", "story": "Story extras", "memory": "Chat memory"}[part]
            proposal = agent._proposal(session, "memory" if part == "memory" else "extras", title, summary, payload)
            try:
                note = actions.apply(session, proposal["id"])
            except actions.ProposalError as e:
                session.proposals.remove(proposal)
                return JsonResponse({"error": str(e)}, status=400)
            shown.append({"type": "proposal", "id": proposal["id"]})
        form_event["answers"] = {**{k: payload.get(k) for k in payload},
                                 **({"trackers": answers["trackers"]} if tracker_pick is not None else {})}
        if tracker_pick:  # the trackers they kept ticked, for the character: their own card, with Undo
            pid, lines = tracker_pick
            note = (note + " " + actions.apply(session, pid)).strip()
            shown.append({"type": "proposal", "id": pid})
            summary += lines
        moved = agent.advance_stage(session, proposal) if proposal and part != "memory" else None
        shown += [moved] if moved else []
        if part == "memory":  # the Fast route's memory step: on to the persona question, no AI needed
            events = agent.after_memory_form(session, shown)
        elif part == "setup" and session.stage == "taste":  # the basics form comes next, no AI needed
            events = agent._canned(session, "Sent the extras",
                                   "Done. Now the main part: how replies should read. Answer what you care about, "
                                   "skip the rest.", extra_events=shown, after=[{"type": "form", "form": "basics"}])
            session.messages[-2]["content"] = "[Sent the extras form; applied: " + "; ".join(summary) + "]"
        else:
            events = agent.run_turn(session, None, action_note="Sent the extras",
                                    model_note=f"They sent the {'story ' if part == 'story' else ''}extras form; "
                                               f"applied: {'; '.join(summary)}. {note} Don't ask about these again; "
                                               "carry on with the next step")
            # The card (and the new stage) go right after the "Sent" line, before Bulba's message
            at = len(session.events) - len(events) + 1
            session.events[at:at] = shown
            events[1:1] = shown
    elif action == "basics":  # the basics form: recorded as preferences, then Bulba carries on
        answers = data.get("answers") if isinstance(data.get("answers"), dict) else {}
        form_event = next((e for e in reversed(session.events) if e.get("type") == "form"), None)
        if form_event is not None:  # the sent form keeps showing what they picked
            form_event["answers"] = {str(k)[:40]: ([str(x)[:80] for x in v][:20] if isinstance(v, list) else str(v)[:300])
                                     for k, v in answers.items()}
        text = agent.apply_basics(session, data.get("answers"))
        events = agent.run_turn(session, None, action_note="Sent the basics", model_note=text)
    elif action in ("apply", "dismiss", "undo"):
        try:
            note = getattr(actions, action)(session, data.get("id"))
        except actions.ProposalError as e:
            return JsonResponse({"error": str(e)}, status=400)
        proposal = next(p for p in session.proposals if p["id"] == data.get("id"))
        verb = {"apply": "Applied", "dismiss": "Dismissed", "undo": "Undid"}[action]
        events = [{"type": "note", "text": note}]
        session.events.append(events[0])
        moved = agent.advance_stage(session, proposal) if action == "apply" else None
        if moved:  # the panel moves on, and Bulba reads the next stage's guides
            events.append(moved)
            session.events.append(moved)
        note_for_bulba = f"{verb}: {proposal['title']}"
        link = _bulba_chat_link(session) if action == "apply" and proposal["kind"] == "character" else None
        if link:  # so Bulba can point to the right places (pictures go on the character's page)
            note_for_bulba += f" — chat: {link['url']}, pictures (Sprites section): {link['edit_url']}"
        if action == "apply" and proposal["kind"] == "connections":  # 🔁 a new chat model: does their preset still fit?
            from .bulba import connections as conn_mod
            after = conn_mod.after_model_change(request.user)
            if after:
                note_for_bulba += "\n\n" + after
        if action == "apply" and proposal["kind"] == "character":  # 🧭 and on to persona, world, extras
            from .bulba import lore as lore_mod
            note_for_bulba += "\n\n" + lore_mod.AFTER_NEW_CARD
        events += agent.run_turn(session, None, action_note=f"{verb}: {proposal['title']}", model_note=note_for_bulba)
    elif action == "forget":  # the user removes a preference Bulba recorded
        pref = next((p for p in session.preferences if p["id"] == data.get("id")), None)
        if pref:
            pref["status"] = "rejected"
            session.messages.append({"role": "user", "content": f"[I removed this preference: {pref['interpretation']}]"})
    elif action == "use_retry":  # a reply Bulba rewrote in a chat becomes a new version of the chat's last reply
        if session.chat_id is None:
            return JsonResponse({"error": "That only works inside a chat."}, status=400)
        ev = next((e for e in session.events if e.get("retry_id") and e["retry_id"] == data.get("id")), None)
        chat_data = chats.read(session.chat)
        messages = chat_data.get("messages") or []
        if ev is None or not ev.get("samples"):
            return JsonResponse({"error": "That rewrite is gone."}, status=400)
        if ev.get("used"):
            return JsonResponse({"error": "It's in the chat already."}, status=400)
        if len(messages) != ev.get("at") or not messages or messages[-1][0] != "assistant":
            return JsonResponse({"error": "The chat has moved on since; ask Bulba to rewrite the new last reply."},
                                status=400)
        last = tuple(messages[-1])
        new = chats.with_reasoning(("assistant", datetime.now().strftime("%H:%M"), ev["samples"][0]["text"],
                                    last[3], last[4]), ev.get("reasoning") or "")
        messages[-1] = chats.add_version(last, new)
        chat_data["messages"] = messages
        chats.write(session.chat, chat_data)
        ev["used"] = True
        events = [{"type": "note", "text": "It's in the chat now, as a new version of the last reply (the arrows "
                                           "under it flip back to the old one)."}]
        session.events.append(events[0])
        session.messages.append({"role": "user", "content": "[I put your rewritten reply into the chat.]"})
    elif action == "edit_proposal":  # the user rewrites a proposal's text before applying it
        try:
            proposal, changed = editing.edit(session, data.get("id"), data.get("values"))
        except (ValueError, KeyError, IndexError, TypeError) as e:
            return JsonResponse({"error": str(e) or "Couldn't save that."}, status=400)
        if changed:
            session.messages.append({"role": "user", "content": f"[I edited your proposal “{proposal['title']}” before "
                                     f"applying it ({', '.join(changed)}). Treat my wording as what I want.]"})
            events = [{"type": "action", "text": f"Edited: {proposal['title']}"}]
            session.events.append(events[0])
    elif action == "edit_preference":  # the user rewords what Bulba noted; it counts as confirmed
        pref = next((p for p in session.preferences if p["id"] == data.get("id")), None)
        text = str(data.get("text") or "").strip()[:300]
        if pref is None or not text:
            return JsonResponse({"error": "Nothing to change."}, status=400)
        old, pref["interpretation"], pref["status"] = pref["interpretation"], text, "confirmed"
        session.messages.append({"role": "user", "content": f"[I reworded a preference you noted: “{old}” → “{text}”]"})
    elif action == "budget":
        try:
            session.budget = max(0.5, min(50.0, float(data.get("value"))))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Enter an amount in dollars."}, status=400)
    else:
        return JsonResponse({"error": "Unknown action."}, status=400)
    session.activity = ""
    session.save()
    return JsonResponse({"events": events, "state": _bulba_state(session)})


def _bulba_picture_upload(request):
    """A picture for Bulba: just to look at ("look": a screenshot, character art, a place, a moodboard), or to
    use as the character's picture, a mood or a background (Bulba looks at the main picture and backgrounds too)."""
    from django.core.files.base import ContentFile
    from .bulba import agent, lore, vision
    session = _bulba_for_request(request, restart=False)
    if session is None:
        return JsonResponse({"error": "Bulba isn't available."}, status=400)
    upload, target = request.FILES["picture"], request.POST.get("as", "look")
    their_words = str(request.POST.get("text") or "").strip()[:2000]
    emotion = str(request.POST.get("emotion") or "").strip()[:40]
    # The three kinds on the page: the character (a mood picture, or a reference for their appearance), the chat
    # look (inspiration, or a picture behind the chat), anything else ("look")
    hints = {
        "appearance": "It's the character" + (f" ({emotion})" if emotion else "") + ", for their appearance: "
                      "write or update the card's Appearance from it (propose_card_edit section_edits appearance on a "
                      "card kept as sections; for a card you're still making, use it there).",
        "ui": "It's inspiration for how their chat page should look: read_look_options, then propose_chat_look "
              "(match its palette and mood first, then shapes, lettering, decorations).",
        "ui_background": "They want it behind the chat in their custom look: propose_chat_look with changes "
                         "{\"background\": \"picture\", \"picture\": the URL below, \"veil\": about 40} (or a whole "
                         "look around it if they have none yet).",
    }
    if target not in SPRITE_EMOTIONS + ["neutral", "background", "look", *hints]:
        return JsonResponse({"error": "Unknown kind of picture."}, status=400)
    hint = hints.get(target, "")
    saved_url = ""
    if target == "ui_background":  # kept in their pictures, so the look can point at it
        ext0 = os.path.splitext(upload.name)[1].lower() or ".png"
        folder, url = user_media_dir(request.user, "backgrounds")
        name = unique_upload_name("look", ext0)
        with open(os.path.join(folder, name), "wb") as f:
            for chunk in upload.chunks():
                f.write(chunk)
        upload.seek(0)
        saved_url = url + name
        hint += f" URL: {saved_url}"
    if target == "appearance" and sprite_mod.clean_name(emotion) and sprite_mod.clean_name(emotion) not in sprite_mod.BUILT_IN:
        # The character with an emotion of their own ("smug", "battle-ready"): one of their extra mood pictures
        character = lore.target_character(session)
        if character is None:
            return JsonResponse({"error": "Make or pick a character first, then add their pictures."}, status=400)
        ext0 = (os.path.splitext(upload.name)[1].lower().lstrip(".") or "png")[:5]
        try:
            sprite_mod.save(character, emotion, upload.read(), ext0)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        mood = sprite_mod.clean_name(emotion)
        upload.seek(0)
        thumb = vision.prepare(upload.read())[1]
        events = [{"type": "picture", "src": thumb, "text": their_words}]
        session.events += events
        note = f"They added a mood picture of {character.name}: “{mood}” (their own mood; the chat shows it when the reply fits)."
        if request.POST.get("quiet") == "1":
            session.messages.append({"role": "user", "content": f"[{note}\n(More pictures follow.)]"})
        else:
            events += agent.run_turn(session, None, action_note=f"Added {character.name}'s “{mood}” picture", model_note=note)
        session.activity = ""
        session.save()
        return JsonResponse({"events": events, "state": _bulba_state(session)})
    if hint:
        target = "look"
    if upload.size > 15 * 1024 * 1024:
        return JsonResponse({"error": "That picture is over 15 MB."}, status=400)
    raw = upload.read()
    try:
        data_url, thumb = vision.prepare(raw)
    except ValueError as e:
        return JsonResponse({"error": str(e)}, status=400)
    character = lore.target_character(session)
    if target != "look" and character is None:
        return JsonResponse({"error": "Make or pick a character first, then add their pictures. (To just show "
                                      "Bulba a picture, pick \"Just show Bulba\".)"}, status=400)
    events = [{"type": "picture", "src": thumb, "text": their_words}]
    seen = ""
    if target in ("look", "neutral", "background"):
        agent.set_activity(session, "Looking at the picture…")
        try:
            seen, who = vision.describe(request.user, data_url, their_words)
            seen = f"What the picture shows (described by {who}, since you can't see it yourself):\n{seen}"
        except ai_client.AIError as e:
            if target == "look":
                session.activity = ""
                session.save(update_fields=["activity"])
                return JsonResponse({"error": f"Couldn't look at the picture: {e}"}, status=400)
            seen = ""
    words = f"\nWhat they said with it: {their_words}" if their_words else ""
    # Several pictures sent together: all but the last are only noted, so Bulba answers once, about all of them
    quiet = request.POST.get("quiet") == "1"
    if target == "look":
        session.events += events
        note = f"They showed you a picture.{words}" + (f"\n{hint}" if hint else "") + f"\n{seen}"
        if quiet:
            session.messages.append({"role": "user", "content": f"[{note}\n(More pictures follow.)]"})
        else:
            events += agent.run_turn(session, None, action_note="You showed Bulba a picture" + (f": {their_words}" if their_words else ""),
                                     model_note=note + "\nHelp with what they want; if it isn't clear, say briefly "
                                                       "what you see and ask.")
        session.activity = ""
        session.save()
        return JsonResponse({"events": events, "state": _bulba_state(session)})
    ext = os.path.splitext(upload.name)[1].lower() or ".png"
    if target == "background":
        folder, url = user_media_dir(request.user, "backgrounds")
        name = unique_upload_name(character.slug, ext)
        with open(os.path.join(folder, name), "wb") as f:
            f.write(raw)
        undo = {"character_id": character.id, "theme": dict(character.theme or {})}
        character.theme = {**(character.theme or {}), "bg": url + name}
        character.save(update_fields=["theme"])
        kind, what = "theme", f"a background for {character.name}'s chats (now their theme)"
    else:
        field = f"photo_{target}"
        undo = {"character_id": character.id, "field": field, "old": getattr(character, field).name or ""}
        getattr(character, field).save(f"{character.slug}-{target}{ext}", ContentFile(raw), save=True)
        kind, what = "picture", f"{character.name}'s {'main' if target == 'neutral' else target} picture"
    p = agent._proposal(session, kind, f"Picture: {what}", ["Added from your upload."], {"character_id": character.id})
    p.update(status="applied", undo=undo)
    events.append({"type": "proposal", "id": p["id"]})
    session.events += events
    note = f"They uploaded {what}; it's set.{words}" + (f"\n{seen}" if seen else "")
    if quiet:
        session.messages.append({"role": "user", "content": f"[{note}\n(More pictures follow.)]"})
    else:
        events += agent.run_turn(session, None, action_note=f"Added {what}", model_note=note)
    session.activity = ""
    session.save()
    return JsonResponse({"events": events, "state": _bulba_state(session)})


def _bulba_card_upload(request):
    from .bulba import agent, lore
    session = _bulba_for_request(request, restart=False)
    if session is None or session.mode != "setup":
        return JsonResponse({"error": "Cards can be imported during setup."}, status=400)
    upload = request.FILES["card"]
    if upload.size > MAX_CARD_BYTES:
        return JsonResponse({"error": "That file is over 20 MB, too big for a character card."}, status=400)
    try:
        character, proposal = lore.import_card(session, upload)
    except cards.CardError as e:
        return JsonResponse({"error": str(e)}, status=400)
    events = [{"type": "proposal", "id": proposal["id"]}]
    session.events += events
    link = _bulba_chat_link(session)
    note = (f"Imported their card: {proposal['title']} — chat: {link['url']}, pictures (Sprites section): "
            f"{link['edit_url']}\n\n{lore.card_report(character)}\n\n{lore.AFTER_NEW_CARD}")
    events += agent.run_turn(session, None, action_note=f"Imported {character.name}", model_note=note)
    session.activity = ""
    session.save()
    return JsonResponse({"events": events, "state": _bulba_state(session)})


MAX_PRESET_BYTES = 5 * 1024 * 1024


def _bulba_preset_upload(request):
    """Their own preset, brought into the setup: saved and made active, then Bulba tailors it (propose_preset_edit)."""
    from .bulba import agent, doctor
    from .models import Preset
    session = _bulba_for_request(request, restart=False)
    if session is None or session.mode != "setup":
        return JsonResponse({"error": "Presets can be brought in during setup (or on the Presets page)."}, status=400)
    upload = request.FILES["preset"]
    if upload.size > MAX_PRESET_BYTES:
        return JsonResponse({"error": "That file is over 5 MB, too big for a preset."}, status=400)
    try:
        preset, suggested = presets.from_any(json.loads(upload.read().decode("utf-8-sig")))
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError) as e:
        return JsonResponse({"error": f"That file isn't a preset this app can read: {e}"}, status=400)
    name = suggested or upload.name.rsplit(".", 1)[0] or "My preset"
    from . import mature
    obj = Preset.objects.create(user=request.user, data=mature.keep(request.user, preset),
                                name=presets.unique_name(request.user, name))
    presets.activate(obj)
    events = [{"type": "action", "text": f"Imported your preset: {obj.name}"}]
    session.events += events
    normalized = presets.normalize(obj.data)
    note = (f"Imported their own preset “{obj.name}”; it's saved and active now. Outline:\n"
            f"{doctor._preset_outline(normalized)}\n\nDon't replace it with a starter (no propose_preset). Read the "
            "blocks that matter (read_block), tell them in two or three lines what it does well and anything that "
            "fights what they told you (or their model's known habits), and offer to tailor it with "
            "propose_preset_edit: their taste, their length, the habits they hate. Small changes; they can say no.")
    events += agent.run_turn(session, None, action_note=f"Imported {obj.name}", model_note=note)
    session.activity = ""
    session.save()
    return JsonResponse({"events": events, "state": _bulba_state(session)})


@login_required
def bulba_transcript(request):
    """The current Bulba conversation as a JSON file, to share when something behaves oddly. No keys."""
    from .bulba import agent
    from .models import BulbaSession
    filters = {"mode": "chat", "chat_id": request.GET["chat"]} if request.GET.get("chat") else {"mode": "setup"}
    session = BulbaSession.objects.filter(user=request.user, active=True, **filters).first()
    if session is None:
        return HttpResponseNotFound("No Bulba conversation yet.")
    if session.mode == "chat":
        from .bulba import doctor
        system = doctor.system_prompt(session)
    else:
        system = agent.system_prompt(session)
    data = {
        "format": "narrativeai-bulba-transcript", "exported": datetime.now().isoformat(timespec="seconds"),
        "mode": session.mode, "target_model": session.target_model, "stage": session.stage,
        "spent_usd": round(session.spent, 4), "budget_usd": session.budget,
        "events": session.events, "preferences": session.preferences, "proposals": session.proposals,
        "messages": session.messages, "system_prompt": system,
    }
    response = HttpResponse(json.dumps(data, ensure_ascii=False, indent=2), content_type="application/json")
    response["Content-Disposition"] = f'attachment; filename="bulba-{session.id}-{datetime.now():%Y%m%d-%H%M}.json"'
    return response


# ---------------------------------------------------------------------------
# Digital Screen Hub & Telegram Messenger (Phase F)
# ---------------------------------------------------------------------------

def _user_characters(user):
    from django.db.models import Q
    return list(Character.objects.filter(Q(author=user) | Q(is_default=True)).distinct().order_by("-time_create"))


@login_required
def screen_hub(request):
    """The Digital Screen Hub: launches with Telegram Messenger as the main app, plus Moments & Notes."""
    from . import messenger
    from .models import MessengerThread
    messenger.use_browser_time_zone(request)

    chars = _user_characters(request.user)
    char_by_slug = {c.slug: c for c in chars}

    wanted_slug = request.GET.get("char") or ""
    wanted_thread_id = request.GET.get("thread") or ""
    active_thread = None

    if wanted_thread_id and str(wanted_thread_id).isdigit():
        active_thread = MessengerThread.objects.filter(user=request.user, id=int(wanted_thread_id)).first()
    if active_thread is None and wanted_slug and wanted_slug in char_by_slug:
        active_thread = messenger.ensure_thread_for_character(request.user, char_by_slug[wanted_slug])

    threads = list(MessengerThread.objects.filter(user=request.user).prefetch_related("characters"))
    if not threads and chars:
        first_thread = messenger.ensure_thread_for_character(request.user, chars[0])
        threads = [first_thread]
    if active_thread is None and threads:
        active_thread = threads[0]

    if active_thread is not None:
        t_data = messenger.thread_data(active_thread)
        if t_data.get("unread") and (request.GET.get("app") == "messenger" or wanted_slug or wanted_thread_id):
            t_data["unread"] = 0
            messenger.save_thread_data(active_thread, t_data)

    serialized_threads = [messenger.serialize_thread_summary(t) for t in threads]
    serialized_active = messenger.serialize_thread_full(active_thread, request.user) if active_thread else None

    from . import subtext, vn_scenes
    char_catalog = []
    for c in chars:
        prof = messenger.char_profile(c)
        char_catalog.append({
            "slug": c.slug,
            "name": c.name,
            "edit_url": reverse("character", kwargs={"slug": c.slug}),
            "chat_url": reverse("chat", kwargs={"slug": c.slug}),
            "burner_handle": subtext.burner_handle_for(c),
            **prof,
        })

    initial_state = {
        "account_id": request.user.pk,
        "threads": serialized_threads,
        "active_thread": serialized_active,
        "characters": char_catalog,
        "user_profile": messenger.user_profile(request.user),
        "persona_photo": request.user.persona_photo_neutral.url if request.user.persona_photo_neutral else "",
        "wallpapers": messenger.WALLPAPERS,
        "reactions": messenger.REACTIONS,
        "built_in_stickers": messenger.BUILT_IN_STICKERS,
        "voices": voice.list_voices_for_user(request.user),
        "tts_models": list(voice.OPENROUTER_TTS_MODELS),
        "active_model": messenger.active_model_texting_rules(request.user),
        "subtext": subtext.get_subtext_state(request.user, chars),
        "vn_scenes": {
            **vn_scenes.get_vn_state(request.user),
            "looks": vn_scenes.looks_payload(request.user, vn_scenes.get_vn_state(request.user)["active_scene"] or {}),
            "look_packs": vn_scenes.look_packs(request.user, vn_scenes.get_vn_state(request.user)["active_scene"]),
            "watch_on": messenger._watch_on(request.user),
            "cost": vn_scenes.episode_cost(request.user, (vn_scenes.get_vn_state(request.user)["active_scene"] or {}).get("cost_since")
                                           or vn_scenes.get_vn_state(request.user).get("prep_since")),
            "music_tracks": vn_scenes.available_music_tracks(chars),
            "backgrounds": vn_scenes.available_backgrounds(chars, request.user),
            "meetup_cue": vn_scenes.detect_meetup_cue(active_thread) if active_thread else {"ready": False, "reason": ""},
        },
    }
    return render(request, "mainapp/messenger.html", {
        "initial_json": json.dumps(initial_state, ensure_ascii=False),
        "has_characters": bool(chars),
    })


@login_required
def messenger_api(request):
    """JSON & multipart endpoint for the Digital Screen Hub and Telegram Messenger."""
    import time
    from django.utils import timezone
    from . import messenger
    from .models import MessengerThread
    messenger.use_browser_time_zone(request)  # 🌍 the browser's time zone, not the server's UTC

    if request.method == "GET":
        action = request.GET.get("action") or "poll"
        if action == "poll":
            from . import pulse
            pulse.deliver_due(user=request.user, limit=100)
            u_prof = messenger.user_profile(request.user)
            threads = list(MessengerThread.objects.filter(user=request.user).prefetch_related("characters"))
            # Optional spontaneous check-in when enabled and user is on another page
            spawned = None
            if u_prof.get("spontaneous_texts") and threads and request.GET.get("allow_spontaneous") == "1":
                now_ts = time.time()
                cooldown_sec = max(120, int(u_prof.get("spontaneous_minutes") or 15) * 60)
                for t in threads:
                    td = messenger.thread_data(t)
                    msgs = td.get("messages") or []
                    last_ts = messenger.ts_of(msgs[-1]) if msgs else 0
                    last_auto = td.get("last_auto_at") or 0
                    # one check-in per silence: not again until the user has answered the last one
                    unanswered = msgs and msgs[-1].get("role") != "user" and last_auto and float(last_auto) >= \
                        next((messenger.ts_of(m) for m in reversed(msgs) if m.get("role") == "user"), 0)
                    if unanswered or messenger.waiting_reply(td):
                        continue
                    if last_ts and (now_ts - float(last_ts) >= cooldown_sec) and (now_ts - float(last_auto) >= cooldown_sec):
                        try:
                            res = messenger.generate_turn(request.user, t, auto_check_in=True)
                            if res.get("bubbles"):
                                b = res["bubbles"][-1]
                                spawned = {
                                    "thread_id": t.id,
                                    "sender_name": b.get("sender_name") or t.title,
                                    "text": (b.get("text") or "Sent a message")[:140],
                                    "id": b.get("id"),
                                }
                        except Exception:
                            pass
                        break

            # ⏰ reminders that are due: the character texts about them (one chat per poll)
            for t in threads:
                try:
                    if messenger.due_events(messenger.thread_data(t)) and messenger.send_reminders(request.user, t):
                        break
                except Exception as e:
                    log.info("messenger: reminder failed: %s", e)

            # ✨ now and then a character posts a status of their own (one per poll at most)
            if u_prof.get("auto_statuses", True) and threads:
                for t in threads:
                    for c in t.characters.all():
                        from django.core.cache import cache
                        if messenger.is_set_up(c) and messenger.status_due(c) and cache.add(f"tg-status-try:{c.id}", 1, 3600):
                            try:
                                messenger.post_own_status(request.user, c, thread=t)
                            except Exception as e:
                                log.info("messenger: no status from %s: %s", c.name, e)
                            break
                    else:
                        continue
                    break

            total_unread = 0
            latest_unread = spawned
            for t in threads:
                td = messenger.thread_data(t)
                u_cnt = int(td.get("unread") or 0)
                total_unread += u_cnt
                if u_cnt > 0 and latest_unread is None and td.get("messages"):
                    last_m = td["messages"][-1]
                    latest_unread = {
                        "thread_id": t.id,
                        "sender_name": last_m.get("sender_name") or t.title,
                        "text": (last_m.get("text") or "New message")[:140],
                        "id": last_m.get("id"),
                    }
            return JsonResponse({
                "total_unread": total_unread,
                "latest_unread": latest_unread,
                "in_app_toasts": u_prof.get("in_app_toasts", True),
                "browser_notifications": u_prof.get("browser_notifications", False),
                "active_model": messenger.active_model_texting_rules(request.user),
            })
        return JsonResponse({"error": "Unknown GET action."}, status=400)

    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    # Multipart media upload (image, file, voice recording, custom sticker, neutral ref, or extra ref)
    if request.content_type and request.content_type.startswith("multipart/form-data"):
        kind = request.POST.get("kind") or "image"
        upload = request.FILES.get("file")
        if not upload:
            return JsonResponse({"error": "No file attached."}, status=400)
        if upload.size > 15 * 1024 * 1024:
            return JsonResponse({"error": "File is over 15 MB."}, status=400)
        ext = "." + upload.name.rsplit(".", 1)[-1].lower()[:8] if "." in upload.name else ".bin"
        ext = re.sub(r"[^.a-z0-9]", "", ext) or ".bin"
        raw_bytes = upload.read()
        rel_path = f"messenger/uploads/{request.user.id}-{uuid.uuid4().hex[:10]}{ext}"
        saved = default_storage.save(rel_path, ContentFile(raw_bytes))
        url = default_storage.url(saved)

        if kind == "sticker":
            u_prof = messenger.user_profile(request.user)
            stickers = list(u_prof.get("custom_stickers") or [])
            st_item = {
                "id": f"custom_{uuid.uuid4().hex[:8]}",
                "pack": "My Stickers",
                "name": (request.POST.get("name") or upload.name.rsplit(".", 1)[0] or "Sticker")[:40],
                "url": url,
            }
            stickers.append(st_item)
            messenger.save_user_profile(request.user, {"custom_stickers": stickers})
            return JsonResponse({"sticker": st_item, "url": url})

        if kind == "group_avatar":  # 🖼️ a group chat's own picture, uploaded by the user
            thread = MessengerThread.objects.filter(user=request.user, id=request.POST.get("thread_id") or 0, is_group=True).first()
            if not thread:
                return JsonResponse({"error": "Group chat not found."}, status=404)
            raw = dict(thread.data or {})
            raw["group_avatar"], raw["group_avatar_changed"] = url, time.time()
            thread.data = raw
            thread.save(update_fields=["data"])
            return JsonResponse({"thread": messenger.serialize_thread_full(thread, request.user)})

        if kind == "char_avatar":  # 🖼️ their profile picture, uploaded by the user
            c_obj = next((c for c in _user_characters(request.user) if c.slug == (request.POST.get("char_slug") or "")), None)
            if not c_obj:
                return JsonResponse({"error": "Character not found."}, status=404)
            return JsonResponse({"profile": messenger.save_char_profile(c_obj, {"avatar_url": url}), "char_slug": c_obj.slug})

        if kind in ("char_neutral", "char_extra_ref"):
            slug = request.POST.get("char_slug") or ""
            chars = _user_characters(request.user)
            c_obj = next((c for c in chars if c.slug == slug), None)
            if not c_obj:
                return JsonResponse({"error": "Character not found."}, status=404)
            c_prof = messenger.char_profile(c_obj)
            if kind == "char_neutral":
                updates = {"neutral_url": url}
                if not c_prof.get("avatar_url"):
                    updates["avatar_url"] = url
                if not getattr(c_obj, "photo_neutral", None) or not c_obj.photo_neutral:
                    c_obj.photo_neutral.name = saved
                    c_obj.save(update_fields=["photo_neutral"])
                updated = messenger.save_char_profile(c_obj, updates)
            else:
                extra = list(c_prof.get("extra_refs") or [])
                slot = request.POST.get("slot")
                if slot is not None and str(slot).isdigit() and int(slot) < len(extra):
                    extra[int(slot)] = url
                elif len(extra) < 4:
                    extra.append(url)
                else:
                    extra[-1] = url
                updated = messenger.save_char_profile(c_obj, {"extra_refs": extra[:4]})
            return JsonResponse({"url": url, "profile": updated, "char_slug": c_obj.slug})

        if kind == "voice_rec":  # 🎤 a recorded voice note: its words, for the character to read
            fmt = "m4a" if ("mp4" in (upload.content_type or "") or ext in (".m4a", ".mp4")) else \
                  "ogg" if ext == ".ogg" else "mp3" if ext == ".mp3" else "wav" if ext == ".wav" else "webm"
            try:
                words = voice.transcribe(request.user, raw_bytes, fmt)
            except voice.VoiceError as e:
                return JsonResponse({"error": str(e), "url": url}, status=400)
            return JsonResponse({"url": url, "transcript": words})

        text_preview = ""
        if kind == "file":
            try:
                text_preview = raw_bytes.decode("utf-8", errors="replace")[:20000]
            except Exception:
                text_preview = ""
        return JsonResponse({
            "url": url,
            "name": upload.name[:80],
            "size": f"{max(1, len(raw_bytes) // 1024)} KB" if len(raw_bytes) >= 1024 else f"{len(raw_bytes)} B",
            "content": text_preview,
        })

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    action = body.get("action") or ""
    chars = _user_characters(request.user)
    char_by_slug = {c.slug: c for c in chars}

    if action == "load_thread":
        tid = body.get("thread_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        if td.get("unread"):
            td["unread"] = 0
            messenger.save_thread_data(thread, td)
        return JsonResponse({"thread": messenger.serialize_thread_full(thread, request.user)})

    if action == "create_thread":
        slugs = body.get("character_slugs") or []
        if isinstance(slugs, str):
            slugs = [slugs]
        picked = [char_by_slug[s] for s in slugs if s in char_by_slug]
        if not picked:
            return JsonResponse({"error": "Pick at least one character."}, status=400)
        is_group = bool(body.get("is_group")) or len(picked) > 1
        if not is_group and len(picked) == 1 and not body.get("force_new"):
            thread = messenger.ensure_thread_for_character(request.user, picked[0])
        else:
            thread = messenger.create_thread(
                request.user,
                picked,
                title=str(body.get("title") or "").strip(),
                is_group=is_group,
                scenario_override=str(body.get("scenario_override") or "").strip(),
            )
        all_threads = [
            messenger.serialize_thread_summary(t)
            for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")
        ]
        return JsonResponse({
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": all_threads,
        })

    if action == "create_char_bulba":
        idea = str(body.get("idea") or "").strip()
        name = str(body.get("name") or "").strip()
        mode = body.get("mode") if body.get("mode") in ("canon", "modern_au") else "modern_au"
        gen_pics = bool(body.get("generate_pics", False))
        try:
            new_char = messenger.create_messenger_character_with_bulba(
                request.user,
                idea=idea,
                name=name,
                mode=mode,
                generate_pics=gen_pics,
            )
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        thread = messenger.ensure_thread_for_character(request.user, new_char)
        c_prof = messenger.char_profile(new_char)
        new_char_entry = {
            "slug": new_char.slug,
            "name": new_char.name,
            "edit_url": reverse("character", kwargs={"slug": new_char.slug}),
            "chat_url": reverse("chat", kwargs={"slug": new_char.slug}),
            **c_prof,
        }
        all_threads = [
            messenger.serialize_thread_summary(t)
            for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")
        ]
        return JsonResponse({
            "character": new_char_entry,
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": all_threads,
        })

    if action == "generate_char_refs":
        slug = body.get("char_slug") or ""
        c_obj = char_by_slug.get(slug)
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        # Save any unsaved appearance/art_style notes passed along with the request first
        if isinstance(body.get("profile"), dict):
            messenger.save_char_profile(c_obj, body["profile"])
        count = max(1, min(5, int(body.get("count") or 2)))
        try:
            updated_prof, cost = messenger.generate_character_references_from_description(request.user, c_obj, count=count)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"profile": updated_prof, "char_slug": c_obj.slug, "cost": cost})

    if action == "preview_voice":
        vid = str(body.get("voice_id") or "sarah").strip()
        v_model = str(body.get("voice_model") or "").strip() or None
        sample = str(body.get("text") or "").strip()
        # Check if the voice already has a direct static preview URL from ElevenLabs
        all_v = voice.list_voices_for_user(request.user)
        matched = next((v for v in all_v if v["id"].lower() == vid.lower() and v.get("preview")), None)
        if matched and matched.get("preview") and not sample:
            return JsonResponse({"audio_url": matched["preview"], "cached": True})
        try:
            audio_url = messenger.preview_voice(request.user, voice_id=vid, sample_text=sample, model=v_model)
        except voice.VoiceError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"audio_url": audio_url})

    if action == "delete_thread":
        tid = body.get("thread_id")
        MessengerThread.objects.filter(user=request.user, id=tid).delete()
        remaining = list(MessengerThread.objects.filter(user=request.user).prefetch_related("characters"))
        return JsonResponse({
            "threads": [messenger.serialize_thread_summary(t) for t in remaining],
            "active_thread": messenger.serialize_thread_full(remaining[0], request.user) if remaining else None,
        })

    if action == "pin_thread":
        tid = body.get("thread_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        thread.pinned = not thread.pinned
        thread.save(update_fields=["pinned", "updated"])
        all_threads = [
            messenger.serialize_thread_summary(t)
            for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")
        ]
        return JsonResponse({"pinned": thread.pinned, "threads": all_threads})

    if action == "send_user_message":
        tid = body.get("thread_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        u_prof = messenger.user_profile(request.user)
        text = str(body.get("text") or "").strip()[:4000]
        sticker = body.get("sticker") if isinstance(body.get("sticker"), dict) else None
        file_obj = body.get("file") if isinstance(body.get("file"), dict) else None
        photo_obj = body.get("photo") if isinstance(body.get("photo"), dict) else None
        voice_obj = body.get("voice") if isinstance(body.get("voice"), dict) else None
        if not (text or sticker or file_obj or photo_obj or voice_obj):
            return JsonResponse({"error": "Write a message or attach something first."}, status=400)

        now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
        msg = {
            "id": uuid.uuid4().hex[:10],
            "role": "user",
            "sender_name": u_prof["display_name"],
            "text": text,
            "time": now_hm,
            "ts": time.time(),
            "reactions": {},
        }
        reply_to_id = body.get("reply_to_id")
        if reply_to_id:
            target_m = next((m for m in td["messages"] if m.get("id") == reply_to_id), None)
            if target_m:
                msg["reply_to_id"] = reply_to_id
                msg["reply_to_sender"] = target_m.get("sender_name") or "Message"
                msg["reply_to_text"] = (target_m.get("text") or "Media")[:120]
        if sticker:
            msg["sticker"] = messenger.see_sticker(request.user, sticker)
        if file_obj:
            msg["file"] = file_obj
        if photo_obj:
            photo_obj = dict(photo_obj)
            if photo_obj.get("kind") == "upload" and photo_obj.get("url") and not photo_obj.get("seen"):
                photo_obj["seen"] = messenger.see_photo(request.user, photo_obj["url"], photo_obj.get("caption") or "")
            msg["photo"] = photo_obj
        if voice_obj:
            msg["voice"] = voice_obj

        td["messages"].append(msg)
        td["unread"] = 0
        messenger.save_thread_data(thread, td)

        if body.get("generate"):
            try:
                turn = messenger.generate_turn(request.user, thread, extra_instruction=str(body.get("instruction") or ""))
            except ai_client.AIError as e:
                return JsonResponse({"user_message": msg, "error": str(e)}, status=400)
            return JsonResponse({
                "user_message": msg,
                "turn": turn,
                "thread": messenger.serialize_thread_full(thread, request.user),
            })
        return JsonResponse({"user_message": msg, "thread": messenger.serialize_thread_full(thread, request.user)})

    if action == "generate_reply":
        tid = body.get("thread_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            turn = messenger.generate_turn(request.user, thread, extra_instruction=str(body.get("instruction") or ""))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        all_threads = [
            messenger.serialize_thread_summary(t)
            for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")
        ]
        return JsonResponse({
            "turn": turn,
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": all_threads,
        })

    if action == "group_scenario":  # 🥔 a group chat's shared scenario, written by Bulba
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            messenger.group_scenario(request.user, thread, hint=str(body.get("hint") or ""))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": [messenger.serialize_thread_summary(t)
                        for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")],
        })

    if action == "split_card":  # ✂️ a card with several people → one character each, and a group chat
        c_obj = char_by_slug.get(body.get("char_slug") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            thread = messenger.split_card(request.user, c_obj)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": [messenger.serialize_thread_summary(t)
                        for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")],
        })

    if action in ("new_chat", "branch_chat", "rename_chat"):  # 💬 chat files
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            if action == "new_chat":
                thread = messenger.new_chat_like(request.user, thread)
            elif action == "branch_chat":
                thread = messenger.branch_chat(request.user, thread, body.get("message_id"))
            else:
                thread.title = str(body.get("title") or "").strip()[:200] or thread.title
                thread.save(update_fields=["title", "updated"])
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": [messenger.serialize_thread_summary(t)
                        for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")],
        })

    if action == "redo_message":  # ↻ one of their messages again (text or voice note), with an optional note
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            message = messenger.redo_message(request.user, thread, body.get("message_id"), note=str(body.get("note") or ""))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"message": message, "thread": messenger.serialize_thread_full(thread, request.user)})

    if action == "regenerate":  # ↻ the characters' last reply again, with an optional note from the user
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            turn = messenger.regenerate_turn(request.user, thread, note=str(body.get("note") or ""))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "turn": turn,
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": [messenger.serialize_thread_summary(t)
                        for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")],
        })

    if action == "react":
        tid = body.get("thread_id")
        mid = body.get("message_id")
        emoji = str(body.get("emoji") or "❤️").strip()[:8]
        thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        target_m = next((m for m in td["messages"] if m.get("id") == mid), None)
        if not target_m:
            return JsonResponse({"error": "Message not found."}, status=404)
        reacts = dict(target_m.get("reactions") or {})
        who = list(reacts.get(emoji) or [])
        if "You" in who:
            who.remove("You")
        else:
            who.append("You")
        if who:
            reacts[emoji] = who
        else:
            reacts.pop(emoji, None)
        target_m["reactions"] = reacts
        messenger.save_thread_data(thread, td)
        return JsonResponse({"message_id": mid, "reactions": reacts})

    if action == "group_avatar":  # 🖼️ a group's picture: made from the members' pictures, or back to their two
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id") or 0, is_group=True).first()
        if not thread:
            return JsonResponse({"error": "Group chat not found."}, status=404)
        if body.get("clear"):
            raw = dict(thread.data or {})
            raw["group_avatar"] = ""
            thread.data = raw
            thread.save(update_fields=["data"])
        else:
            try:
                messenger.new_group_avatar(request.user, thread, str(body.get("what") or "all of them together, at ease").strip()[:400])
            except ai_client.AIError as e:
                return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"thread": messenger.serialize_thread_full(thread, request.user)})

    if action == "edit_message":
        tid = body.get("thread_id")
        mid = body.get("message_id")
        new_text = str(body.get("text") or "").strip()[:4000]
        thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
        if not thread or not new_text:
            return JsonResponse({"error": "Invalid edit."}, status=400)
        td = messenger.thread_data(thread)
        target_m = next((m for m in td["messages"] if m.get("id") == mid), None)
        if not target_m:
            return JsonResponse({"error": "Message not found."}, status=404)
        if target_m.get("role") == "user" and "edited_from" not in target_m:
            # what they first said: the characters know it only if they'd already answered it (they read it then);
            # an edit before anyone answered is just the message
            i = td["messages"].index(target_m)
            if any(m.get("role") == "assistant" for m in td["messages"][i + 1:]):
                target_m["edited_from"] = target_m.get("text") or ""
        target_m["text"] = new_text
        target_m["edited"] = True
        messenger.touch_memory(td, mid)
        if target_m.get("voice"):
            target_m["voice"]["transcript"] = new_text
        messenger.save_thread_data(thread, td)
        return JsonResponse({"message": target_m})

    if action == "delete_message":
        tid = body.get("thread_id")
        mid = body.get("message_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        messenger.touch_memory(td, mid, removed=True)
        td["messages"] = [m for m in td["messages"] if m.get("id") != mid]
        if td.get("pinned_id") == mid:
            td["pinned_id"] = None
        messenger.save_thread_data(thread, td)
        messenger.relock_clock(thread)  # 🕰️ a clock locked to the last message follows the new last one
        return JsonResponse({"deleted": mid, "pinned_id": td["pinned_id"]})

    if action == "pin_message":
        tid = body.get("thread_id")
        mid = body.get("message_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        td["pinned_id"] = None if td.get("pinned_id") == mid else mid
        messenger.save_thread_data(thread, td)
        return JsonResponse({"pinned_id": td["pinned_id"]})

    if action == "thread_settings":
        tid = body.get("thread_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        if "bg" in body and body["bg"] in messenger.WALLPAPERS:
            td["bg"] = body["bg"]
        if "custom_bg_url" in body:
            td["custom_bg_url"] = str(body.get("custom_bg_url") or "").strip()[:500]
        if "scenario_override" in body:
            td["scenario_override"] = str(body.get("scenario_override") or "").strip()[:3000]
        if "share_memory" in body:
            td["share_memory"] = bool(body["share_memory"])
        if "leave_on_read" in body:  # 🙈 per chat: they may answer up to 5 minutes later, when it fits
            td["leave_on_read"] = bool(body["leave_on_read"])
        if body.get("group_mode") in messenger.GROUP_MODES:  # 👥 conversation or lively
            td["group_mode"] = body["group_mode"]
        if isinstance(body.get("persona"), dict):  # 🎭 who they are in this chat ({} = their usual persona)
            td["persona"] = {k: str(body["persona"].get(k) or "").strip() for k in ("name", "description")}
        if body.get("clock"):  # 🕰️ the chat's own clock (real, resume, or a date and time)
            try:
                td["clock_offset"] = messenger.set_clock(thread, body["clock"])
                td["clock_mode"] = messenger.thread_data(thread)["clock_mode"]
            except ValueError:
                return JsonResponse({"error": "That isn't a date and time."}, status=400)
        if isinstance(body.get("linked"), list):  # 🔗 other chats this one remembers (only their own)
            mine = set(MessengerThread.objects.filter(user=request.user).values_list("id", flat=True))
            td["linked"] = [int(x) for x in body["linked"] if str(x).isdigit() and int(x) in mine and int(x) != thread.id][:messenger.LINKED_MAX]
        if isinstance(body.get("scene"), dict):  # 📍 "Right now", edited by hand
            td["scene"] = messenger.clean_scene(body["scene"])
        if isinstance(body.get("places"), dict):
            td["places"] = messenger.clean_places(body["places"])
        if "photo_mood" in body and body["photo_mood"] in messenger.PHOTO_MOODS:  # 📸 how far tease photos go
            td["photo_mood"] = body["photo_mood"]
        if "theme" in body and (body["theme"] in messenger.THEMES or not body["theme"]):  # 🎨 a ready theme
            td["theme"] = body["theme"] or ""
        if "memory" in body:  # 🧠 the chat's memory, edited by hand
            td["memory"] = str(body.get("memory") or "").strip()[:6000]
        if body.get("context_size") in messenger.CONTEXT_SIZES:
            td["context_size"] = body["context_size"]
        if body.get("started"):  # 🧭 the "Before you start" card was answered
            td["started"] = True
        if isinstance(body.get("events"), list):
            td["events"] = [e for e in body["events"] if isinstance(e, dict)][:30]
            messenger.tidy_events(td, by="you")
        if "title" in body and str(body["title"]).strip():
            thread.title = str(body["title"]).strip()[:200]
            thread.save(update_fields=["title"])
        if isinstance(body.get("character_slugs"), list):
            picked = [char_by_slug[s] for s in body["character_slugs"] if s in char_by_slug]
            if picked:
                thread.characters.set(picked)
                thread.is_group = len(picked) > 1 or thread.is_group
                thread.save(update_fields=["is_group"])
        messenger.save_thread_data(thread, td)
        return JsonResponse({"thread": messenger.serialize_thread_full(thread, request.user)})

    if action == "char_profile":
        slug = body.get("char_slug") or ""
        c_obj = char_by_slug.get(slug)
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        old_prof = messenger.char_profile(c_obj)
        saved = messenger.save_char_profile(c_obj, body.get("profile") or {})
        # If bio changed and a thread_id was provided, add a system notice in chat
        tid = body.get("thread_id")
        if tid and saved.get("bio") != old_prof.get("bio") and saved.get("bio"):
            thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
            if thread:
                td = messenger.thread_data(thread)
                td["messages"].append({
                    "id": uuid.uuid4().hex[:10],
                    "role": "system",
                    "text": f"{saved['display_name']} updated their bio: \"{saved['bio']}\"",
                    "time": timezone.localtime(timezone.now()).strftime("%H:%M"),
                    "ts": time.time(),
                })
                messenger.save_thread_data(thread, td)
        return JsonResponse({"profile": saved, "char_slug": c_obj.slug})

    if action == "setup_look":  # 🥔 Bulba's setup, step two: draw them again for this texting setup
        c_obj = char_by_slug.get(body.get("char_slug") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            prof, cost = messenger.redraw_setup_look(request.user, c_obj, outfit=str(body.get("outfit") or ""))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"profile": prof, "char_slug": c_obj.slug, "cost": cost})

    if action == "modernize_bulba":
        slug = body.get("char_slug") or ""
        c_obj = char_by_slug.get(slug)
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        mode = body.get("mode") if body.get("mode") in ("canon", "modern_au") else "modern_au"
        hint = str(body.get("hint") or "").strip()
        save_now = body.get("save", True) is not False
        try:
            draft = messenger.modernize_with_bulba(request.user, c_obj, mode=mode, hint=hint, save=save_now)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"profile": draft, "char_slug": c_obj.slug})

    if action == "user_profile":
        old_u = messenger.user_profile(request.user)
        saved_u = messenger.save_user_profile(request.user, body.get("profile") or {})
        tid = body.get("thread_id")
        if tid and saved_u.get("bio") != old_u.get("bio") and saved_u.get("bio"):
            thread = MessengerThread.objects.filter(user=request.user, id=tid).first()
            if thread:
                td = messenger.thread_data(thread)
                td["messages"].append({
                    "id": uuid.uuid4().hex[:10],
                    "role": "system",
                    "text": f"{saved_u['display_name']} updated their bio: \"{saved_u['bio']}\"",
                    "time": timezone.localtime(timezone.now()).strftime("%H:%M"),
                    "ts": time.time(),
                })
                messenger.save_thread_data(thread, td)
        return JsonResponse({"user_profile": saved_u})

    if action == "update_scene":  # 📍 in the background, every few messages
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            return JsonResponse({"scene": messenger.update_scene(request.user, thread)})
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)

    if action == "continuity_check":  # 🧩 in the background, every few replies (Bulba Watch on)
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            note = messenger.continuity_check(request.user, thread)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"note": note})

    if action == "suggest":  # 🥔 ideas when they're stuck: a reply, a photo to send, a photo to ask for
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        what = body.get("what") if body.get("what") in ("reply", "my_picture", "their_picture", "reminders", "status", "bio", "persona") else "reply"
        try:
            ideas = messenger.suggest(request.user, thread, what, body.get("hint") or "")
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"ideas": ideas})

    if action == "setup_ideas":  # 🥔 directions for the first setup step
        c_obj = char_by_slug.get(body.get("char_slug") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            return JsonResponse({"ideas": messenger.setup_ideas(request.user, c_obj, body.get("mode") or "modern_au", body.get("hint") or "")})
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)

    if action == "remove_sticker_pack":  # 🗑 a pack they added (Telegram, or their own) out of their stickers
        pack = str(body.get("pack") or "")
        u_prof = messenger.user_profile(request.user)
        kept = [s for s in u_prof.get("custom_stickers") or [] if (s.get("pack") or "") != pack]
        return JsonResponse({"user_profile": messenger.save_user_profile(request.user, {"custom_stickers": kept})})

    if action == "custom_sticker":  # ✨ a sticker from their own idea
        who = body.get("who") or ""
        try:
            item = messenger.custom_sticker(request.user, body.get("idea"), character=char_by_slug.get(who), of_me=(who == "me"))
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"sticker": item})

    if action in ("make_lore", "save_lore"):  # 📚 the texting worldbook: Bulba writes it, or edited by hand
        c_obj = char_by_slug.get(body.get("char_slug") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            if action == "make_lore":
                messenger.make_texting_lore(request.user, c_obj)
            else:
                messenger.save_char_profile(c_obj, {"lore": body.get("lore") or []})
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"profile": messenger.char_profile(c_obj), "char_slug": c_obj.slug})

    if action == "style_from_pictures":  # 🥔🎨 the art style read from their pictures
        c_obj = char_by_slug.get(body.get("char_slug") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            return JsonResponse({"style": messenger.style_from_pictures(request.user, c_obj)})
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)

    if action == "gallery":  # 🖼️ the photos of every chat
        return JsonResponse({"photos": messenger.gallery(request.user)})

    if action == "delete_story":  # ✨ a status taken down (the user's own or a character's)
        owner, sid = body.get("owner") or "user", str(body.get("story_id") or "")
        if owner == "user":
            u_prof = messenger.user_profile(request.user)
            saved_u = messenger.save_user_profile(request.user, {"stories": [s for s in u_prof.get("stories") or [] if s.get("id") != sid]})
            return JsonResponse({"user_profile": saved_u})
        c_obj = char_by_slug.get(owner)
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        c_prof = messenger.char_profile(c_obj)
        saved_c = messenger.save_char_profile(c_obj, {"stories": [s for s in c_prof.get("stories") or [] if s.get("id") != sid]})
        return JsonResponse({"profile": saved_c, "char_slug": c_obj.slug})

    if action == "post_story":
        owner = body.get("owner") or "user"
        text = str(body.get("text") or "").strip()[:280]
        emoji = str(body.get("emoji") or "✨").strip()[:12]
        image_url = str(body.get("image_url") or "").strip()[:500]
        if not text and not image_url:
            return JsonResponse({"error": "Write a status update first."}, status=400)
        story_item = {
            "id": uuid.uuid4().hex[:8],
            "emoji": emoji,
            "text": text,
            "image_url": image_url,
            "at": timezone.localtime(timezone.now()).strftime("%H:%M"),
            "ts": time.time(),
        }
        if owner == "user":
            u_prof = messenger.user_profile(request.user)
            stories = [story_item, *(u_prof.get("stories") or [])][:30]
            saved_u = messenger.save_user_profile(request.user, {"stories": stories, "status_emoji": emoji})
            return JsonResponse({"story": story_item, "user_profile": saved_u})
        c_obj = char_by_slug.get(owner)
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        c_prof = messenger.char_profile(c_obj)
        stories = [story_item, *(c_prof.get("stories") or [])][:30]
        saved_c = messenger.save_char_profile(c_obj, {"stories": stories, "status_emoji": emoji})
        return JsonResponse({"story": story_item, "profile": saved_c, "char_slug": c_obj.slug})

    if action in ("make_sticker", "telegram_pack"):  # 🎨 a sticker of their pack · 📥 a Telegram pack by link
        try:
            if action == "make_sticker":
                c_obj = char_by_slug.get(body.get("char_slug") or "")
                if not c_obj:
                    return JsonResponse({"error": "Character not found."}, status=404)
                prof = messenger.make_sticker(request.user, c_obj, body.get("mood"))
                return JsonResponse({"profile": prof, "char_slug": c_obj.slug, "stickers": messenger.character_stickers(c_obj)})
            title, added, skipped = messenger.telegram_pack(request.user, body.get("link"))
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"title": title, "added": added, "skipped": skipped,
                             "user_profile": messenger.user_profile(request.user)})

    if action == "translate_message":  # 🌐 one message in the user's reading language
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            text, lang = messenger.translate_message(request.user, thread, body.get("message_id"))
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"message_id": body.get("message_id"), "text": text, "language": lang})

    if action == "update_memory":  # 🧠 the chat's memory brought up to date (quietly after a turn, or "now")
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        try:
            memory = messenger.update_memory(request.user, thread, force=bool(body.get("now")), everything=bool(body.get("all")))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"memory": memory, "thread": messenger.serialize_thread_full(thread, request.user)})

    if action == "one_reference":  # ✨/↻ one reference picture, just this one
        c_obj = char_by_slug.get(body.get("char_slug") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            prof = messenger.one_reference(request.user, c_obj, body.get("slot", -1))
        except (ValueError, TypeError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"profile": prof, "char_slug": c_obj.slug})

    if action == "user_picture":  # 🎨 a picture the user makes to send (made again as often as they like)
        thread = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id")).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        refs = [str(u) for u in (body.get("refs") or []) if isinstance(u, str)][:5]
        try:
            url, seen = messenger.user_picture(request.user, thread, body.get("prompt"), refs, with_me=bool(body.get("with_me", True)))
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"url": url, "seen": seen})

    if action == "answer_story":  # ✨ a reply or a reaction to a character's story, into the chat it came from
        c_obj = char_by_slug.get(body.get("owner") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            thread, new = messenger.answer_story(request.user, c_obj, body.get("story_id"), body.get("text"), body.get("emoji"))
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"thread_id": thread.id, "thread_title": thread.title, "messages": new,
                             "profile": messenger.char_profile(c_obj), "char_slug": c_obj.slug})

    if action == "story_picture":  # 🖼️ a status's picture, made when it's first viewed
        c_obj = char_by_slug.get(body.get("owner") or "")
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        try:
            story = messenger.story_picture(request.user, c_obj, body.get("story_id"))
        except (ValueError, ai_client.AIError) as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"story": story, "char_slug": c_obj.slug, "profile": messenger.char_profile(c_obj)})

    if action == "voice_bubble":
        tid = body.get("thread_id")
        mid = body.get("message_id")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        target_m = next((m for m in td["messages"] if m.get("id") == mid), None)
        if not target_m:
            return JsonResponse({"error": "Message not found."}, status=404)
        c_obj = char_by_slug.get(target_m.get("sender_slug")) or thread.characters.first()
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        transcript = (target_m.get("voice") or {}).get("transcript") or target_m.get("text") or ""
        try:
            audio_url = messenger.synthesize_voice_bubble(request.user, c_obj, transcript)
        except voice.VoiceError as e:
            return JsonResponse({"error": str(e)}, status=400)
        voice_dict = dict(target_m.get("voice") or {})
        voice_dict.update({
            "transcript": transcript,
            "audio_url": audio_url,
            "duration": voice_dict.get("duration") or max(2, min(45, len(transcript.split()) // 2)),
        })
        target_m["voice"] = voice_dict
        messenger.save_thread_data(thread, td)
        return JsonResponse({"message": target_m, "audio_url": audio_url})

    if action == "photo_bubble":
        tid = body.get("thread_id")
        mid = body.get("message_id")
        kind = "tease" if body.get("kind") == "tease" else "casual"
        prompt_desc = str(body.get("prompt") or "").strip()
        if body.get("subject") == "not_them":  # 📷 asked for a photo without them in it
            prompt_desc = "No people: " + (prompt_desc or "something from their day, what they're looking at right now")
        thread = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first()
        if not thread:
            return JsonResponse({"error": "Chat not found."}, status=404)
        td = messenger.thread_data(thread)
        target_m = next((m for m in td["messages"] if m.get("id") == mid), None) if mid else None
        slug = body.get("char_slug") or (target_m.get("sender_slug") if target_m else "")
        c_obj = char_by_slug.get(slug) or thread.characters.first()
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        if target_m and not prompt_desc:
            prompt_desc = (target_m.get("photo") or {}).get("prompt") or target_m.get("text") or ""

        extracted_caption = ""
        if not prompt_desc:
            scene = messenger.describe_photo_scene(request.user, thread, c_obj, kind=kind)
            prompt_desc = scene["visual_prompt"]
            extracted_caption = scene.get("caption") or ""
            shot_type = scene.get("shot_type")
            camera_angle = scene.get("camera_angle") or ""
        else:
            shot_type = None
            camera_angle = ""

        if body.get("subject") == "them":  # 📸 a photo of them, asked for
            shot_type = "selfie"
        try:
            img_url, cost = messenger.generate_messenger_photo(
                request.user,
                c_obj,
                prompt_desc,
                kind=kind,
                thread=thread,
                shot_type=shot_type,
                camera_angle=camera_angle,
                also=(None if not body.get("also") else False if body.get("also") == "none"
                      else char_by_slug.get(body.get("also")) or None),  # 👥 who else is in it (auto in groups)
            )
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)

        seen = messenger.see_photo(request.user, img_url)  # 👁️ what really came out, for the chat to read
        if target_m:
            p_dict = dict(target_m.get("photo") or {})
            p_dict.update({"kind": kind, "prompt": prompt_desc, "url": img_url, "seen": seen})
            target_m["photo"] = p_dict
            messenger.save_thread_data(thread, td)
            return JsonResponse({"message": target_m, "url": img_url, "cost": cost})
        else:
            c_prof = messenger.char_profile(c_obj)
            cap = str(body.get("caption") or extracted_caption or "").strip()
            new_m = {
                "id": uuid.uuid4().hex[:10],
                "role": "assistant",
                "sender_slug": c_obj.slug,
                "sender_name": c_prof["display_name"],
                "text": cap,
                "photo": {"kind": kind, "prompt": prompt_desc, "caption": cap, "url": img_url, "seen": seen},
                "time": timezone.localtime(timezone.now()).strftime("%H:%M"),
                "ts": time.time(),
                "reactions": {},
            }
            td["messages"].append(new_m)
            messenger.save_thread_data(thread, td)
            return JsonResponse({"message": new_m, "url": img_url, "cost": cost})

    return JsonResponse({"error": f"Unknown action '{action}'."}, status=400)


@login_required
def subtext_api(request):
    """JSON endpoint for Subtext / Chirp (Public posts, Locked Burners, AITA threads, and Forward-to-TeleChat DMs)."""
    import time
    from django.utils import timezone
    from . import messenger, subtext
    from .models import MessengerThread

    chars = _user_characters(request.user)
    char_by_slug = {c.slug: c for c in chars}

    if request.method == "GET":
        return JsonResponse({"subtext": subtext.get_subtext_state(request.user, chars)})

    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    action = body.get("action") or ""

    if action == "generate_wave":
        slugs = body.get("character_slugs") or []
        picked = [char_by_slug[s] for s in slugs] or chars[:4]
        mode = body.get("mode") if body.get("mode") in ("mix", "burner", "aita", "subtweet") else "mix"
        topic = str(body.get("topic") or "").strip()
        try:
            new_posts = subtext.generate_wave(request.user, picked, mode=mode, topic_hint=topic)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "new_posts": new_posts,
            "subtext": subtext.get_subtext_state(request.user, chars),
        })

    if action == "create_post":
        text = str(body.get("text") or "").strip()
        if not text:
            return JsonResponse({"error": "Write something to post first."}, status=400)
        vis = body.get("visibility") if body.get("visibility") in ("public", "burner", "aita") else "public"
        title = str(body.get("title") or "").strip()
        ask_replies = bool(body.get("ask_replies", True))
        slugs = body.get("character_slugs") or []
        picked = ([char_by_slug[s] for s in slugs if s in char_by_slug] or chars[:3]) if ask_replies else []
        post = subtext.create_user_post(request.user, text, visibility=vis, title=title, chars_for_replies=picked)
        return JsonResponse({
            "post": post,
            "subtext": subtext.get_subtext_state(request.user, chars),
        })

    if action == "add_comment":
        pid = body.get("post_id")
        text = str(body.get("text") or "").strip()
        if not text:
            return JsonResponse({"error": "Comment cannot be empty."}, status=400)
        state = subtext.get_subtext_state(request.user, chars)
        post = next((p for p in state["posts"] if p.get("id") == pid), None)
        if not post:
            return JsonResponse({"error": "Post not found."}, status=404)
        u_prof = messenger.user_profile(request.user)
        now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
        verdict = str(body.get("verdict") or "").strip().upper()
        if verdict not in ("NTA", "YTA", "ESH"):
            verdict = ""
        if post.get("visibility") == "aita" and verdict:
            votes = post.setdefault("aita_votes", {"nta": 0, "yta": 0, "esh": 0, "user_vote": ""})
            v_key = verdict.lower()
            votes[v_key] = votes.get(v_key, 0) + 1
            votes["user_vote"] = verdict
        user_c = {
            "id": "stc_" + uuid.uuid4().hex[:8],
            "author_slug": "user",
            "author_name": u_prof.get("display_name") or request.user.username,
            "author_avatar": u_prof.get("avatar_url") or "",
            "handle": u_prof.get("handle") or "@you",
            "is_burner": False,
            "verdict": verdict,
            "text": text[:600],
            "time": now_hm,
            "ts": time.time(),
        }
        post.setdefault("comments", []).append(user_c)
        if body.get("ask_replies", True) and chars:
            author_char = char_by_slug.get(post.get("author_slug"))
            reply_pool = [author_char] if author_char else []
            for c in chars:
                if c not in reply_pool and len(reply_pool) < 3:
                    reply_pool.append(c)
            try:
                subtext.generate_replies_for_post(request.user, post, reply_pool)
            except Exception:
                pass
        subtext.save_subtext_state(request.user, {"posts": state["posts"]})
        return JsonResponse({"post": post, "subtext": state})

    if action == "generate_replies":
        pid = body.get("post_id")
        state = subtext.get_subtext_state(request.user, chars)
        post = next((p for p in state["posts"] if p.get("id") == pid), None)
        if not post:
            return JsonResponse({"error": "Post not found."}, status=404)
        slugs = body.get("character_slugs") or []
        picked = [char_by_slug[s] for s in slugs if s in char_by_slug] or chars[:3]
        try:
            added = subtext.generate_replies_for_post(request.user, post, picked)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        subtext.save_subtext_state(request.user, {"posts": state["posts"]})
        return JsonResponse({"post": post, "added_comments": added, "subtext": state})

    if action == "react_post":
        pid = body.get("post_id")
        emo = str(body.get("emoji") or "❤️").strip()[:8]
        state = subtext.get_subtext_state(request.user, chars)
        post = next((p for p in state["posts"] if p.get("id") == pid), None)
        if not post:
            return JsonResponse({"error": "Post not found."}, status=404)
        u_name = messenger.user_profile(request.user).get("display_name") or request.user.username
        reacts = dict(post.get("reactions") or {})
        lst = list(reacts.get(emo) or [])
        if u_name in lst:
            lst.remove(u_name)
        else:
            lst.append(u_name)
        if lst:
            reacts[emo] = lst
        else:
            reacts.pop(emo, None)
        post["reactions"] = reacts
        subtext.save_subtext_state(request.user, {"posts": state["posts"]})
        return JsonResponse({"post": post, "reactions": reacts})

    if action == "vote_aita":
        pid = body.get("post_id")
        verdict = str(body.get("verdict") or "").strip().upper()
        if verdict not in ("NTA", "YTA", "ESH"):
            return JsonResponse({"error": "Invalid verdict."}, status=400)
        state = subtext.get_subtext_state(request.user, chars)
        post = next((p for p in state["posts"] if p.get("id") == pid), None)
        if not post:
            return JsonResponse({"error": "Post not found."}, status=404)
        votes = post.setdefault("aita_votes", {"nta": 0, "yta": 0, "esh": 0, "user_vote": ""})
        prev = votes.get("user_vote") or ""
        if prev and prev.lower() in votes:
            votes[prev.lower()] = max(0, int(votes[prev.lower()]) - 1)
        v_key = verdict.lower()
        votes[v_key] = int(votes.get(v_key) or 0) + 1
        votes["user_vote"] = verdict
        subtext.save_subtext_state(request.user, {"posts": state["posts"]})
        return JsonResponse({"post": post, "aita_votes": votes})

    if action == "generate_photo":
        pid = body.get("post_id")
        state = subtext.get_subtext_state(request.user, chars)
        post = next((p for p in state["posts"] if p.get("id") == pid), None)
        if not post:
            return JsonResponse({"error": "Post not found."}, status=404)
        c_obj = char_by_slug.get(post.get("author_slug")) or (chars[0] if chars else None)
        if not c_obj:
            return JsonResponse({"error": "Character not found."}, status=404)
        p_info = dict(post.get("photo") or {})
        prompt_desc = str(body.get("prompt") or p_info.get("prompt") or post.get("text") or "").strip()
        try:
            img_url, cost = messenger.generate_messenger_photo(request.user, c_obj, description=prompt_desc, kind="casual")
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        p_info["prompt"] = prompt_desc
        p_info["url"] = img_url
        post["photo"] = p_info
        subtext.save_subtext_state(request.user, {"posts": state["posts"]})
        return JsonResponse({"post": post, "url": img_url, "cost": cost})

    if action == "forward_to_telechat":
        pid = body.get("post_id")
        comment = str(body.get("comment") or "").strip()
        state = subtext.get_subtext_state(request.user, chars)
        post = next((p for p in state["posts"] if p.get("id") == pid), None)
        if not post:
            return JsonResponse({"error": "Post not found."}, status=404)
        target_slug = body.get("char_slug") or post.get("author_slug")
        c_obj = char_by_slug.get(target_slug) or (chars[0] if chars else None)
        if not c_obj:
            return JsonResponse({"error": "Pick a character to DM this post to."}, status=400)
        try:
            thread, user_msg, turn = subtext.forward_post_to_telechat(request.user, post, c_obj, user_comment=comment)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        all_threads = [
            messenger.serialize_thread_summary(t)
            for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")
        ]
        return JsonResponse({
            "thread": messenger.serialize_thread_full(thread, request.user),
            "threads": all_threads,
            "user_message": user_msg,
            "turn": turn,
        })

    if action == "delete_post":
        pid = body.get("post_id")
        state = subtext.get_subtext_state(request.user, chars)
        state["posts"] = [p for p in state["posts"] if p.get("id") != pid]
        subtext.save_subtext_state(request.user, {"posts": state["posts"]})
        return JsonResponse({"subtext": state})

    return JsonResponse({"error": f"Unknown subtext action '{action}'."}, status=400)


@login_required
def vn_scenes_api(request):
    """JSON endpoint for Visual Novel Meet-Up Scenes, Dynamic Sprite Generation, and Event CG Gallery."""
    from . import messenger, vn_scenes
    from .models import MessengerThread

    chars = _user_characters(request.user)
    char_by_slug = {c.slug: c for c in chars}

    def _full_vn_payload(active_thread=None):
        st = vn_scenes.get_vn_state(request.user)
        return {
            **st,
            "looks": vn_scenes.looks_payload(request.user, st["active_scene"]) if st.get("active_scene") else {},
            "look_packs": vn_scenes.look_packs(request.user, st.get("active_scene")),
            "watch_on": messenger._watch_on(request.user),
            "cost": vn_scenes.episode_cost(request.user, (st.get("active_scene") or {}).get("cost_since") or st.get("prep_since")),
            "music_tracks": vn_scenes.available_music_tracks(chars),
            "backgrounds": vn_scenes.available_backgrounds(chars, request.user),
            "meetup_cue": vn_scenes.detect_meetup_cue(active_thread) if active_thread else {"ready": False, "reason": ""},
        }

    if request.method == "GET":
        tid = request.GET.get("thread_id")
        t_obj = MessengerThread.objects.filter(user=request.user, id=tid).first() if (tid and str(tid).isdigit()) else None
        return JsonResponse({"vn_scenes": _full_vn_payload(t_obj)})

    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        # The browser's transparent cut-out of one episode-look mood.
        from . import episode_looks
        upload = request.FILES.get("file")
        if request.POST.get("kind") != "episode_cut" or not upload:
            return JsonResponse({"error": "Attach the cut-out picture."}, status=400)
        try:
            look = episode_looks.owned(request.user, request.POST.get("look_id"))
            try:
                changed = float(request.POST.get("body_changed"))
                changed = changed if 0 <= changed <= 1 else None
            except (TypeError, ValueError):
                changed = None
            episode_looks.save_cut(look, request.POST.get("mood") or "", upload.read(), body_changed=changed)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse({"look": episode_looks.pack(look)})

    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    if not isinstance(body, dict):
        return JsonResponse({"error": "Expected a JSON object."}, status=400)
    for field in ("polish_enabled", "capture_image"):
        if field in body and not isinstance(body[field], bool):
            return JsonResponse({"error": f"{field} must be true or false."}, status=400)
    if body.get("thread_id") is not None and (isinstance(body["thread_id"], bool) or not str(body["thread_id"]).isdigit() or len(str(body["thread_id"])) > 19 or not 0 < int(body["thread_id"]) <= 2**63 - 1):
        return JsonResponse({"error": "Invalid chat ID."}, status=400)

    action = body.get("action") or ""

    if action not in ("check_meetup", "start_scene", "delete_gallery_item"):
        active = vn_scenes.get_vn_state(request.user).get("active_scene") or {}
        if body.get("scene_id") and (body["scene_id"] != active.get("id") or
                ("revision" in body and body["revision"] != active.get("revision", 0))):
            return JsonResponse({"error": "This episode changed in another tab. Reload it before continuing."}, status=409)

    if action in ("edit_passage", "regenerate_passage", "branch_passage", "resume_draft", "reopen_completed", "episode_preferences", "suggest_choices", "park_scene", "inspect_request"):
        from . import vn_history, vn_story
        try:
            if action == "park_scene":
                vn_history.park(request.user)
                return JsonResponse({"scene": None, "vn_scenes": _full_vn_payload()})
            if action == "inspect_request":
                _, scene = vn_history.current(request.user)
                return JsonResponse({"request": scene.get("last_request")})
            if action == "suggest_choices":
                scene = vn_scenes.suggest_choices(request.user)
            elif action == "edit_passage":
                scene = vn_history.edit(request.user, str(body.get("beat_id") or ""), str(body.get("text") or ""))
            elif action == "regenerate_passage":
                scene = vn_history.regenerate(request.user, str(body.get("beat_id") or ""), str(body.get("direction") or ""))
            elif action == "branch_passage":
                scene = vn_history.branch(request.user, str(body.get("beat_id") or ""))
            elif action == "resume_draft":
                scene = vn_history.resume(request.user, str(body.get("draft_id") or ""))
            elif action == "reopen_completed":
                scene = vn_history.reopen_completed(request.user, str(body.get("episode_id") or ""))
            else:
                _, scene = vn_history.current(request.user)
                expected = (scene["id"], scene.get("revision", 0))
                previous_mode = scene.get("interaction_mode", "mixed")
                if body.get("interaction_mode") in vn_story.INTERACTIONS:
                    scene["interaction_mode"] = body["interaction_mode"]
                if body.get("authoring_mode") in vn_story.AUTHORING:
                    scene["authoring_mode"] = body["authoring_mode"]
                if "direction" in body:
                    scene["direction"] = str(body["direction"])[:4000]
                if "polish_enabled" in body:
                    scene["polish_enabled"] = bool(body["polish_enabled"])
                if scene.get("interaction_mode") == "write":
                    if previous_mode != "write":
                        scene["choice_cache"] = list(scene.get("choices") or [])
                    scene["choices"] = []
                elif previous_mode == "write":
                    scene["choices"] = list(scene.get("choice_cache") or [])
                vn_scenes.save_vn_state(request.user, {"active_scene": scene}, expected=expected)
        except ai_client.AIError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        linked = MessengerThread.objects.filter(user=request.user, id=scene.get("thread_id")).first()
        return JsonResponse({"scene": scene, "vn_scenes": _full_vn_payload(),
                             "thread": messenger.serialize_thread_full(linked, request.user) if linked else None,
                             "threads": [messenger.serialize_thread_summary(t) for t in MessengerThread.objects.filter(user=request.user)]})

    if action == "check_meetup":
        tid = body.get("thread_id")
        t_obj = MessengerThread.objects.filter(user=request.user, id=tid).first() if tid else None
        return JsonResponse({"meetup_cue": vn_scenes.detect_meetup_cue(t_obj)})

    if action.startswith("episode_look"):
        from . import episode_looks
        from .models import EpisodeLook

        def member(key):
            if key == "user":
                return None
            if key not in char_by_slug:
                raise ValueError("Choose someone from your characters.")
            return char_by_slug[key]
        try:
            if action == "episode_looks":  # who is in the cast, their setting, their looks and the default pick
                slugs = body.get("character_slugs")
                if not isinstance(slugs, list):
                    t_obj = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id") or 0).prefetch_related("characters").first()
                    slugs = [c.slug for c in t_obj.characters.all()] if t_obj else []
                cast = [char_by_slug[s] for s in slugs if isinstance(s, str) and s in char_by_slug]
                people = [(c.slug, c, messenger.char_profile(c)["display_name"], episode_looks.setting_for(c)) for c in cast]
                people.append(("user", None, messenger.user_profile(request.user).get("display_name") or "You",
                               vn_scenes.scene_setting(cast)))
                out = []
                for key, character, name, setting in people:
                    looks = episode_looks.looks_for(request.user, character, setting)
                    out.append({"key": key, "name": name, "setting": setting, "looks": [episode_looks.pack(l) for l in looks],
                                "chosen": looks[0].pk if looks else None,
                                "has_reference": bool(episode_looks.references(request.user, character, setting)[:1])})
                return JsonResponse({"cast": out, "core_moods": episode_looks.CORE_MOODS,
                                     "picture_models": [["", "Nano Banana (Google): the app's default"],
                                                        *[[k, v] for k, v in messenger.PICTURE_MODELS.items()]],
                                     "default_model": episode_looks.picture_model(request.user)})
            if action in ("episode_look_create", "episode_look_moods", "episode_look_redraw") and \
                    not vn_scenes.get_vn_state(request.user).get("active_scene"):
                vn_scenes.mark_prep(request.user)  # looks made while casting count toward the coming episode
            if action == "episode_look_create":
                key = str(body.get("key") or "")
                character = member(key)
                setting = (episode_looks.setting_for(character) if character else
                           ("modern" if body.get("setting") == "modern" else "canon"))
                moods = body.get("moods") if isinstance(body.get("moods"), list) else None
                look, cost, errors = episode_looks.create(request.user, character, setting, body.get("name"),
                                                          body.get("outfit"), moods=moods,
                                                          model=body.get("model") if isinstance(body.get("model"), str) else None)
                return JsonResponse({"look": episode_looks.pack(look), "cost": cost, "errors": errors})
            look = episode_looks.owned(request.user, body.get("look_id"))
            if action == "episode_look_moods":
                moods = [m for m in (body.get("moods") or []) if isinstance(m, str)][:episode_looks.MAX_MOODS]
                cost, errors = episode_looks.add_moods(request.user, look, moods)
                return JsonResponse({"look": episode_looks.pack(look), "cost": cost, "errors": errors})
            if action == "episode_look_remove_mood":
                episode_looks.remove_mood(look, str(body.get("mood") or ""))
                return JsonResponse({"look": episode_looks.pack(look)})
            if action == "episode_look_rename":
                look.name = " ".join(str(body.get("name") or "").split())[:60] or look.name
                look.save(update_fields=["name", "updated"])
                return JsonResponse({"look": episode_looks.pack(look)})
            if action == "episode_look_restyle":
                new, cost, errors = episode_looks.restyle(request.user, look, body.get("name"), body.get("outfit"))
                return JsonResponse({"look": episode_looks.pack(new), "cost": cost, "errors": errors})
            if action == "episode_look_redraw":  # one mood again, or the whole look when mood is "all"
                note = " ".join(str(body.get("note") or "").split())[:500]
                if body.get("mood") == "all":
                    cost, errors = episode_looks.redraw_look(request.user, look, note=note)
                else:
                    cost, errors = episode_looks.redraw_mood(request.user, look, str(body.get("mood") or ""),
                                                             auto=bool(body.get("auto")), note=note), []
                return JsonResponse({"look": episode_looks.pack(look), "cost": cost, "errors": errors})
            if action == "episode_look_note":  # how this person shows a mood (used the next time it's drawn)
                episode_looks.set_mood_note(look, str(body.get("mood") or ""), str(body.get("note") or ""))
                return JsonResponse({"look": episode_looks.pack(look)})
            if action == "episode_look_model":  # the picture model for this look's next drawings
                look.model = episode_looks.picture_model(request.user, str(body.get("model") or ""))
                look.save(update_fields=["model", "updated"])
                return JsonResponse({"look": episode_looks.pack(look)})
            if action == "episode_look_delete":
                episode_looks.delete(look)
                return JsonResponse({"ok": True})
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except ai_client.AIError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse({"error": "Unknown look action."}, status=400)

    if action == "voice_line":  # 🔊 one page read aloud in the speaker's voice (kept, so replays are free)
        try:
            _, url = vn_scenes.voice_line(request.user, str(body.get("beat_id") or ""))
        except ai_client.AIError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse({"url": url, "vn_scenes": _full_vn_payload()})

    if action in ("episode_watch", "watch_dismiss"):  # Bulba's continuity check of the latest turn
        from . import vn_watch
        try:
            if action == "episode_watch":
                vn_watch.run(request.user)
            else:
                vn_watch.dismiss(request.user, str(body.get("beat_id") or ""))
        except ai_client.AIError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse({"vn_scenes": _full_vn_payload()})

    if action in ("casting_propose", "place_draw", "place_delete"):
        from . import vn_casting
        from .models import EpisodePlace
        try:
            if not vn_scenes.get_vn_state(request.user).get("active_scene"):
                vn_scenes.mark_prep(request.user)  # the coming episode's cost counts from its casting
            if action == "casting_propose":  # Bulba's casting sheet for this chat (one call to Bulba's model)
                t_obj = MessengerThread.objects.filter(user=request.user, id=body.get("thread_id") or 0).prefetch_related("characters").first()
                if not t_obj:
                    return JsonResponse({"error": "Open the chat this episode continues first."}, status=400)
                cast = list(t_obj.characters.all())
                pulse_event = None
                if body.get("pulse_event_id") is not None:
                    from . import pulse, screen_apps
                    from .models import ScreenEntry
                    event = ScreenEntry.objects.filter(owner=request.user, thread=t_obj, kind="event",
                                                       pk=screen_apps.positive(body["pulse_event_id"])).first()
                    if event:
                        pulse_event = pulse.scene_seed(request.user, event, screen_apps.positive(body.get("pulse_event_revision")))
                sheet = vn_casting.propose(request.user, t_obj, cast, pulse_event=pulse_event,
                                           wish=str(body.get("wish") or "")[:600], director=body.get("authoring_mode") == "director")
                return JsonResponse({"casting": sheet,
                                     "backgrounds": vn_scenes.available_backgrounds(cast, request.user)})
            if action == "place_draw":  # draw the written-out place once and keep it as a backdrop
                place = body.get("place") if isinstance(body.get("place"), dict) else {}
                place = vn_casting.checked({"place": place}, [], request.user)["place"]
                kept, cost = vn_casting.draw_place(request.user, place, "modern" if body.get("setting") == "modern" else "canon")
                return JsonResponse({"place": vn_casting.pack_place(kept), "cost": cost})
            kept = EpisodePlace.objects.filter(author=request.user, pk=str(body.get("place_id") or "").replace("place_", "") or 0).first()
            if kept:
                from django.core.files.storage import default_storage
                default_storage.delete(kept.image)
                kept.delete()
            return JsonResponse({"ok": True})
        except (ValueError, ai_client.AIError) as exc:
            return JsonResponse({"error": str(exc)}, status=400)

    if action == "start_scene":
        tid = body.get("thread_id")
        t_obj = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first() if tid else None
        if tid and t_obj is None:
            return JsonResponse({"error": "That chat no longer exists or is not yours."}, status=404)
        pulse_event = None
        if body.get("pulse_event_id") is not None:
            from . import pulse, screen_apps
            from .models import ScreenEntry
            try:
                event = ScreenEntry.objects.filter(owner=request.user, thread=t_obj,
                    pk=screen_apps.positive(body["pulse_event_id"]), kind="event").first()
                if not event:
                    return JsonResponse({"error": "Pulse plan not found in this chat."}, status=404)
                pulse_event = pulse.scene_seed(request.user, event, screen_apps.positive(body.get("pulse_event_revision")))
            except ValueError as exc:
                return JsonResponse({"error": str(exc)}, status=400)
        slugs = body.get("character_slugs") or []
        if not isinstance(slugs, list) or any(not isinstance(s, str) or s not in char_by_slug for s in slugs):
            return JsonResponse({"error": "Choose available scene characters."}, status=400)
        picked = [char_by_slug[s] for s in slugs if s in char_by_slug]
        if pulse_event:
            if any(s not in char_by_slug for s in pulse_event["participants"]):
                return JsonResponse({"error": "A plan participant is no longer available."}, status=400)
            picked = [char_by_slug[s] for s in pulse_event["participants"]]
        if not picked and t_obj:
            picked = list(t_obj.characters.all())
        if not picked:
            return JsonResponse({"error": "Pick at least one character for the scene."}, status=400)
        hint = str(body.get("location_hint") or "").strip()
        try:
            scene = vn_scenes.start_scene(
                request.user,
                thread=t_obj,
                characters=picked,
                location_hint=hint,
                looks=body.get("looks") if isinstance(body.get("looks"), dict) else None,
                direction=str(body.get("direction") or "").strip()[:4000],
                polish_enabled=bool(body.get("polish_enabled", False)),
                interaction_mode=body.get("interaction_mode", "mixed"),
                authoring_mode=body.get("authoring_mode", "roleplay"),
                pulse_event=pulse_event,
                generate_background=bool(body.get("generate_background", False)),
                casting=body.get("casting") if isinstance(body.get("casting"), dict) else None,
            )
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "scene": scene,
            "looks": vn_scenes.looks_payload(request.user, scene),
            "vn_scenes": _full_vn_payload(t_obj),
        })

    if action == "step_scene":
        user_input = str(body.get("user_input") or "").strip()
        try:
            scene, new_beats = vn_scenes.step_scene(request.user, user_input=user_input)
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({
            "scene": scene,
            "new_beats": new_beats,
            "looks": vn_scenes.looks_payload(request.user, scene),
            "vn_scenes": _full_vn_payload(),
        })

    if action == "add_look_mood":  # one more mood for the look on stage, drawn as an edit of its neutral picture
        try:
            scene, look, cost = vn_scenes.add_look_mood(request.user, beat_id=str(body.get("beat_id") or ""),
                                                        emotion=str(body.get("emotion") or ""))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"scene": scene, "look": look, "cost": cost,
                             "looks": vn_scenes.looks_payload(request.user, scene)})

    if action == "change_look":  # from one passage on: another of their looks, a new outfit edited from this one, or keep
        look_id = body.get("look_id")
        try:
            scene, cost, errors = vn_scenes.change_look(
                request.user, str(body.get("beat_id") or ""), str(body.get("key") or ""),
                look_id=int(look_id) if str(look_id or "").isdigit() else None,
                name=str(body.get("name") or ""), outfit=str(body.get("outfit") or "")[:1200], keep=bool(body.get("keep")))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        return JsonResponse({"scene": scene, "cost": cost, "errors": errors, "vn_scenes": _full_vn_payload()})

    if action == "set_stage":
        from . import vn_story
        state = vn_scenes.get_vn_state(request.user)
        scene = state.get("active_scene")
        if not scene:
            return JsonResponse({"error": "No active scene."}, status=400)
        expected = (scene["id"], scene.get("revision", 0))
        beat = next((b for b in scene.get("beats", []) if b.get("id") == body.get("beat_id")), None)
        if not beat:
            beat = (scene.get("beats") or [{}])[-1]
        change = {k: body[src] for k, src in (("music", "music_id"), ("background", "background_id")) if body.get(src)}
        stage = vn_story.advance_stage(beat.get("stage") or vn_story.stage_of(scene), change,
                                      vn_scenes.available_music_tracks(chars), vn_scenes.available_backgrounds(chars, request.user))
        group = beat.get("block_id") or beat.get("id")
        for collection in (scene.get("beats", []), scene.get("history", []), scene.get("current_beats", [])):
            for item in collection:
                if (item.get("block_id") or item.get("id")) == group:
                    item["stage"] = stage
        if group == ((scene.get("beats") or [{}])[-1].get("block_id") or (scene.get("beats") or [{}])[-1].get("id")):
            scene["current_stage"] = stage
            scene.update({k: stage.get(k) for k in ("background", "music", "location", "continuity")})
        try:
            vn_scenes.save_vn_state(request.user, {"active_scene": scene}, expected=expected)
        except ai_client.AIError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        return JsonResponse({"scene": scene})

    if action == "finish_scene":
        cg_hint = str(body.get("cg_hint") or "").strip()
        try:
            entry, cost = vn_scenes.finish_scene_with_cg(request.user, cg_hint=cg_hint,
                                                       capture_image=bool(body.get("capture_image", True)))
        except ai_client.AIError as e:
            return JsonResponse({"error": str(e)}, status=400)
        tid = entry.get("thread_id")
        t_obj = MessengerThread.objects.filter(user=request.user, id=tid).prefetch_related("characters").first() if tid else None
        all_threads = [
            messenger.serialize_thread_summary(t)
            for t in MessengerThread.objects.filter(user=request.user).prefetch_related("characters")
        ]
        return JsonResponse({
            "gallery_entry": entry,
            "cost": cost,
            "vn_scenes": _full_vn_payload(t_obj),
            "thread": messenger.serialize_thread_full(t_obj, request.user) if t_obj else None,
            "threads": all_threads,
        })

    if action == "delete_gallery_item":
        gid = body.get("id")
        state = vn_scenes.get_vn_state(request.user)
        gallery = [g for g in (state.get("gallery") or []) if g.get("id") != gid]
        vn_scenes.save_vn_state(request.user, {"gallery": gallery})
        return JsonResponse({"vn_scenes": _full_vn_payload()})

    return JsonResponse({"error": f"Unknown scenes action '{action}'."}, status=400)


