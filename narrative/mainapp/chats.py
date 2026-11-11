"""
Chats: a character can have many conversations (and, later, branches of them).
Each chat is a JSON file: {"messages": [...], "summary": ..., "trackers": ..., ...}.
"""
import json
import logging
import os
import shutil
import threading
import uuid
from datetime import datetime

from django.core.files.base import ContentFile
from django.http import Http404

from mainapp.models import Chat


# --- Keeping chat files safe ---
# A chat file is never written in place: the new version goes to a temporary file that then replaces the old one
# in one step, so a crash or a restart mid-save can't leave half a file, and a request reading at the same moment
# always sees a whole one. The last few versions are kept beside it (.bak1 newest), and a version with fewer
# messages than the one before keeps that one as .shrunk. A file that can't be read is never taken for an empty
# chat (that used to reset a whole chat to its greeting): the newest readable backup is used, else ChatUnreadable.
BACKUPS = 3
_locks = {}
_locks_guard = threading.Lock()


class ChatUnreadable(Exception):
    """The chat's file and all its backups exist but can't be read: nothing may be saved over them."""


def _lock(path):
    with _locks_guard:
        return _locks.setdefault(path, threading.RLock())


def _load(path):
    with open(path, "rb") as f:
        data = json.loads(f.read().decode("utf-8"))
    if not isinstance(data, (dict, list)):
        raise ValueError("not a chat")
    return data


def backup_paths(path):
    return [f"{path}.bak{i}" for i in range(1, BACKUPS + 1)] + [f"{path}.shrunk"]


def load_path(path):
    """The chat file's contents (a dict, or a bare list for very old files); None when there's no file at all.
    A broken file falls back to its newest readable backup; raises ChatUnreadable when none can be read."""
    candidates = [path] + backup_paths(path)[:BACKUPS]
    if not any(os.path.exists(p) for p in candidates):
        return None
    for p in candidates:
        if os.path.exists(p):
            try:
                data = _load(p)
            except (OSError, ValueError):
                continue
            if p != path:
                logging.getLogger(__name__).error("Chat file %s couldn't be read; using its backup %s", path, p)
            return data
    raise ChatUnreadable(path)


def _count(data):
    msgs = data.get("messages") if isinstance(data, dict) else data
    return len(msgs) if isinstance(msgs, list) else 0


def save_path(path, data):
    """Saves a chat file safely (see above)."""
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    with _lock(path):
        tmp = f"{path}.tmp-{uuid.uuid4().hex}"
        with open(tmp, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        if os.path.exists(path):
            try:
                before = _load(path)
            except (OSError, ValueError):  # a broken file is kept aside, never rotated into the backups
                os.replace(path, f"{path}.broken-{datetime.now():%Y%m%d-%H%M%S}")
            else:
                if _count(before) > _count(data):  # fewer messages than before (a deletion, or worse): keep it
                    shutil.copyfile(path, f"{path}.shrunk")
                baks = backup_paths(path)[:BACKUPS]
                for older, newer in zip(reversed(baks[1:]), reversed(baks[:-1])):
                    if os.path.exists(newer):
                        os.replace(newer, older)
                shutil.copyfile(path, baks[0])
        os.replace(tmp, path)


def read(chat):
    """The chat file as a dict (very old files were a bare list of messages). Raises ChatUnreadable rather than
    pretending a broken chat is empty."""
    if not chat.log_file:
        return {"messages": []}
    try:
        path = chat.log_file.path
    except (NotImplementedError, ValueError, AttributeError):
        return {"messages": []}
    data = load_path(path)
    if data is None:
        return {"messages": []}
    return data if isinstance(data, dict) else {"messages": data}


def write(chat, data):
    if chat.log_file:
        save_path(chat.log_file.path, data)
        chat.save(update_fields=["time_update"])
    else:
        content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
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


def greeting_texts(character):
    return [t for t in [character.initial_message, *(getattr(character, "alternate_greetings", None) or [])]
            if isinstance(t, str) and t.strip()]


def refresh_greeting(messages, character, name, old_names):
    """The opening message with {{user}} filled in as `name`, when it still reads exactly as the card's greeting
    filled with one of `old_names` (the login, say, before they made a persona). Edited greetings are left alone.
    Returns the messages, changed or not, and whether they changed."""
    from mainapp.cards import fill_names
    if not messages or messages[0][0] != "assistant" or not name:
        return messages, False
    raws = greeting_texts(character)
    if not raws or not any("{{user}}" in r.lower() or "<user>" in r.lower() for r in raws):
        return messages, False
    olds = [o for o in dict.fromkeys(old_names) if o and o != name]

    def refill(text):
        for raw in raws:
            if any(text == fill_names(raw, character.name, old) for old in olds):
                return fill_names(raw, character.name, name)
        return text

    first = list(messages[0])
    changed = False
    new_text = refill(first[2])
    if new_text != first[2]:
        first[2], changed = new_text, True
    extras = _extras(messages[0])
    if extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        for v in versions:
            fixed = refill(v.get("text", ""))
            if fixed != v.get("text"):
                v["text"], changed = fixed, True
        if changed:
            first = first[:5] + [{**extras, "swipes": versions}]
    if not changed:
        return messages, False
    return [tuple(first), *messages[1:]], True


def create(character, title=None, data=None, parent=None, branch_point=None):
    count = character.chats.count()
    chat = Chat.objects.create(character=character, title=title or f"Chat {count + 1}",
                               parent=parent, branch_point=branch_point)
    write(chat, data if data is not None else {"messages": greeting(character)})
    return chat


MAX_IMPORT_MESSAGES = 5000
MAX_IMPORT_TEXT = 200000


def clean_import(raw):
    """Messages from an imported chat file, in this app's shape: its own export / the rescue snippet
    ({"messages": [[role, time, text, emotion, char_count, {"note": true}?], ...]} or the bare list), or
    SillyTavern's (a list of {"is_user", "mes", "send_date"}; the chats page reads .jsonl lines into one).
    Only plain messages and the director's-note mark come in. Raises ValueError when nothing usable is there."""
    items = raw.get("messages") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("That file doesn't hold a chat.")
    out = []
    for m in items[:MAX_IMPORT_MESSAGES]:
        if isinstance(m, (list, tuple)) and len(m) >= 3:
            role, time, text = m[0], m[1], m[2]
            emotion = m[3] if len(m) > 3 else "neutral"
            count = m[4] if len(m) > 4 else 1
            note = len(m) > 5 and isinstance(m[5], dict) and bool(m[5].get("note"))
        elif isinstance(m, dict) and "mes" in m:  # SillyTavern
            if m.get("is_system"):
                continue
            role, time, text = ("user" if m.get("is_user") else "assistant"), str(m.get("send_date") or ""), m.get("mes")
            emotion, count, note = "neutral", 1, False
        else:
            continue
        if role not in ("user", "assistant") or not isinstance(text, str) or not text.strip():
            continue
        msg = [role, str(time or "")[:40], text[:MAX_IMPORT_TEXT], str(emotion or "neutral")[:30],
               count if isinstance(count, int) and 1 <= count <= 4 else 1]
        if note and role == "user":
            msg.append({"note": True})
        out.append(msg)
    if not out:
        raise ValueError("No messages found in that file.")
    return out


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
        try:
            messages = read(chat).get("messages", [])
        except ChatUnreadable:  # still listed (it can be recovered), just without a preview
            messages = []
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
        for extra in backup_paths(chat.log_file.path):  # its backups go with it
            if os.path.exists(extra):
                os.remove(extra)
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
VERSION_KEYS = ("reasoning", "game", "audio", "polish", "directed", "condensed", "translation")


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
    # A swipe keeps its own copy of these: the one on screen gets the change too, so flipping away and back keeps
    # it (a translation or a polish that arrived after the version was made)
    if key in VERSION_KEYS and extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        current = extras.get("swipe", 0)
        if 0 <= current < len(versions) and versions[current].get("text") == message[2]:
            if value:
                versions[current][key] = value
            else:
                versions[current].pop(key, None)
            extras["swipes"] = versions
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


def condensed_of(message):
    """The short version the AI gets instead of this message, if it's still about the text on screen."""
    rec = _extras(message).get("condensed") or {}
    return rec.get("text") if rec.get("text") and rec.get("of") == message[2] else ""


def with_condensed(message, text):
    """Keeps a condensed version for the AI (also in the shown swipe). An empty text drops it."""
    rec = {"text": text, "of": message[2]} if text else None
    message = _with(message, "condensed", rec)
    extras = dict(_extras(message))
    if extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        if rec:
            versions[extras.get("swipe", 0)]["condensed"] = rec
        else:
            versions[extras.get("swipe", 0)].pop("condensed", None)
        extras["swipes"] = versions
        message = tuple(message[:5]) + (extras,)
    return message


def prompt_text(message):
    """What the AI gets for a message: its condensed version when there is one, else the text."""
    return condensed_of(message) or message[2]


def is_note(message):
    """A director's note: a message of its own from them (role "user"), outside the story. The AI reads it
    framed as a direction (views._history); it's edited, deleted and regenerated like any message."""
    return message[0] == "user" and bool(_extras(message).get("note"))


def as_note(message):
    return _with(message, "note", True)


def directed_of(message):
    """The director's note that steered this version of the reply, if any."""
    return _extras(message).get("directed") or ""


def with_directed(message, note):
    return _with(message, "directed", note)


def polish_of(message):
    """Bulba's polish on the version on screen, if its text hasn't changed since: {"original", "fixes"}."""
    rec = _extras(message).get("polish") or {}
    return rec if rec.get("original") and rec.get("text") == message[2] else None


def with_polish(message, text, rec):
    """The message with its polished text, the original kept (also in its swipe). rec=None drops it."""
    message = set_text(message, text)
    rec = {**rec, "text": text} if rec else None
    message = _with(message, "polish", rec)
    extras = dict(_extras(message))
    if extras.get("swipes"):
        versions = [dict(v) for v in extras["swipes"]]
        if rec:
            versions[extras.get("swipe", 0)]["polish"] = rec
        else:
            versions[extras.get("swipe", 0)].pop("polish", None)
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
