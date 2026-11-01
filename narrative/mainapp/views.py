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
from .models import Character, Worldbook, ChatSettings
from . import extras, game, media_library, recall, story, thinking, ai_client, cards, chats, regex_rules, model_profiles, presets, samplers, starters, trackers
from .bulba import control, polish, watch

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
def characters_list(request):
    return render(request, 'mainapp/characters.html')




import re

log = logging.getLogger(__name__)

def _summary_line(message):
    return f"{message[0]}: {chats.prompt_text(message)}"


def _summarize(user, messages, existing="", room=None):
    """One summary piece for `messages`, continuing `existing` when there is one. With `room` (tokens), a single
    message longer than that is cut to fit (its end kept)."""
    if existing:
        sys_prompt = (f"Existing summary: {existing}\n\nTask: Read the recent conversation below "
                      "and create a short paragraph summarizing ONLY the new events, advancing the existing summary.")
    else:
        sys_prompt = ("Summarize this entire roleplay story concisely. Capture key events and current status. "
                      "Be clear and precise, focus on describing events and reactions in detail. "
                      "The summary should include Tone, Setting, Events, Current emotional state.")
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


NOTE_FRAME = "[Director's note, outside the story (not something said or done in it): {text}]"


def _history(messages, note_slot=False):
    """The chat as the AI reads it. Director's notes come framed as directions; with note_slot, a note at the very
    end is left out, because the request carries it in the preset's director's note slot."""
    out = []
    for i, m in enumerate(messages):
        if m[0] not in ("user", "assistant"):
            continue
        text = extras.for_prompt(chats.prompt_text(m), chats.game_of(m))
        if chats.is_note(m):
            if note_slot and i == len(messages) - 1:
                continue
            text = NOTE_FRAME.replace("{text}", text)
        out.append({"role": m[0], "content": text})
    return out


def _photo(character, prefix, emotion):
    """The sprite for an emotion, falling back to neutral."""
    image = getattr(character, f"{prefix}_{emotion}", None) or getattr(character, f"{prefix}_neutral", None)
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
        "context_guides": {},
        "current_bg": "",
        "current_music": {},
        "music_follow": {},     # {"on": bool, "since": replies since the last pick}: music follows the scene
        "last_recall": [],      # old messages free recall brought back for the last reply (see mainapp/recall.py)
        "persona": {},          # {"name", "description"}: who the user is in this chat only (else their usual persona)
        "game": {},             # dice and inventory: the starting inventory after manual edits (see mainapp/game.py)
        "voices": {},           # voices picked for speakers in this chat (see mainapp/voice.py), so they stay the same
        "story": {},            # story systems' values: meters, story time, events (see mainapp/story.py)
    }
    game_mode = game.mode_for(request.user, character)
    extra_kinds = extras.kinds_for(request.user)        # letters, phone screens, milestones (Extras page)
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
        if os.path.exists(chat_file_path):
            with open(chat_file_path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)

                    if isinstance(data, dict):
                        set_summary(chats.summary_parts(data, len(data.get("messages") or [])))
                        chat_state["trackers"] = data.get("trackers") or {}
                        chat_state["tracker_history"] = data.get("tracker_history") or []
                        chat_state["summary_paused"] = bool(data.get("summary_paused"))
                        chat_state["context_guides"] = data.get("context_guides", {})
                        chat_state["current_bg"] = data.get("current_bg", "")
                        chat_state["current_music"] = data.get("current_music", {})
                        chat_state["music_follow"] = data.get("music_follow") if isinstance(data.get("music_follow"), dict) else {}
                        chat_state["last_recall"] = data.get("last_recall") if isinstance(data.get("last_recall"), list) else []
                        chat_state["persona"] = data.get("persona") if isinstance(data.get("persona"), dict) else {}
                        chat_state["game"] = data.get("game") if isinstance(data.get("game"), dict) else {}
                        chat_state["voices"] = data.get("voices") if isinstance(data.get("voices"), dict) else {}
                        chat_state["story"] = data.get("story") if isinstance(data.get("story"), dict) else {}
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

                    return fixed_messages
                except json.JSONDecodeError:
                    return []
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

    def save_messages(messages):
        sync_game_trackers(messages)
        full_data = {
            "messages": messages,
            "summary": chat_state["summary"],
            "summary_upto": chat_state["summary_upto"],
            "summary_parts": chat_state["summary_parts"],
            "summary_paused": chat_state["summary_paused"],
            "trackers": chat_state["trackers"],
            "tracker_history": chat_state["tracker_history"],
            "context_guides": chat_state["context_guides"],
            "current_bg": chat_state["current_bg"],
            "current_music": chat_state["current_music"],
            "music_follow": chat_state["music_follow"],
            "last_recall": chat_state["last_recall"],
            "persona": chat_state["persona"],
            "game": chat_state["game"],
            "voices": chat_state["voices"],
            "story": chat_state["story"],
        }
        with open(chat_file_path, "w", encoding="utf-8") as f:
            json.dump(full_data, f, ensure_ascii=False, indent=2)
        chat_obj.save(update_fields=["time_update"])

    messages = load_messages()

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
        if action in ("list_chats", "new_chat", "rename_chat", "delete_chat"):
            go_to = None
            if action == "new_chat":
                go_to = chats.create(character).id
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
                    # Update the message text, keep other fields
                    new_text = text_rules("saved", new_text, messages[index][0], edits_only=True)
                    if messages[index][0] == "assistant" and messages[index][2] != new_text:
                        watch.note_signal(request.user, chat_obj, "edited", messages[index][2], new_text)
                        rec = chats.polish_of(messages[index])
                        if rec:  # they changed Bulba's polished version: ask what didn't work
                            watch.polish_rejected(request.user, chat_obj, index, "edited", rec, rec.get("habits"))
                    messages[index] = chats.set_text(messages[index], new_text)
                    save_messages(messages)
                    return JsonResponse({"success": True, "text": new_text,
                                         "watch": watch.page_state(request.user, chat_obj)})
                else:
                    return JsonResponse({"success": False, "error": "Invalid message index"})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        # Handle delete action
        elif action == "delete":
            try:
                index = int(data.get("index"))

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
                else:
                    return JsonResponse({"success": False, "error": "Invalid message index"})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        # --- Write my message (impersonate): the AI writes or expands the user's next message ---
        elif action == "expand":
            draft = text_rules("saved", str(data.get("text") or "").strip(), "user") if data.get("text") else ""
            preset = presets.normalize(presets.get_active(request.user).data)
            ask = (preset["utility"]["impersonation"].strip() or presets.UTILITY_DEFAULTS["impersonation"])
            if draft:
                ask += ("\n\n[{{user}} sketched their next move below. Write it out as their full message, in the "
                        "story's language and style and about as long as their earlier messages: what they say, "
                        "and how they say and do it (tone, gesture, a small detail of the moment). Keep their intent "
                        "and decisions; don't add new decisions for them, other characters' reactions or "
                        f"outcomes.]\n{draft}")
            names = prompt_names(request.user, character, chat_state["persona"])
            ask = ask.replace("{{user}}", names["user"]).replace("{{char}}", names["char"])
            try:
                built = build_chat_request(request.user, chat_obj, preset=preset, drop_last_reply=False,
                                           generation="impersonate", tail=[{"role": "system", "content": ask}])
                message, _ = ai_client.complete_message(request.user, "chat", built["messages"], **built["params"])
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            thought, written = thinking.split(message.get("content") or "")
            written = written.strip()
            if not written:
                why = ("The model used up the reply length thinking. Raise the reply length limit (Samplers) or "
                       "ask Bulba." if thought or message.get("reasoning") else "The model sent back nothing. Try again.")
                return JsonResponse({"success": False, "error": why, "text": draft,
                                     "spending": ai_client.spending(request.user)})
            if draft and written.strip() == draft.strip():
                return JsonResponse({"success": False, "error": "The model gave your draft back unchanged. Try again, "
                                     "or add a word about what you want.", "text": draft,
                                     "spending": ai_client.spending(request.user)})
            # Bulba's polish: the habits they asked to have fixed, in their written-out message too
            fixed = []
            habits = polish.habits_for_draft(request.user, chat_obj, written, polish.others_before(messages, len(messages), "user"))
            if habits:
                try:
                    written, fixed = polish.polish_text(request.user, character, chat_obj, written,
                                                        polish.others_before(messages, len(messages), "user"),
                                                        chat_state["summary"], habits, whose="theirs")
                except ai_client.AIError as e:
                    log.info("Polish skipped for a written message: %s", e)
            return JsonResponse({"success": True, "text": written, "polished": len(fixed),
                                 "spending": ai_client.spending(request.user)})

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
                audio, cast = voice.voice_reply(request.user, character, message[2], chat_state["voices"],
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
                save_messages(messages)
            if now or again:
                reason = polish.why_not_now(request.user, chat_obj, messages, index)
                if not reason and chats.polish_of(messages[index]):
                    reason = "That reply is already polished (Undo fixes under it puts the original back)."
                if reason:
                    return JsonResponse({"success": True, "changed": False, "reason": reason})
            elif index != len(messages) - 1 or not polish.due(request.user, chat_obj, messages) \
                    or chats.polish_of(messages[-1]):
                return JsonResponse({"success": True, "changed": False})
            original = messages[index][2]
            try:
                new_text, fixes = polish.polish(request.user, character, chat_obj, messages, chat_state["summary"],
                                                index)
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})
            messages = load_messages()  # read again: they may have moved on while it worked
            if not fixes or index >= len(messages) or messages[index][0] != "assistant" \
                    or messages[index][2] != original:
                return JsonResponse({"success": True, "changed": False, "spending": ai_client.spending(request.user),
                                     "reason": "Bulba found nothing to change in that reply." if not fixes
                                     else "The reply changed meanwhile; nothing was replaced."})
            messages[index] = chats.with_polish(messages[index], new_text,
                                                polish.record(original, fixes, polish.habits_of(request.user, fixes)))
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
        elif action == "watch_note":  # a note: dismissed, "I don't mind this", or opened with Bulba
            if data.get("status") not in ("dismissed", "muted", "opened", "fix", "stop_fix"):
                return JsonResponse({"success": False, "error": "Unknown choice."}, status=400)
            try:
                watch.set_notice(request.user, chat_obj, str(data.get("id") or ""), data["status"])
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            return JsonResponse({"success": True, "watch": watch.page_state(request.user, chat_obj)})
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
        elif action == "ai_saw":  # the pen menu's "What the AI saw": summary, pinned note, trackers, lore
            from .bulba import memory
            return JsonResponse({"success": True, **memory.what_the_ai_saw(chat_obj)})
        elif action == "note_ideas":  # "Be creative": Bulba writes two director's notes, a logical one and a bold one
            try:
                ideas = note_ideas(request.user, character, messages, chat_state["summary"], chat_state["persona"])
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
                user_name = request.user.name or request.user.username
                named = [(user_name if m[0] == "user" else character.name, m[2]) for m in recent]
                def tracker_request(named):
                    built = trackers.update_messages(config, state, named, character.name, user_name, only)
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
                                     "has_trackers": bool((tracker_state or {}).get("values"))})

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
            title = f"{chat_obj.title} ⑂ {chat_obj.branches.count() + 1}"[:200]
            branch = chats.create(character, title, branch_data, parent=chat_obj, branch_point=count)
            return JsonResponse({"success": True, "go_to": branch.id})

        # --- 5. NEW: Regenerate/Continue Logic ---
        elif action == "regenerate":
            # The old reply is only replaced once the new one arrives (and is kept as a swipe)
            if messages and messages[-1][0] == "assistant":
                regen_from = messages.pop()
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
            save_messages(messages)
            _, _, text, emotion, char_count = messages[-1][:5]
            emo1, _, emo2 = (emotion or "neutral").partition("|")
            return JsonResponse({
                "success": True, "reply": text, "emotion": emotion, "char_count": char_count,
                "reasoning": chats.reasoning_of(messages[-1]),
                "game": [game.describe(op) for op in chats.game_of(messages[-1]) if not extras.is_extra(op)],
                "extras_html": [extras.render(op) for op in chats.game_of(messages[-1]) if extras.is_extra(op)],
                "game_trackers": game_trackers(),
                "photo_url": _photo(character, "photo", emo1),
                "photo_second": _photo(character, "photo_second", emo2 or "neutral")
                if (character.is_mult or char_count >= 2) else None,
                "swipes": chats.version_info(messages),
                "polish": polish.page_payload(chats.polish_of(messages[-1])),
                "directed": chats.directed_of(messages[-1]),
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
                                          summary=chat_state["summary"])
                preset = presets.normalize(presets.get_active(request.user).data)
                _, chat_model = ai_client.resolve(request.user, "chat")
                names = prompt_names(request.user, character, chat_state["persona"])
                history = _history(messages)
                history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, request.user), history, names)
                # The unfinished reply is the last message; the preset's continue nudge comes after it
                nudge = preset["utility"]["continue_nudge"].strip() or presets.UTILITY_DEFAULTS["continue_nudge"]
                history.append({"role": "system", "content": nudge})
                built, _ = recall.assemble_with_recall(
                    presets.assemble, preset, prompt_slots(request.user, character, prompt, chat_state["persona"]),
                    history, names, chat_model, generation="continue")
                new_chunk = ai_client.complete(request.user, "chat", built["messages"], **built["params"])
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})

            new_chunk = (new_chunk or "").rstrip()
            if new_chunk and not new_chunk[0].isspace() and new_chunk[0] not in ".,;:!?)…'\"" and not last_text.endswith((" ", "\n")):
                new_chunk = " " + new_chunk
            full_text = text_rules("saved", last_text + new_chunk, "assistant")
            messages[-1] = chats.set_text(messages[-1], full_text)
            save_messages(messages)
            return JsonResponse({"success": True, "reply": full_text,
                                 "polish_due": polish.due(request.user, chat_obj, messages)})
        elif action == "chat_persona":  # who the user is in this chat only; empty name = their usual persona
            name = str(data.get("name") or "").strip()[:100]
            chat_state["persona"] = ({"name": name, "description": str(data.get("description") or "").strip()[:4000]}
                                     if name else {})
            save_messages(messages)
            return JsonResponse({"success": True, "persona": chat_state["persona"],
                                 "name": prompt_names(request.user, character, chat_state["persona"])["user"]})
        elif action == "appearance" and "layout" in data:  # chat bubbles or chapters
            try:
                set_layout(request.user, data.get("layout"))
            except ValueError as e:
                return JsonResponse({"success": False, "error": str(e)}, status=400)
            if data.get("layout") == "book":  # the look without director mode: Bulba offers the rest
                watch.offer_director_for_book(request.user, chat_obj)
            return JsonResponse({"success": True, **_appearance(request.user),
                                 "watch": watch.page_state(request.user, chat_obj)})
        elif action == "appearance":  # dialogue colour: a hex colour, or "preset" to leave it to the preset
            color = str(data.get("dialogue_color") or "")
            if color != "preset" and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                return JsonResponse({"success": False, "error": "Pick a colour."}, status=400)
            # Each character has its own colour (part of its theme)
            character.theme = {**(character.theme or {}), "dialogue_color": color}
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
                        summary=chat_state["summary"],
                        story_values=story_state() if systems else None)
                    lore_report = prompt.get("LoreReport")


                    # --- Build the request from the active preset ---
                    preset = presets.normalize(presets.get_active(request.user).data)
                    _, chat_model = ai_client.resolve(request.user, "chat")
                    names = prompt_names(request.user, character, chat_state["persona"])
                    history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, request.user), api_messages, names)
                    if control.mode_of(preset) == "director":  # each direction says what it means (see control.py)
                        history = control.frame_directions(history, names)
                    built, recalled = recall.assemble_with_recall(
                        presets.assemble, preset, prompt_slots(request.user, character, prompt, chat_state["persona"]),
                        history, names, chat_model, generation="regenerate" if action == "regenerate" else "normal")
                    context_dropped = built["dropped"]
                    chat_state["last_recall"] = recalled  # shown in "What the AI saw"
                    # Dice and inventory: the model gets tools and the current state (the reply works on a copy)
                    game_state = game.current_state(chat_state, messages)
                    built = game.add_to_request(built, game_mode, game_state, names, extra_kinds,
                                                tables=story.of_type(systems, "table"))
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
                    reply = text_rules("saved", reply, "assistant")
                    reasoning = text_rules("saved", reasoning, "reasoning").strip() if reasoning else ""
                    reply = extras.place(reply, ops)  # each story extra's marker, where it goes in the text
                    char_count = 1
                    emotion_char_1 = "neutral"
                    emotion_char_2 = "neutral"

                    # --- Classify emotion (optional, can be turned off on the Connections page) ---
                    try:
                        if not ai_client.is_enabled(request.user, "emotion"):
                            raise ai_client.AIError("emotion detection is turned off")
                        valid_emotions = ["neutral", "happy", "sad", "angry", "surprised", "scared", "confused", "calm", "scheming"]

                        # Prompt asks LLM who is speaking (1, 2, or both) and their emotions
                        classification_system_prompt = (
                            f"You are an analysis tool. The main character is named '{character.name}'.\n"
                            "Analyze the last message and determine who is speaking.\n"
                            "Rules:\n"
                            f"1. If ONLY '{character.name}' is speaking, set 'speaking' to '1'.\n"
                            f"2. If ONLY the other character is speaking, set 'speaking' to '2'.\n"
                            "3. If BOTH characters are speaking, set 'speaking' to 'both'.\n"
                            "4. Determine the emotion for the speaking character(s) from this list: "
                            f"{json.dumps(valid_emotions)}.\n"
                            "Return ONLY a JSON object with this format:\n"
                            '{ "speaking": "1" or "2" or "both", "emotion_1": "...", "emotion_2": "..." }'
                        )

                        class_text = ai_client.complete(request.user, "emotion", [
                            {"role": "system", "content": classification_system_prompt},
                            {"role": "user", "content": reply}],
                            max_tokens=100, temperature=0.0, response_format={"type": "json_object"})
                        class_data = json.loads(class_text)

                        speaker = str(class_data.get("speaking", "1")).lower()
                        emotion_char_1 = class_data.get("emotion_1", "neutral")
                        emotion_char_2 = class_data.get("emotion_2", "neutral")

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

                    # Store emotions as "happy|sad" string
                    final_emotion_str = f"{emotion_char_1}|{emotion_char_2}"
                    new_message = chats.with_game(chats.with_reasoning(
                        ("assistant", datetime.now().strftime("%H:%M"), reply, final_emotion_str, char_count), reasoning),
                        [dict(op) for op in ops if op.get("type") != "notice"])
                    if directed:  # shown above the reply: what steered it (a note is a message of its own instead)
                        new_message = chats.with_directed(new_message, directed[:1000])
                    messages.append(chats.add_version(regen_from, new_message) if regen_from else new_message)

                    photo_url = _photo(character, "photo", emotion_char_1)
                    photo_second = (_photo(character, "photo_second", emotion_char_2)
                                    if (character.is_mult or char_count >= 2) else None)

                    save_messages(messages)
                    watch.on_reply_done(request.user, chat_obj, messages, character.name)  # free checks, pace clock

                    # Automatic summary: tell the page to run one in the background
                    summary_task = ai_client.get_task_setting(request.user, "summary")
                    summarized = chat_state["summary_upto"] or 0
                    summary_due = (summary_task.mode == summary_task.MODE_AUTO and not chat_state["summary_paused"]
                                   and len(messages) - summarized >= summary_task.interval)

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
                        "char_count": char_count,
                        "voice": bool(get_elevenlabs_key(request.user)),
                        "lore": lore_report,
                        "summary_due": summary_due,
                        "trackers_due": trackers_due,
                        "music_due": music_due(),  # the music follows the scene: the page asks for a pick
                        "watch_due": watch.due(request.user, chat_obj, messages),  # Bulba Watch reads, in the background
                        "polish_due": polish.due(request.user, chat_obj, messages),  # the page asks for the polish next
                        "watch": watch.page_state(request.user, chat_obj),
                        "context_dropped": context_dropped,
                        "swipes": chats.version_info(messages),
                        "spending": ai_client.spending(request.user),
                        "directed": chats.directed_of(messages[-1]),
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

                response = StreamingHttpResponse(stream_reply(), content_type="application/x-ndjson")
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

    user_avatar = None
    if hasattr(request.user, 'photo') and request.user.photo:
        user_avatar = request.user.photo.url

    sync_game_trackers(messages)
    context = {
        # The template shows the version on screen, and its thoughts (if the model sent any)
        "messages": [tuple(m[:5]) + (chats.reasoning_of(m),
                                     [game.describe(op) for op in chats.game_of(m) if not extras.is_extra(op)],
                                     [extras.render(op) for op in chats.game_of(m) if extras.is_extra(op)],
                                     (chats.audio_of(m) or {}).get("url", ""),
                                     polish.dumps(chats.polish_of(m)) if chats.polish_of(m) else "",
                                     chats.directed_of(m), chats.condensed_of(m), chats.is_note(m))
                     for m in messages],
        "voice_on": bool(get_elevenlabs_key(request.user)),
        "swipes": chats.version_info(messages),
        "spending": ai_client.spending(request.user),
        "appearance": _appearance(request.user, character),
        "bulba_ideas": extras.ideas_on(request.user),
        "bulba_url": reverse("bulba_chat", kwargs={"chat_id": chat_obj.id}),
        "watch_data": watch.page_state(request.user, chat_obj),
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
        "char_count": char_count,
        "photo_neutral": photo_url,
        "summary": chat_state["summary"],
        "summary_upto": chat_state["summary_upto"],
        "summary_data": summary_payload(),
        "context_guides": json.dumps(chat_state["context_guides"]),
        "pinned_note_json": json.dumps(pinned_note(chat_state["context_guides"])),
        # The chat's own background and music, else the character's theme
        "current_bg": chat_state["current_bg"] or (character.theme or {}).get("bg", ""),
        "current_music": json.dumps(chat_state["current_music"] or (character.theme or {}).get("music") or {}),
        "music_follow": bool(chat_state["music_follow"].get("on")),
        "user_avatar": user_avatar,
        "trackers_data": {**_tracker_page_data(request.user, character, _synced(chat_state)), "story": story_payload()},
        "stream_replies": presets.normalize(presets.get_active(request.user).data)["options"]["streaming"],
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
    if color != "preset" and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        color = DIALOGUE_DEFAULT
    # "book": replies read as chapters and the user's messages fold away (director mode); "chat": bubbles
    layout = look.get("layout") if look.get("layout") in LAYOUTS else "chat"
    return {"dialogue_color": color, "layout": layout}


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


WORD_NOTE_PROMPT = (
    "You help someone steer their roleplay with an AI. They give you a rough wish for {what}; you write it as "
    "a director's note the roleplay model will follow. One to three short sentences, addressed to the model, "
    "saying concretely what should happen or how it should read. Keep their meaning; don't add events, twists "
    "or details they didn't ask for. Name characters as they appear in the chat. Never write {user}'s words, "
    "actions or thoughts unless they asked for exactly that. Plain words: no 'ensure', 'immersive', 'vivid', "
    "'delve', capitals or exclamation marks. Reply with the note only.")


CONDENSE_PROMPT = (
    "Condense one message from a roleplay so the AI can keep it in mind in fewer words. Keep what matters later: "
    "what happened, decisions, promises, names, places, objects, how people feel about each other, and any line "
    "of dialogue worth remembering word for word. Drop description and repetition. Same person and tense as the "
    "message, plain sentences, at most a quarter of its length. Reply with the condensed message only.")


def condense(user, character, message, persona=None):
    """A short version of one message for the AI (one call on the summary model)."""
    names = prompt_names(user, character, persona)
    who = names["user"] if message[0] == "user" else character.name
    text = ai_client.complete(user, "summary", [
        {"role": "system", "content": CONDENSE_PROMPT},
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
    recent = "\n\n".join(str(m[2])[:1200] for m in messages[-2:])
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


NOTE_IDEAS_PROMPT = (
    "You help someone direct their roleplay with an AI. Read the chat and write two director's notes for the next "
    "reply, each one or two short sentences addressed to the roleplay model, saying concretely what should happen "
    "or how it should read. \"logical\": what would most naturally happen next, given the scene and the people in "
    "it. \"creative\": an unexpected turn that still fits the characters and the world (a complication, an "
    "arrival, a reveal, a change of place or time), not a random one. Name characters as they appear in the chat. "
    "Never write {user}'s words, actions or thoughts. Plain words: no 'ensure', 'immersive', 'vivid', 'delve', "
    "capitals or exclamation marks. Answer only with JSON: {{\"logical\": \"...\", \"creative\": \"...\"}}")


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
    transcript = "\n\n".join(f"{names['user'] if m[0] == 'user' else character.name}: {m[2][:1500]}" for m in recent)
    text = bulba_quick(user, [
        {"role": "system", "content": NOTE_IDEAS_PROMPT.format(user=names["user"])},
        {"role": "user", "content": (f"The story so far: {summary[:2000]}\n\n" if summary else "")
                                    + f"The latest messages (latest last):\n\n{transcript}"}],
        temperature=0.8, response_format={"type": "json_object"})
    ideas = _note_fields(text)
    if not any(ideas.values()):
        log.warning("Be creative: no notes in the answer: %r", (text or "")[:300])
        raise ai_client.AIError("Bulba couldn't come up with anything this time. Try again.")
    return ideas


IDEAS_PROMPT = {
    "player": (
        "You help someone who is stuck in a roleplay with an AI. Read the chat and suggest three different things "
        "{user} could do or say next, as {user}. Each is one or two short sentences they could send as their "
        "message, written the way {user}'s recent messages are written (same person, tense and style). Make the "
        "three genuinely different: one that goes along with the scene, one that pushes it somewhere, one "
        "unexpected but in character for {user}. Only {user}'s own words and actions; never decide what "
        "{char} or anyone else does or feels. Stay true to what has happened and to the world."),
    "director": (
        "You help someone who directs a roleplay with an AI from outside the story. Read the chat and suggest "
        "three different things that could happen next, each one or two short sentences they could send as a "
        "direction (\"{char} finds the letter\", \"A storm cuts the power\"). Make them genuinely different: one "
        "that deepens the current scene, one that moves the plot, one surprising but believable in this world. "
        "Stay true to what has happened, the characters and the world."),
}
IDEAS_STYLE = ("Plain words, no 'ensure', 'immersive', 'vivid', 'delve', no capitals for emphasis, no exclamation "
               "marks. Answer with JSON only: {\"ideas\": [\"...\", \"...\", \"...\"]}")


def bulba_ideas(user, character, messages, mode, persona=None, summary=""):
    """Three ideas for what to write next ("player") or what could happen next ("director"), on Bulba's model."""
    names = prompt_names(user, character, persona)
    recent = [m for m in messages if m[0] in ("user", "assistant")][-8:]
    transcript = "\n\n".join(f"{names['user'] if m[0] == 'user' else character.name}: {m[2][:1500]}" for m in recent)
    system = IDEAS_PROMPT[mode].format(user=names["user"], char=names["char"]) + "\n\n" + IDEAS_STYLE
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
    transcript = "\n\n".join(f"{names['user'] if m[0] == 'user' else character.name}: {m[2][:1500]}" for m in recent)
    what = "a new version of the last reply" if rewrite else "the next reply"
    system = WORD_NOTE_PROMPT.format(what=what, user=names["user"])
    text = bulba_quick(user, [
        {"role": "system", "content": system},
        {"role": "user", "content": f"The chat so far (latest last):\n\n{transcript}\n\nTheir wish: {wish}"}],
        temperature=0.4)
    text = (text or "").strip().strip('"')
    if not text:
        raise ai_client.AIError("Bulba couldn't word it this time. Try again.")
    return text


def prompt_names(user, character, chat_persona=None):
    """{{char}} and {{user}}: this chat's persona name, else the usual persona name, else the account name."""
    return {"char": character.name or "Character",
            "user": (chat_persona or {}).get("name") or getattr(user, "persona_name", None) or user.name or user.username}


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
                       tail=()):
    """
    The request a chat would send for its next AI reply (or, with drop_last_reply, to re-answer the last user
    message), optionally with another preset or an edited character. Used by Bulba to rewrite a reply with a
    proposed change. `tail`: extra turns after the chat (an impersonation request). Returns presets.assemble()'s result.
    """
    character = character or chat_obj.character
    data = chats.read(chat_obj)
    messages = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    if drop_last_reply and messages and messages[-1][0] == "assistant":
        messages = messages[:-1]
    summary = chats.summary_text(chats.summary_parts(data, len(messages)))
    worldbook_slug = character.worldbook.slug if character.worldbook and character.worldbook.author == user else None
    prompt = build_ai_request(user, character, chat=chat_obj, worldbook_slug=worldbook_slug, message=None,
                              guidance="", persistent_guides=data.get("context_guides") or {}, summary=summary)
    preset = presets.normalize(preset or presets.get_active(user).data)
    persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    names = prompt_names(user, character, persona)
    history = _history(messages)
    history = regex_rules.run_on_history(regex_rules.for_chat(preset, character, user), history, names)
    if control.mode_of(preset) == "director" and not tail:
        history = control.frame_directions(history, names)
    history += list(tail)
    _, model = ai_client.resolve(user, "chat")
    if tail:  # an extra request at the end (impersonation): no recall, its words aren't the scene's
        return presets.assemble(preset, prompt_slots(user, character, prompt, persona), history, names, model,
                                generation=generation)
    return recall.assemble_with_recall(presets.assemble, preset, prompt_slots(user, character, prompt, persona),
                                       history, names, model, generation=generation)[0]


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
            obj = Preset.objects.create(user=request.user, data=presets.build_default(request.user),
                                        name=presets.unique_name(request.user, presets.DEFAULT_NAME))
        elif action == "use_starter":
            try:
                obj = starters.apply(request.user, data.get("starter"))
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
        "macro_help": presets.MACRO_HELP,
        "post_processing": presets.POST_PROCESSING,
        "characters": [{"slug": c.slug, "name": c.name} for c in Character.objects.filter(author=request.user)],
        "starters": starters.for_page(_chat_model(request.user)),
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

    return render(request, "mainapp/tracker_setup.html", {
        "character": character,
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
    result = activate(book, messages)
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


@login_required
def character_sprite(request, slug):
    """Makes one mood picture from the character's neutral picture with Nano Banana (OpenRouter)."""
    from django.core.files.base import ContentFile
    character = get_object_or_404(Character, slug=slug, author=request.user)
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        data = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    emotion = data.get("emotion")
    prefix = "photo_second" if data.get("second") else "photo"
    if emotion not in SPRITE_EMOTIONS:
        return JsonResponse({"error": "Unknown mood."}, status=400)
    neutral = getattr(character, f"{prefix}_neutral")
    if not neutral:
        return JsonResponse({"error": "Add a neutral picture first; the others are made from it."}, status=400)
    with neutral.open("rb") as f:
        reference = f.read()
    kind = "image/png" if reference.startswith(b"\x89PNG") else "image/webp" if reference[:4] == b"RIFF" else "image/jpeg"
    who = character.name if prefix == "photo" else f"the second character of {character.name}"
    prompt = (f"This is {who}. Make a new picture of exactly the same character: same face, hair, body, outfit, "
              f"art style, framing, lighting and background. Only the expression and body language change: show "
              f"them {emotion}. No text, no borders, no extra people.")
    model = data.get("model") or None
    if model:
        known = [m["id"] for m in ai_client.image_models()]
        if known and model not in known:
            return JsonResponse({"error": "OpenRouter doesn't list that image model."}, status=400)
    try:
        image, cost = ai_client.generate_image(request.user, prompt, reference, kind, model=model)
    except ai_client.AIError as e:
        return JsonResponse({"error": str(e)}, status=502)
    field = getattr(character, f"{prefix}_{emotion}")
    if field:
        field.storage.delete(field.name)
    ext = "jpg" if image[:3] == b"\xff\xd8\xff" else "webp" if image[:4] == b"RIFF" else "png"
    field.save(f"{slugify(character.name) or 'character'}-{emotion}.{ext}", ContentFile(image), save=False)
    character.save()
    return JsonResponse({"status": "ok", "field": f"{prefix}_{emotion}", "url": field.url, "cost": cost,
                         "spending": ai_client.spending(request.user)})


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
    return JsonResponse({"status": "ok", "name": character.name, "notes": notes,
                         "url": reverse("chat", kwargs={"slug": character.slug}),
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
        "music": media_library.built_in("music") + get_files("music")
    })


# ---------------------------------------------------------------------------
# Bulba, the setup assistant
# ---------------------------------------------------------------------------

def _bulba_state(session):
    from .bulba import agent, editing, progress
    profile = agent.target_profile(session)
    return {
        "id": session.id, "stage": session.stage, "stages": agent.STAGES,
        "progress": progress.progress(session, agent.STAGES) if session.mode == "setup" else None,
        "spent": round(session.spent, 4), "budget": session.budget, "month": ai_client.spending(session.user),
        "chat": _bulba_chat_link(session) if session.mode == "setup" else None,
        "mode": session.mode,
        "chat_with": session.chat.character.name if session.mode == "chat" and session.chat_id else "",
        "model": profile["name"] if profile else session.target_model,
        "preferences": [p for p in session.preferences if p.get("status") not in ("rejected", "superseded")],
        "proposals": [{**{k: p.get(k) for k in ("id", "kind", "title", "status", "result", "edited")},
                       "summary": _shown_summary(session, p), "editable": editing.fields(p)} for p in session.proposals],
    }


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
    profile = model_profiles.for_model(chat_model)
    if profile is None:
        return None
    session = BulbaSession.objects.filter(user=user, active=True, mode="setup").first()
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
    profile = model_profiles.for_model(chat_model)
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


def _bulba_for_request(request, restart=False):
    """The setup conversation, or the one about a chat when the page passes ?chat=<id>."""
    from .models import Chat
    chat_id = request.GET.get("chat")
    if chat_id:
        chat_obj = Chat.objects.filter(id=chat_id, character__author=request.user).first()
        if chat_obj is None:
            raise Http404("No such chat.")
        return _bulba_chat_session(request.user, chat_obj, restart)
    return _bulba_session(request.user, restart)


@login_required
def bulba_page(request):
    if not ai_client.has_connection(request.user):
        return redirect("users:welcome")
    session = _bulba_session(request.user)
    route = request.GET.get("route")
    if session and route in ("full", "fast") and len(session.events) == 1:  # picked on the welcome tour's last step
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
        "bulba_data": {"state": _bulba_state(session), "events": session.events} if session else None,
        "known_models": model_profiles.known_names(),
        "in_chats": in_chats,
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
        return JsonResponse({"error": "Bulba needs your OpenRouter key first (the welcome page)."}, status=400)
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
        "bulba_data": {"state": _bulba_state(session), "events": session.events} if session else None,
        "known_models": model_profiles.known_names(),
        "embed": True, "chat_obj": chat_obj,
    })


@login_required
def bulba_api(request):
    from .bulba import actions, agent, editing, progress
    from .models import BulbaSession
    if request.method == "GET":  # what Bulba is doing right now (the page asks while a turn runs)
        filters = {"mode": "chat", "chat_id": request.GET["chat"]} if request.GET.get("chat") else {"mode": "setup"}
        session = BulbaSession.objects.filter(user=request.user, active=True, **filters).first()
        return JsonResponse({"activity": session.activity if session else ""})
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    if request.FILES.get("card"):  # a card they already have, from the upload box
        return _bulba_card_upload(request)
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
        events = agent.run_turn(session, data.get("text"))
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
    from django.core.files.base import ContentFile
    from PIL import Image, UnidentifiedImageError
    from .bulba import agent, lore
    session = _bulba_for_request(request, restart=False)
    if session is None:
        return JsonResponse({"error": "Bulba isn't available."}, status=400)
    character = lore.target_character(session)
    if character is None:
        return JsonResponse({"error": "Make or pick a character first, then add their pictures."}, status=400)
    upload, target = request.FILES["picture"], request.POST.get("as", "neutral")
    if target not in SPRITE_EMOTIONS + ["neutral", "background"]:
        return JsonResponse({"error": "Unknown kind of picture."}, status=400)
    if upload.size > 15 * 1024 * 1024:
        return JsonResponse({"error": "That picture is over 15 MB."}, status=400)
    raw = upload.read()
    try:
        Image.open(io.BytesIO(raw)).verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        return JsonResponse({"error": "That file isn't a picture."}, status=400)
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
    events = [{"type": "proposal", "id": p["id"]}]
    session.events += events
    events += agent.run_turn(session, None, action_note=f"Added {what}", model_note=f"They uploaded {what}; it's set.")
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
            f"{link['edit_url']}\n\n{lore.card_report(character)}")
    events += agent.run_turn(session, None, action_note=f"Imported {character.name}", model_note=note)
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
