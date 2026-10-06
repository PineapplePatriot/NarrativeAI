"""
Chats: a character can have many conversations (and, later, branches of them).
Each chat is a JSON file: {"messages": [...], "summary": ..., "trackers": ..., ...}.
"""
import json
import os
import uuid
from datetime import datetime

from django.core.files.base import ContentFile
from django.http import Http404

from mainapp.models import Chat


def read(chat):
    """The chat file as a dict (very old files were a bare list of messages)."""
    try:
        with chat.log_file.open("rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError, AttributeError):
        return {"messages": []}
    return data if isinstance(data, dict) else {"messages": data}


def write(chat, data):
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    if chat.log_file:
        with open(chat.log_file.path, "wb") as f:
            f.write(content)
        chat.save(update_fields=["time_update"])
    else:
        chat.log_file.save(f"{uuid.uuid4().hex}.json", ContentFile(content), save=True)


def greeting(character):
    """The opening message; a card's alternate greetings become its other swipes."""
    from mainapp.cards import fill_names, user_name
    texts = [t for t in [character.initial_message, *(getattr(character, "alternate_greetings", None) or [])]
             if isinstance(t, str) and t.strip()]
    # Cards write {{user}}/{{char}} in greetings; the chat stores the names, as SillyTavern shows them
    texts = [fill_names(t, character.name, user_name(character.author)) for t in texts]
    if not texts:
        return []
    now = datetime.now().strftime("%H:%M")
    message = ["assistant", now, texts[0], "neutral", 1]
    if len(texts) > 1:
        versions = [{"time": now, "text": t, "emotion": "neutral", "char_count": 1} for t in texts]
        message.append({"swipes": versions, "swipe": 0})
    return [message]


def create(character, title=None, data=None, parent=None, branch_point=None):
    count = character.chats.count()
    chat = Chat.objects.create(character=character, title=title or f"Chat {count + 1}",
                               parent=parent, branch_point=branch_point)
    write(chat, data if data is not None else {"messages": greeting(character)})
    return chat


def current(character, chat_id=None):
    """The chat to open: the one asked for (must belong to the character), else the most recent."""
    if chat_id:
        chat = character.chats.filter(id=chat_id).first()
        if chat is None:
            raise Http404("No such chat.")
        return chat
    chat = character.chats.first()
    if chat:
        return chat
    # Characters made before multiple chats (or by older code) may still have a single log file
    if character.chat_log_file:
        return Chat.objects.create(character=character, title="Chat 1", log_file=character.chat_log_file.name)
    return create(character, "Chat 1")


def summary_list(character, current_id=None):
    out = []
    for chat in character.chats.all():
        messages = read(chat).get("messages", [])
        last = next((m for m in reversed(messages) if isinstance(m, (list, tuple)) and len(m) > 2), None)
        preview = (last[2] if last else "")[:90]
        out.append({
            "id": chat.id, "title": chat.title, "count": len(messages), "preview": preview,
            "updated": chat.time_update.strftime("%Y-%m-%d %H:%M"), "current": chat.id == current_id,
            "created": chat.time_create.strftime("%Y-%m-%d"),
            "parent": chat.parent.title if chat.parent else None, "branch_point": chat.branch_point,
        })
    return out


def delete(chat):
    if chat.log_file and os.path.exists(chat.log_file.path):
        # Character.chat_log_file may still point at the same file (from before multiple chats)
        character = chat.character
        if character.chat_log_file and character.chat_log_file.name == chat.log_file.name:
            character.chat_log_file = None
            character.save(update_fields=["chat_log_file"])
        os.remove(chat.log_file.path)
    chat.delete()


# --- Swipes: alternative versions of an AI reply ---
# A message is [role, time, text, emotion, char_count] plus an optional 6th part
# {"swipes": [{"text", "time", "emotion", "char_count"}, ...], "swipe": <shown>}.
# The first five parts always mirror the version on screen, so everything else
# (the prompt, lorebook, summary, trackers) can ignore swipes entirely.
# The 6th part may also hold "reasoning": what a thinking model thought before that reply (each swipe
# keeps its own). It's shown folded under "Thoughts" and never sent back to the model.

def _extras(message):
    return message[5] if len(message) > 5 and isinstance(message[5], dict) else {}


# Things each version (swipe) of a reply keeps for itself: the model's thoughts, and the dice and
# inventory changes it made (see mainapp/game.py), so flipping swipes flips them too
VERSION_KEYS = ("reasoning", "game", "audio")


def _version(message):
    v = {"text": message[2], "time": message[1], "emotion": message[3], "char_count": message[4]}
    for key in VERSION_KEYS:
        if _extras(message).get(key):
            v[key] = _extras(message)[key]
    return v


def _with(message, key, value):
    extras = dict(_extras(message))
    if value:
        extras[key] = value
    else:
        extras.pop(key, None)
    return tuple(message[:5]) + ((extras,) if extras else ())


def reasoning_of(message):
    return _extras(message).get("reasoning") or ""


def with_reasoning(message, reasoning):
    """The message with what the model thought before it (kept out of every prompt)."""
    return _with(message, "reasoning", reasoning)


def game_of(message):
    return _extras(message).get("game") or []


def with_game(message, ops):
    """The message with the dice rolls and inventory changes made while writing it."""
    return _with(message, "game", list(ops or []))


def audio_of(message):
    """The saved recording of the version on screen, if its text hasn't changed since: {"url", "text"}."""
    audio = _extras(message).get("audio") or {}
    return audio if audio.get("url") and audio.get("text") == message[2] else None


def with_audio(message, audio):
    """Keeps a recording with the version on screen (and in its swipe, so flipping back keeps it)."""
    message = _with(message, "audio", audio)
    extras = dict(_extras(message))
    if extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        versions[extras.get("swipe", 0)]["audio"] = audio
        extras["swipes"] = versions
        message = tuple(message[:5]) + (extras,)
    return message


def add_version(previous, message):
    """`message` replaces `previous` as a new swipe; the earlier versions are kept."""
    versions = list(_extras(previous).get("swipes") or [_version(previous)])
    versions.append(_version(message))
    extras = {"swipes": versions, "swipe": len(versions) - 1}
    extras.update({k: _extras(message)[k] for k in VERSION_KEYS if _extras(message).get(k)})
    return tuple(message[:5]) + (extras,)


def choose_version(message, index):
    versions = _extras(message).get("swipes") or []
    if not 0 <= index < len(versions):
        raise IndexError("No such version.")
    v = versions[index]
    extras = {"swipes": versions, "swipe": index}
    extras.update({k: v[k] for k in VERSION_KEYS if v.get(k)})
    return (message[0], v["time"], v["text"], v["emotion"], v["char_count"], extras)


def set_text(message, text):
    """Edit the shown text (and the shown swipe, so flipping away and back keeps the edit)."""
    extras = dict(_extras(message))
    edited = (message[0], message[1], text, message[3], message[4])
    if extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        versions[extras.get("swipe", 0)]["text"] = text
        extras["swipes"] = versions
    return edited + ((extras,) if extras else ())


def version_info(messages):
    """Swipe counter for the last message, if it's the AI's: {"count", "current"}."""
    if not messages or messages[-1][0] != "assistant":
        return None
    extras = _extras(messages[-1])
    versions = extras.get("swipes") or []
    return {"count": max(len(versions), 1), "current": extras.get("swipe", 0) if versions else 0}


# --- Summary pieces: each summary run remembers which messages it covered ---
# "summary_parts": [{"text", "from", "to"}] covers messages[from:to]. "summary" and
# "summary_upto" are still written (joined text / end of the last piece) for older code.

def summary_parts(data, message_count):
    parts = data.get("summary_parts")
    if isinstance(parts, list):
        return [p for p in parts if isinstance(p, dict) and p.get("text")]
    # Chats from before pieces: the whole summary is one piece
    if data.get("summary"):
        upto = data.get("summary_upto")
        return [{"text": data["summary"], "from": 0,
                 "to": upto if isinstance(upto, int) else message_count}]
    return []


def summary_text(parts):
    return "\n\n".join(p["text"] for p in parts)


def summary_upto(parts):
    return parts[-1]["to"] if parts else 0


def parts_within(parts, count):
    """The pieces that only cover the first `count` messages (deleting messages drops the rest)."""
    return [p for p in parts if p["to"] <= count]


# --- Tracker snapshots: the tracker state after each update, by message count ---
MAX_SNAPSHOTS = 40


def add_snapshot(history, state, at):
    history = [s for s in history if s.get("at") != at]
    history.append({"at": at, "state": json.loads(json.dumps(state))})
    return history[-MAX_SNAPSHOTS:]


def trackers_at(history, current_state, count):
    """Tracker state as it was with `count` messages, and the snapshots up to then."""
    kept = [s for s in history if isinstance(s, dict) and s.get("at", 0) <= count]
    if kept:
        return json.loads(json.dumps(kept[-1]["state"])), kept
    if history:  # snapshots exist, but all are from later messages
        return {"values": {}, "locks": [], "upto": 0}, []
    # No snapshots (older chats): keep the current state unless it was built from later messages
    upto = (current_state or {}).get("upto") or 0
    return (current_state if upto <= count else {"values": {}, "locks": [], "upto": 0}), []


def first_uncovered(parts, count):
    """Where the next summary starts: after the last piece (gaps left by deleted pieces come first)."""
    covered = 0
    for p in sorted(parts, key=lambda p: p["from"]):
        if p["from"] > covered:
            return covered
        covered = max(covered, p["to"])
    return min(covered, count)
