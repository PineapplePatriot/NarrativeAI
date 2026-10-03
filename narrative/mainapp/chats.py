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
