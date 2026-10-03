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
    if not character.initial_message:
        return []
    return [["assistant", datetime.now().strftime("%H:%M"), character.initial_message, "neutral", 1]]


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

def _extras(message):
    return message[5] if len(message) > 5 and isinstance(message[5], dict) else {}


def _version(message):
    return {"text": message[2], "time": message[1], "emotion": message[3], "char_count": message[4]}


def add_version(previous, message):
    """`message` replaces `previous` as a new swipe; the earlier versions are kept."""
    versions = list(_extras(previous).get("swipes") or [_version(previous)])
    versions.append(_version(message))
    return tuple(message[:5]) + ({"swipes": versions, "swipe": len(versions) - 1},)


def choose_version(message, index):
    versions = _extras(message).get("swipes") or []
    if not 0 <= index < len(versions):
        raise IndexError("No such version.")
    v = versions[index]
    return (message[0], v["time"], v["text"], v["emotion"], v["char_count"],
            {"swipes": versions, "swipe": index})


def set_text(message, text):
    """Edit the shown text (and the shown swipe, so flipping away and back keeps the edit)."""
    extras = _extras(message)
    edited = (message[0], message[1], text, message[3], message[4])
    if extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        versions[extras.get("swipe", 0)]["text"] = text
        edited += ({"swipes": versions, "swipe": extras.get("swipe", 0)},)
    return edited


def version_info(messages):
    """Swipe counter for the last message, if it's the AI's: {"count", "current"}."""
    if not messages or messages[-1][0] != "assistant":
        return None
    extras = _extras(messages[-1])
    versions = extras.get("swipes") or []
    return {"count": max(len(versions), 1), "current": extras.get("swipe", 0) if versions else 0}
