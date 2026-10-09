"""
Bulba Watch: Bulba quietly keeps an eye on a chat and speaks up only when something keeps happening.

- Every few replies, a cheap model (Bulba's own) reads the latest ones and notes slips it can quote:
  the same sentence starts, metaphors stretched too far, forced callbacks, unearned depth... (the list
  is in data/bulba/watch.md). One slip is nothing; a slip in several of the last few replies is a
  habit, and that's when the 🥔 gets a badge. It also notes where a slip seems to come from (the model,
  the setup, or the person's own messages) and learns what they like from the replies they rewrite or edit.
- How long they take to reply, against what's usual for them (worked out here, no AI): much slower
  than usual for a while can mean they're stuck; much faster with very short messages, that the story
  stopped pulling them in. Either way Bulba offers help.

On by default (the "watch" task on the Connections model, which the Extras page switches); each chat can
turn it off. What it found lives on the chat (Chat.watch); what it learned about the person, on their
ChatSettings.watch.
"""
import json
import math
import re
import time
import uuid
from pathlib import Path

from mainapp import ai_client

INSTRUCTIONS = Path(__file__).resolve().parent.parent / "data" / "bulba" / "watch.md"

EVERY = 5          # read after this many new replies
WINDOW = 6         # a habit is judged over the last this-many replies read...
THRESHOLD = 3      # ...and needs to show up in at least this many of them
MAX_READ = 8       # replies sent to the reader at most (after a long pause in reading)
LOG_MAX = 120
TASTE_MAX = 20

# Reply pace
BREAK = 20 * 60    # a longer gap is a break, not a slow reply
PACE_MIN = 15      # replies timed before the person's usual pace counts
PACE_RUN = 3       # this many unusual replies in a row
PACE_Z = 1.5
PACE_COOLDOWN = 20  # replies between two pace notes in one chat

LABELS = {
    "same_openings": "Sentences keep starting the same way",
    "overworked_metaphor": "Metaphors stretched too far",
    "forced_callback": "Leaning on earlier scenes instead of describing this one",
    "unearned_depth": "Big, wise lines the moment hasn't earned",
    "overexplaining": "Explaining what you already got",
    "detail_fixation": "Lingering on small details",
    "out_of_character": "{char} acting out of character",
    "echoing_user": "Your words repeated back to you",
    "writing_for_user": "Deciding things for your character",
    "pet_phrase": "The same pet phrases",
}
CAUSES = ("model", "setup", "their_messages")


# ---------------------------------------------------------------------------
# Where things are kept
# ---------------------------------------------------------------------------

def is_on(user):
    return ai_client.is_enabled(user, "watch")


def set_on(user, on):
    setting = ai_client.get_task_setting(user, "watch")
    setting.enabled = bool(on)
    setting.save()


def user_data(user):
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).first()
    data = dict(obj.watch or {}) if obj else {}
    data.setdefault("muted", [])
    data.setdefault("taste", [])
    data.setdefault("pace", {"n": 0, "mean": 0.0, "m2": 0.0})
    return data


def save_user_data(user, data):
    from mainapp.models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    obj.watch = data
    obj.save(update_fields=["watch"])


def chat_data(chat_obj):
    chat_obj.refresh_from_db(fields=["watch"])  # another request may have changed it
    data = dict(chat_obj.watch or {})
    for key, empty in (("log", []), ("checked", []), ("notices", []), ("signals", []), ("pace", {})):
        data.setdefault(key, empty)
    data.setdefault("upto", 0)
    return data


def save_chat_data(chat_obj, data):
    data["log"] = data["log"][-LOG_MAX:]
    data["checked"] = data["checked"][-30:]
    data["notices"] = data["notices"][-20:]
    chat_obj.watch = data
    type(chat_obj).objects.filter(id=chat_obj.id).update(watch=data)


# ---------------------------------------------------------------------------
# Reply pace (no AI)
# ---------------------------------------------------------------------------

def _words(text):
    return len(str(text or "").split())


def on_reply_done(user, chat_obj, reply, now=None):
    if not is_on(user):  # off means nothing is collected
        return
    data = chat_data(chat_obj)
    data["pace"].update({"reply_at": now or time.time(), "reply_words": _words(reply)})
    save_chat_data(chat_obj, data)


def on_user_message(user, chat_obj, text, now=None):
    """Times their reply against what's usual for them. Returns a new notice, or None."""
    if not is_on(user):
        return None
    data = chat_data(chat_obj)
    pace = data["pace"]
    reply_at = pace.pop("reply_at", None)
    if reply_at is None:
        save_chat_data(chat_obj, data)
        return None
    gap = (now or time.time()) - reply_at
    if not 1 <= gap <= BREAK:
        pace["recent"] = []  # a break: start counting again
        save_chat_data(chat_obj, data)
        return None
    words = _words(text)
    # Reading their reply and typing theirs take time; what's left is the part that says something
    expected = 8 + pace.get("reply_words", 0) / 4 + words * 1.5
    x = math.log(gap / expected)
    mine = user_data(user)
    stats = mine["pace"]
    notice = None
    if stats["n"] >= PACE_MIN:
        sd = max(math.sqrt(stats["m2"] / (stats["n"] - 1)), 0.25)
        recent = (pace.get("recent") or [])[-(PACE_RUN - 1):] + [{"z": (x - stats["mean"]) / sd, "words": words}]
        pace["recent"] = recent
        pace["since_notice"] = pace.get("since_notice", PACE_COOLDOWN) + 1
        if len(recent) == PACE_RUN and pace["since_notice"] > PACE_COOLDOWN and not data.get("off"):
            if all(r["z"] > PACE_Z for r in recent):
                notice = _pace_notice("slow")
            elif all(r["z"] < -PACE_Z and r["words"] < 8 for r in recent):
                notice = _pace_notice("fast")
            if notice:
                pace["since_notice"], pace["recent"] = 0, []
                data["notices"].append(notice)
    # Their usual pace (a running mean and spread of the log ratio)
    stats["n"] += 1
    delta = x - stats["mean"]
    stats["mean"] += delta / stats["n"]
    stats["m2"] += delta * (x - stats["mean"])
    save_user_data(user, mine)
    save_chat_data(chat_obj, data)
    return notice


def _pace_notice(kind):
    text = ("You've been taking longer than usual to reply. Stuck, or just busy? I can suggest where the story "
            "could go, recap it, or write a message for you to change." if kind == "slow" else
            "Your last few replies were quick and short. If the story isn't pulling you in, I can help shake it up.")
    return {"id": uuid.uuid4().hex[:10], "kind": "pace", "label": f"pace_{kind}",
            "title": "Taking longer than usual" if kind == "slow" else "Quick, short replies",
            "text": text, "quotes": [], "status": "new", "time": time.time()}


# ---------------------------------------------------------------------------
# What they did with replies (for learning their taste)
# ---------------------------------------------------------------------------

def note_signal(user, chat_obj, kind, before="", after=""):
    """kind: "rewritten" (they asked for another version of a reply) or "edited" (they changed it)."""
    if not is_on(user):
        return
    data = chat_data(chat_obj)
    data["signals"] = (data["signals"] + [{"type": kind, "before": str(before)[:500], "after": str(after)[:500]}])[-12:]
    save_chat_data(chat_obj, data)


# ---------------------------------------------------------------------------
# Reading the replies
# ---------------------------------------------------------------------------

def _replies_since(messages, upto):
    return [i for i, m in enumerate(messages) if i >= upto and m[0] == "assistant"]


def due(user, chat_obj, messages):
    """Time for a read: on, not off for this chat, and enough new replies."""
    if not is_on(user):
        return False
    data = chat_data(chat_obj)
    if data.get("off"):
        return False
    return len(_replies_since(messages, min(data["upto"], len(messages)))) >= EVERY


SENTENCE = re.compile(r"[^.!?…]+[.!?…]+[\"”»]?")


def same_openings(text):
    """A quote when most sentences of a reply start with the same word (free; the reader also checks)."""
    starts = [s.strip().strip("\"“”«»*_ ").split(" ", 1)[0].lower() for s in SENTENCE.findall(text)]
    starts = [s for s in starts if s]
    if len(starts) < 6:
        return None
    word = max(set(starts), key=starts.count)
    if starts.count(word) / len(starts) >= 0.4 and word not in ("the", "a", "and"):
        firsts = [s.strip() for s in SENTENCE.findall(text) if s.strip().strip("\"“”«»*_ ").lower().startswith(word)]
        return " … ".join(f[:40] for f in firsts[:3])
    return None


def _prompt(user, character, messages, picked, data, mine, writes_for_user):
    from mainapp import model_profiles
    _, chat_model = ai_client.resolve(user, "chat")
    profile = model_profiles.for_model(chat_model) or {}
    habits = (profile.get("style") or {}).get("watch_for") or []
    parts = [f"## The character: {character.name}",
             str(character.description or "")[:1500],
             str(character.personality or "")[:600]]
    if habits:
        parts += ["## This model's known habits", "; ".join(habits)]
    parts.append("## The AI may write their character: " + ("yes" if writes_for_user else "no"))
    if mine["muted"]:
        parts += ["## They said they don't mind these (don't note them)", ", ".join(mine["muted"])]
    if data["signals"]:
        parts.append("## What they did with replies")
        for s in data["signals"]:
            parts.append(f"- Rewrote this reply: “{s['before']}”" if s["type"] == "rewritten" else
                         f"- Edited a reply from “{s['before']}” to “{s['after']}”")
    if mine["taste"]:
        parts += ["## Already known about their taste", *[f"- {t}" for t in mine["taste"]]]
    parts.append("## The chat (their messages for context; note slips only in the numbered replies)")
    first = picked[0]
    start = max(0, first - 1)
    n = 0
    for i in range(start, picked[-1] + 1):
        role, text = messages[i][0], str(messages[i][2])
        if role == "assistant" and i in picked:
            n += 1
            parts.append(f"### Reply {n}\n{text[:3000]}")
        elif role == "user":
            parts.append(f"### Them\n{text[:800]}")
    return [{"role": "system", "content": INSTRUCTIONS.read_text(encoding="utf-8")},
            {"role": "user", "content": "\n\n".join(parts)}]


def _parse(text):
    text = re.sub(r"^```(?:json)?|```$", "", str(text or "").strip(), flags=re.M).strip()
    try:
        data = json.loads(text)
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        try:
            data = json.loads(m.group(0)) if m else {}
        except ValueError:
            data = {}
    return data if isinstance(data, dict) else {}


def _label(raw):
    raw = str(raw or "").strip().lower()
    if raw in LABELS:
        return raw
    if raw.startswith("other:") and raw[6:].strip():
        return "other: " + raw[6:].strip()[:40]
    return None


def read(user, character, chat_obj, messages, writes_for_user=False):
    """Reads the replies since the last read; returns the notices it raised (habits that keep coming back)."""
    data = chat_data(chat_obj)
    picked = _replies_since(messages, min(data["upto"], len(messages)))[-MAX_READ:]
    if not picked:
        return []
    mine = user_data(user)
    answer = _parse(ai_client.complete(user, "watch", _prompt(user, character, messages, picked, data, mine,
                                                              writes_for_user),
                                       max_tokens=1500, temperature=0, response_format={"type": "json_object"}))
    slips = []
    for s in answer.get("slips") or []:
        if not isinstance(s, dict):
            continue
        label, quote = _label(s.get("label")), str(s.get("quote") or "").strip()[:300]
        try:
            at = picked[int(s.get("reply")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        if label and quote:
            slips.append({"label": label, "quote": quote, "at": at,
                          "cause": s.get("cause") if s.get("cause") in CAUSES else "model"})
    for at in picked:  # the free check
        quote = same_openings(str(messages[at][2]))
        if quote and not any(x["label"] == "same_openings" and x["at"] == at for x in slips):
            slips.append({"label": "same_openings", "quote": quote, "at": at, "cause": "model"})
    data["log"] += slips
    data["checked"] = sorted(set(data["checked"]) | set(picked))
    data["upto"] = len(messages)
    data["signals"] = []
    known = {t.lower() for t in mine["taste"]}
    for t in (answer.get("taste") or [])[:3]:
        t = str(t).strip()[:200]
        if t and t.lower() not in known:
            mine["taste"].append(t)
            known.add(t.lower())
    mine["taste"] = mine["taste"][-TASTE_MAX:]
    save_user_data(user, mine)
    raised = habits(data, mine["muted"], character.name)
    save_chat_data(chat_obj, data)
    return raised


def habits(data, muted, char_name="the character"):
    """New notices for slips that showed up in enough of the latest replies read (added to `data`)."""
    window = data["checked"][-WINDOW:]
    if len(window) < THRESHOLD:
        return []
    raised = []
    for label in dict.fromkeys(e["label"] for e in data["log"]):
        if label in muted:
            continue
        hits = [e for e in data["log"] if e["label"] == label and e["at"] in window]
        replies = {e["at"] for e in hits}
        if len(replies) < THRESHOLD:
            continue
        # Once per habit for as long as the same replies show it
        if any(n["label"] == label and (n["status"] == "new" or n.get("at", -1) >= window[0]) for n in data["notices"]):
            continue
        theirs = sum(e["cause"] == "their_messages" for e in hits) * 2 >= len(hits)
        title = LABELS.get(label, label.replace("other: ", "").capitalize()).replace("{char}", char_name)
        text = f"{title}: in {len(replies)} of the last {len(window)} replies."
        if theirs:
            text += (" Small thing: this one may partly come from your own messages; models copy what they're "
                     "given. Want to look at it together?")
        notice = {"id": uuid.uuid4().hex[:10], "kind": "user" if theirs else "pattern", "label": label,
                  "title": title, "text": text, "quotes": [e["quote"] for e in hits][-3:],
                  "causes": sorted({e["cause"] for e in hits}), "count": len(replies), "of": len(window),
                  "at": window[-1], "status": "new", "time": time.time()}
        data["notices"].append(notice)
        raised.append(notice)
    return raised


# ---------------------------------------------------------------------------
# The page and Bulba
# ---------------------------------------------------------------------------

def page_state(user, chat_obj):
    data = chat_data(chat_obj)
    on = is_on(user)
    new = [n for n in data["notices"] if n["status"] == "new"] if on and not data.get("off") else []
    return {"on": on, "chat_off": bool(data.get("off")), "intro": on and not user_data(user).get("intro_seen"),
            "every": EVERY, "notices": [{k: n.get(k) for k in ("id", "kind", "title", "text", "quotes")}
                                        for n in reversed(new)][:3], "count": len(new)}


def set_notice(user, chat_obj, notice_id, status):
    """status: "opened", "dismissed" or "muted" (they don't mind that habit: it's never raised again)."""
    data = chat_data(chat_obj)
    notice = next((n for n in data["notices"] if n["id"] == notice_id), None)
    if notice is None:
        raise ValueError("No such note.")
    notice["status"] = status
    if status == "muted" and notice["kind"] in ("pattern", "user"):
        mine = user_data(user)
        if notice["label"] not in mine["muted"]:
            mine["muted"].append(notice["label"])
            save_user_data(user, mine)
    save_chat_data(chat_obj, data)
    return notice


def intro_seen(user, keep_on):
    mine = user_data(user)
    mine["intro_seen"] = True
    save_user_data(user, mine)
    set_on(user, keep_on)


def set_chat_off(chat_obj, off):
    data = chat_data(chat_obj)
    data["off"] = bool(off)
    save_chat_data(chat_obj, data)


def for_bulba(notice):
    """What Bulba (in the chat) is told when they open a note."""
    if notice["kind"] == "pace":
        return (f"[Bulba Watch noticed: {notice['title']}. {notice['text']} They opened the note. Ask lightly how "
                "it's going (no lecture, they may just be busy) and offer concrete help with offer_choices: ideas "
                "for what could happen next, a short recap, or writing their next message for them to change.]")
    quotes = "\n".join(f"- “{q}”" for q in notice.get("quotes") or [])
    causes = ", ".join(notice.get("causes") or [])
    return (f"[Bulba Watch noticed a habit: {notice['title']} (in {notice.get('count')} of the last "
            f"{notice.get('of')} replies). Examples:\n{quotes}\nLikely source: {causes}. They opened the note. "
            "In two or three sentences, show them the habit with one quote and say where it comes from (the "
            "model, the preset or card, or their own messages: if theirs, say it gently and as a shared thing, "
            "never as blame). Then propose one fix the usual way, borrowing tested wording first. A good reply "
            "can still have a slip or two: the point is that it keeps repeating.]")
