# --- Standard library ---
import json
import os
import traceback
from datetime import datetime

# --- Django core ---
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.http import HttpResponse, JsonResponse, HttpResponseNotFound, StreamingHttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
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
from . import ai_client, chats, presets, samplers, trackers
from .utils import build_ai_request, narrate_text_backend, get_elevenlabs_key
from .lorebook import (
    normalize_book, load_worldbook, save_worldbook, activate, format_for_prompt, to_sillytavern,
    DEFAULT_SETTINGS as LORE_DEFAULT_SETTINGS, DEFAULT_ENTRY as LORE_DEFAULT_ENTRY,
)


@login_required
def index_page(request):
    # Беремо лише дефолтні персонажі для поточного користувача
    default_characters = Character.objects.filter(author=request.user, is_default=True)

    context = {
        'characters': default_characters
    }
    return render(request, 'main.html', context)


@login_required
def characters_list(request):
    return render(request, 'mainapp/characters.html')




import re

def _summarize(user, messages, existing=""):
    """One summary piece for `messages`, continuing `existing` when there is one."""
    if existing:
        sys_prompt = (f"Existing summary: {existing}\n\nTask: Read the recent conversation below "
                      "and create a short paragraph summarizing ONLY the new events, advancing the existing summary.")
    else:
        sys_prompt = ("Summarize this entire roleplay story concisely. Capture key events and current status. "
                      "Be clear and precise, focus on describing events and reactions in detail. "
                      "The summary should include Tone, Setting, Events, Current emotional state.")
    prompt_text = "\n".join(f"{m[0]}: {m[2]}" for m in messages)
    return ai_client.complete(user, "summary", [{"role": "system", "content": sys_prompt},
                                                {"role": "user", "content": prompt_text}])


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
        return redirect(f"{reverse('users:api_config')}?next={request.path}")

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
        "current_music": {}
    }

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

    # --- Save messages to file ---
    def save_messages(messages):
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
            "current_music": chat_state["current_music"]
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
                    messages[index] = chats.set_text(messages[index], new_text)
                    save_messages(messages)
                    return JsonResponse({"success": True})
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
                    save_messages(messages)
                    config = trackers.normalize_config(character.tracker_config)
                    return JsonResponse({"success": True, "swipes": chats.version_info(messages),
                                         "summary": chat_state["summary"], "summary_upto": chat_state["summary_upto"],
                                         "summary_data": summary_payload(),
                                         "trackers": trackers.normalize_state(chat_state["trackers"], config)})
                else:
                    return JsonResponse({"success": False, "error": "Invalid message index"})

            except (ValueError, KeyError) as e:
                return JsonResponse({"success": False, "error": "Invalid request data"})

        # --- 2. NEW: Magic Pencil (Expand) ---
        elif action == "expand":
            text = data.get("text", "")
            perspective = data.get("perspective", "The User")
            if not text: return JsonResponse({"success": False})

            # Context: Last 10 messages
            recent = messages[-10:]
            hist_txt = "\n".join([f"{m[0].upper()}: {m[2]}" for m in recent])

            sys_msg = (f"Rewrite this draft: '{text}'. Expand it into a full roleplay response as {perspective}. "
                       f"Match the tone of:\n{hist_txt}\nOutput ONLY the result.")

            try:
                text = ai_client.complete(request.user, "writing_tools", [{"role": "system", "content": sys_msg}])
                return JsonResponse({"success": True, "text": text})
            except ai_client.AIError as e:
                return JsonResponse({"success": False, "error": str(e)})

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
            chat_state["context_guides"] = data.get("guides", {})
            save_messages(messages) # Updates file
            return JsonResponse({"success": True})

        # ... inside chat view POST handler ...
        elif action in ("update_trackers", "save_trackers", "clear_trackers"):
            config = trackers.normalize_config(character.tracker_config)
            state = trackers.normalize_state(chat_state["trackers"], config)

            if action == "save_trackers":  # manual edits and locks from the panel
                state = trackers.normalize_state(
                    {"values": data.get("values"), "locks": data.get("locks"), "upto": state["upto"]}, config)
            elif action == "clear_trackers":
                state = {"values": {}, "locks": [], "upto": len(messages)}
            else:
                only = [t for t in data.get("only") or [] if isinstance(t, str)] or None
                if not trackers.enabled_trackers(config):
                    return JsonResponse({"success": False, "error": "No trackers are turned on for this character."})
                # Messages since the last run (at least the last 4, at most 16)
                upto = state["upto"] if isinstance(state["upto"], int) else 0
                recent = messages[min(upto, len(messages)):]
                recent = (messages[-4:] if len(recent) < 4 else recent)[-16:]
                user_name = request.user.name or request.user.username
                named = [(user_name if m[0] == "user" else character.name, m[2]) for m in recent]
                try:
                    reply_text = ai_client.complete(
                        request.user, "trackers",
                        trackers.update_messages(config, state, named, character.name, user_name, only),
                        temperature=0.2, response_format={"type": "json_object"})
                    update = trackers.parse_update(reply_text)
                except (ai_client.AIError, ValueError) as e:
                    return JsonResponse({"success": False, "error": str(e)})
                changed = trackers.apply_update(config, state, update, only)
                if not only:
                    state["upto"] = len(messages)

            chat_state["trackers"] = state
            chat_state["tracker_history"] = chats.add_snapshot(chat_state["tracker_history"], state, len(messages))
            save_messages(messages)
            return JsonResponse({"success": True, "state": state, "changed": changed if action == "update_trackers" else []})

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
                        new_text = _summarize(request.user, messages[start:stop], earlier)
                    except ai_client.AIError as e:
                        raise ValueError(str(e))
                    parts = sorted(parts + [{"text": new_text, "from": start, "to": stop}], key=lambda p: p["from"])
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
                    parts = [{"text": _summarize(request.user, messages[:count]), "from": 0, "to": count}]
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
                "photo_url": _photo(character, "photo", emo1),
                "photo_second": _photo(character, "photo_second", emo2 or "neutral")
                if (character.is_mult or char_count >= 2) else None,
                "swipes": chats.version_info(messages),
            })

        # --- 5. CONTINUE (Fixed) ---
        elif action == "continue":
            if not messages or messages[-1][0] != "assistant":
                return JsonResponse({"success": False, "error": "Can only continue the AI's last message."})

            # 1. Get the partial text and remove it from the history list used for the prompt
            last_text = messages[-1][2]
            # We slice everything EXCEPT the last message to give the AI context
            history_context = messages[:-1]

            # 2. Build the System Prompt manually for this specific task
            # We instruct the AI that it is continuing a specific text.
            system_instruction = (
                f"Your last response was cut-off. You are continuing the following text exactly where it stopped. "
                f"Do not repeat the beginning. Output only the continuation and give it an ending logical for the message.\n\n"
                f"TEXT SO FAR:\n{last_text}"
            )

            # 3. Construct API Messages
            api_messages = [{"role": "system", "content": system_instruction}]

            # Add recent history (last 5 messages) for context, so it remembers the topic
            for m in history_context[-5:]:
                api_messages.append({"role": "assistant" if m[0] == "assistant" else "user", "content": m[2]})

            try:
                # 4. Call API
                sampler_values = samplers.for_user(request.user)
                _, chat_model = ai_client.resolve(request.user, "chat")
                sampler_params, _ = samplers.to_api_params(sampler_values, chat_model)
                sampler_params.setdefault("max_tokens", 500)  # a continuation is short unless set
                new_chunk = ai_client.complete(request.user, "chat", api_messages, **sampler_params)

                # 5. Combine and Save
                full_text = last_text + " " + new_chunk
                messages[-1] = chats.set_text(messages[-1], full_text)
                save_messages(messages)

                return JsonResponse({"success": True, "reply": full_text})

            except Exception as e:
                print(f"Continue Error: {e}")
                return JsonResponse({"success": False, "error": str(e)})
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

            if (action == "chat" and user_message) or action == "regenerate":
                # Regenerate re-answers the existing last user message, so only chat adds one
                if action == "chat":
                    messages.append(("user", datetime.now().strftime("%H:%M"), user_message, "neutral", 1))

                lore_report = None
                context_dropped = 0

                # --- Prepare history for API ---
                api_messages = []

                # Add system message if character has one
                if hasattr(character, 'system_prompt') and character.system_prompt:
                    api_messages.append({"role": "system", "content": character.system_prompt})

                # Add conversation history
                for m in messages:
                    if m[0] in ("user", "assistant"):
                        api_messages.append({"role": m[0], "content": m[2]})

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
                        message=user_message if action == "chat" else None,
                        guidance=guidance,                             # <--- INJECTION 1
                        persistent_guides=chat_state["context_guides"],# <--- INJECTION 2
                        summary=chat_state["summary"])
                    lore_report = prompt.get("LoreReport")


                    # --- Build the request from the active preset ---
                    preset = presets.normalize(presets.get_active(request.user).data)
                    _, chat_model = ai_client.resolve(request.user, "chat")
                    built = presets.assemble(preset, prompt_slots(request.user, character, prompt),
                                             api_messages, prompt_names(request.user, character), chat_model)
                    context_dropped = built["dropped"]
                    # Stream when the page asks for it and the preset allows it
                    streaming = bool(data.get("stream")) and preset["options"].get("streaming", True)
                    if not streaming:
                        reply = ai_client.complete(request.user, "chat", built["messages"], **built["params"])

                except ai_client.AIError as e:
                    # Keep the user's message so they can press Regenerate (and the old reply, if regenerating)
                    if regen_from:
                        messages.append(regen_from)
                    save_messages(messages)
                    return JsonResponse({"error": str(e)}, status=502)
                except Exception as e:
                    print(f"Error generating reply: {traceback.format_exc()}")
                    if regen_from:
                        messages.append(regen_from)
                    save_messages(messages)
                    return JsonResponse({"error": f"Something went wrong while building the prompt: {e}"}, status=500)

                def finish_reply(reply):
                    """Emotion, saving, voice and the summary/tracker flags, once the reply is complete."""
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

                        print(f"[CLASSIFICATION] Speaker: {speaker} | Emo1: {emotion_char_1} | Emo2: {emotion_char_2}")

                        # Logic: Determine layout (char_count)
                        # 1 = Main Only, 2 = Both, 3 = Second Only
                        if character.is_mult:
                            if speaker == "both": char_count = 2
                            elif speaker == "2": char_count = 3
                            else: char_count = 1
                        else:
                            char_count = 1

                    except Exception as e:
                        print(f"Classification failed: {e}")
                        emotion_char_1 = "neutral"

                    # Store emotions as "happy|sad" string
                    final_emotion_str = f"{emotion_char_1}|{emotion_char_2}"
                    new_message = ("assistant", datetime.now().strftime("%H:%M"), reply, final_emotion_str, char_count)
                    messages.append(chats.add_version(regen_from, new_message) if regen_from else new_message)

                    photo_url = _photo(character, "photo", emotion_char_1)
                    photo_second = (_photo(character, "photo_second", emotion_char_2)
                                    if (character.is_mult or char_count >= 2) else None)

                    save_messages(messages)

                    # --- Voice (ElevenLabs), only if the user has a key ---
                    audio_path = ""
                    ELEVENLABS_API_KEY = get_elevenlabs_key(request.user)
                    if ELEVENLABS_API_KEY:
                        try:
                            audio_path = narrate_text_backend(
                                reply,
                                request.user,
                                character.name,
                                ELEVENLABS_API_KEY,
                                narrator_voice_id=character.eleven_voice_narr_id or None,
                                character_voice_id=character.eleven_voice_char_id or None,
                                second_character_voice_id=character.eleven_voice_second_id or None,
                                output_dir="media/audio_files",
                                is_mult=character.is_mult or (char_count > 1),
                            )
                        except Exception as e:
                            print(f"Voice generation failed: {e}")

                    # Automatic summary: tell the page to run one in the background
                    summary_task = ai_client.get_task_setting(request.user, "summary")
                    summarized = chat_state["summary_upto"] or 0
                    summary_due = (summary_task.mode == summary_task.MODE_AUTO and not chat_state["summary_paused"]
                                   and len(messages) - summarized >= summary_task.interval)

                    # Trackers: same idea, if any tracker is on for this character
                    tracker_task = ai_client.get_task_setting(request.user, "trackers")
                    tracked = (chat_state["trackers"] or {}).get("upto") or 0
                    trackers_due = (bool(trackers.enabled_trackers(trackers.normalize_config(character.tracker_config)))
                                    and tracker_task.mode == tracker_task.MODE_AUTO
                                    and len(messages) - tracked >= tracker_task.interval)

                    return {
                        "reply": reply,
                        "emotion": final_emotion_str,
                        "photo_url": photo_url,
                        "photo_second": photo_second,
                        "char_count": char_count,
                        "audio_url": audio_path,
                        "lore": lore_report,
                        "summary_due": summary_due,
                        "trackers_due": trackers_due,
                        "context_dropped": context_dropped,
                        "swipes": chats.version_info(messages),
                    }

                if not streaming:
                    return JsonResponse(finish_reply(reply))

                def stream_reply():
                    """NDJSON lines: {"type": "delta", "text"} ..., then {"type": "done", ...} or {"type": "error"}."""
                    parts, finished = [], False

                    def keep_partial():
                        # Keep whatever arrived (Stop button, closed tab or a broken stream)
                        text = "".join(parts).strip()
                        if text:
                            partial = ("assistant", datetime.now().strftime("%H:%M"), text, "neutral|neutral", 1)
                            messages.append(chats.add_version(regen_from, partial) if regen_from else partial)
                        elif regen_from:
                            messages.append(regen_from)  # nothing new arrived: keep the old reply
                        save_messages(messages)

                    try:
                        try:
                            for chunk in ai_client.stream(request.user, "chat", built["messages"], **built["params"]):
                                parts.append(chunk)
                                yield json.dumps({"type": "delta", "text": chunk}, ensure_ascii=False) + "\n"
                        except ai_client.AIError as e:
                            keep_partial()
                            finished = True
                            yield json.dumps({"type": "error", "error": str(e), "kept": bool("".join(parts).strip())}) + "\n"
                            return
                        payload = finish_reply("".join(parts))
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
    print(photo_url)

    user_avatar = None
    if hasattr(request.user, 'photo') and request.user.photo:
        user_avatar = request.user.photo.url

    context = {
        "messages": [m[:5] for m in messages],  # the template shows the version on screen
        "swipes": chats.version_info(messages),
        "character": character,
        "photo_url": photo_url,
        "photo_second": photo_second,
        "char_count": char_count,
        "photo_neutral": photo_url,
        "summary": chat_state["summary"],
        "summary_upto": chat_state["summary_upto"],
        "summary_data": summary_payload(),
        "context_guides": json.dumps(chat_state["context_guides"]),
        "current_bg": chat_state["current_bg"],
        "current_music": json.dumps(chat_state["current_music"]),
        "user_avatar": user_avatar,
        "trackers_data": _tracker_page_data(request.user, character, chat_state["trackers"]),
        "stream_replies": presets.normalize(presets.get_active(request.user).data)["options"]["streaming"],
        "chat": chat_obj,
        "chat_list": chats.summary_list(character, chat_obj.id),
    }

    return render(request, "mainapp/chat_page.html", context)


def prompt_names(user, character):
    """{{char}} and {{user}}: the persona name wins over the account name."""
    return {"char": character.name or "Character",
            "user": getattr(user, "persona_name", None) or user.name or user.username}


def prompt_slots(user, character, prompt):
    """Text for the preset's slots (markers), from the character, persona and build_ai_request."""
    extra = prompt.get("SystemPrompts", {})
    return {
        "char_description": character.description or "",
        "char_personality": character.creator_notes or "",
        "scenario": character.scenario or "",
        "persona": getattr(user, "persona_description", None) or "",
        "lore": extra.get("WorldInfo", ""),
        "summary": extra.get("StorySummary", ""),
        "trackers": extra.get("StoryState", ""),
        "world_context": extra.get("WorldContext", ""),
        "director_note": extra.get("DirectorNote", ""),
    }


def _tracker_page_data(user, character, raw_state):
    """Everything the chat page's tracker HUD and panel need."""
    config = trackers.normalize_config(character.tracker_config)
    task = ai_client.get_task_setting(user, "trackers")
    return {
        "panels": trackers.PANELS,
        "specs": [trackers.tracker_spec(t["id"], config) for t in trackers.TRACKERS],
        "config": config,
        "state": trackers.normalize_state(raw_state, config),
        "schedule": {"mode": task.mode, "interval": task.interval},
        "setup_url": reverse("tracker_setup", args=[character.slug]),
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
    built = presets.assemble(preset, prompt_slots(user, character, prompt), history,
                             prompt_names(user, character), model)
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
                                        "options": data.get("options", current["options"])})
            # Samplers are edited on their own page; SillyTavern extras are never edited here
            edited["samplers"], edited["extras"] = current["samplers"], current["extras"]
            obj.data = edited
            obj.save(update_fields=["data", "time_update"])
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
    }})


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
            "locked": sorted(samplers.locked_for_model(model)),
            "all_locked": sorted(samplers.SAMPLING_LOCKED),
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
        character.tracker_config = trackers.normalize_config(data)
        character.save(update_fields=["tracker_config"])
        return JsonResponse({"status": "ok", "config": character.tracker_config})

    return render(request, "mainapp/tracker_setup.html", {
        "character": character,
        "setup_data": {
            "panels": trackers.PANELS,
            "trackers": trackers.TRACKERS,
            "config": trackers.normalize_config(character.tracker_config),
            "field_types": trackers.FIELD_TYPES,
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
        # повертаємо тільки персонажів, створених поточним користувачем
        return Character.objects.filter(author=self.request.user)


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
        print("Форма валідна!")
        print("Дані форми:", form.cleaned_data)
        a = form.save(commit=False)
        a.author = self.request.user
        # Формуємо slug: username + "-" + slugified name
        username = self.request.user.username
        base_slug = slugify(a.name)
        a.slug = f"{username}-{base_slug}"
        a.save()
        print("Збережено об'єкт:", a)
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


def page_not_found(request, exception):
    print("Hi, hi")
    return HttpResponseNotFound("<h1>Сторінку не знайдено. Вибачте, будь ласка!!!</h1>")


# In mainapp/views.py

@login_required
def get_media_resources(request):
    # Define paths inside your MEDIA_ROOT
    bg_dir = os.path.join(settings.MEDIA_ROOT, "backgrounds")
    music_dir = os.path.join(settings.MEDIA_ROOT, "music")

    # Auto-create directories so you don't get FileNotFoundError
    os.makedirs(bg_dir, exist_ok=True)
    os.makedirs(os.path.join(bg_dir, "custom"), exist_ok=True)
    os.makedirs(music_dir, exist_ok=True)
    os.makedirs(os.path.join(music_dir, "custom"), exist_ok=True)

    def get_files(directory, url_prefix):
        files = []
        if os.path.exists(directory):
            # 1. Scan main folder
            for f in os.listdir(directory):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp3', '.wav', '.ogg')):
                    files.append({"name": f, "url": f"{settings.MEDIA_URL}{url_prefix}/{f}"})

            # 2. Scan 'custom' subfolder (user uploads)
            custom_dir = os.path.join(directory, "custom")
            if os.path.exists(custom_dir):
                for f in os.listdir(custom_dir):
                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.mp3', '.wav', '.ogg')):
                        files.append({"name": f"Custom: {f}", "url": f"{settings.MEDIA_URL}{url_prefix}/custom/{f}"})
        return sorted(files, key=lambda x: x['name'])

    if request.method == "POST" and request.FILES:
        try:
            file_type = request.POST.get("type")
            if "file" in request.FILES:
                f = request.FILES["file"]
                target_dir = bg_dir if file_type == "bg" else music_dir
                prefix = "backgrounds" if file_type == "bg" else "music"

                # Save to 'custom' subfolder to keep main folder clean
                custom_path = os.path.join(target_dir, "custom", f.name)
                with open(custom_path, 'wb+') as dest:
                    for chunk in f.chunks(): dest.write(chunk)

                return JsonResponse({
                    "success": True,
                    "url": f"{settings.MEDIA_URL}{prefix}/custom/{f.name}",
                    "name": f"Custom: {f.name}"
                })
        except Exception as e:
            return JsonResponse({"success": False, "error": str(e)})

    # Return lists for GET requests
    return JsonResponse({
        "backgrounds": get_files(bg_dir, "backgrounds"), 
        "music": get_files(music_dir, "music")
    })
