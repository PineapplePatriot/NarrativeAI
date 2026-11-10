"""
Bulba Watch: Bulba quietly keeps an eye on a chat and speaks up only when something keeps happening.

- After every reply, free checks in code: sentences that keep starting the same way, and a phrase repeated
  word for word across recent replies.
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

EVERY = 3          # read after this many new replies
WINDOW = 6         # a habit is judged over the last this-many replies read...
THRESHOLD = 2      # ...and needs to show up in at least this many of them
PHRASE_THRESHOLD = 3  # a repeated four-word phrase needs three replies (two is often just the scene)
FIRST_READ = 2     # the first read comes sooner: after this many replies
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
    "stock_reactions": "Stock physical reactions used as emotional filler",
    "vague_emotion": "Vague changes in eyes, expression or voice",
    "emotional_annotation": "Explaining the emotion after every line",
    "decorative_stacking": "Stacking descriptions that add no new meaning",
    "therapy_voice": "Psychological analysis outside the character's voice",
    "stalled_scene": "Repeated reactions instead of developing the interaction",
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
    "repeated_phrase": "The same phrase, word for word",
    "misremembered_past": "Getting past events wrong",
    "recounting": "Recounting and keeping score instead of talking",
    "leaked_markup": "AI machinery in the reply (code, tool calls, instructions)",
    "same_shape": "Every reply built the same way",
    "overlong": "Replies far longer than the moment needs",
    "long_thinking": "Very long thinking before every reply",
    "staccato": "Chopped, fragment-by-fragment sentences",
    "corrective_contrast": "Feelings defined by what they're not",
    "ending_formula": "The same kind of ending every time",
}
CAUSES = ("model", "setup", "their_messages")
# Known AI slop, whoever the reader is: rewritten out of new replies by default (fix_known, polish.approved)
KNOWN_FIX = ("stock_reactions", "vague_emotion", "emotional_annotation", "corrective_contrast", "staccato")
# What each one looks like, in plain words (Bulba's notebook page)
ABOUT = {
    "stock_reactions": "Clenching and unclenching hands, opening and closing the mouth, jaw or breath cues repeated as emotional filler. A meaningful physical reaction is fine.",
    "vague_emotion": "Something changes in their eyes, gaze or voice, but the description never specifies what is perceived or contributes to the scene.",
    "emotional_annotation": "The narrator explains what every line or gesture means after the reader could already infer it. Preserve requested interior narration.",
    "decorative_stacking": "Repeated near-synonyms and parallel descriptions add emphasis without new information.",
    "therapy_voice": "Characters routinely diagnose feelings or deliver counseling language beyond their voice, knowledge or relationship.",
    "stalled_scene": "Replies repeat observations and reactions without addressing the unresolved exchange. Quiet conversation is not inherently stalled.",
    "same_openings": "He… He… He…: sentence after sentence starts the same way and the rhythm goes flat.",
    "overworked_metaphor": "A small gesture turned into a showy figure of speech, again and again.",
    "forced_callback": "\"The same look she gave him at the station\": pointing back at old scenes instead of this one.",
    "unearned_depth": "A stranger suddenly delivering life wisdom the moment hasn't earned.",
    "overexplaining": "Spelling out the subtext, the feeling, or why a joke was funny.",
    "detail_fixation": "Lingering on smells, textures and sounds while the scene you care about waits.",
    "out_of_character": "Acting or speaking against the character card, or knowing what they couldn't.",
    "echoing_user": "Repeating or paraphrasing what you just wrote back at you.",
    "writing_for_user": "Deciding what your character does, says or feels.",
    "pet_phrase": "The model's stock phrases, or any phrase that keeps coming back.",
    "repeated_phrase": "The same few words, word for word, across replies (checked for free, no AI).",
    "misremembered_past": "Getting earlier events, names or facts wrong.",
    "recounting": "Reciting old events as evidence, keeping score, or therapist-style insights.",
    "leaked_markup": "note_milestone(...), <thinking>, [OOC: …], {{char}}: the model's machinery showing in the story. "
                     "Noticed the first time (checked for free, no AI).",
    "same_shape": "Same number of paragraphs in the same order (action, line, action, question…), reply after reply. "
                  "Checked for free, no AI.",
    "overlong": "Many times longer than your messages, every time: the story slows and costs more. Checked for free.",
    "long_thinking": "A thinking model that thinks for pages before each reply: slower and pricier, rarely better. "
                     "Checked for free.",
    "staccato": "\"The key. His hand. Still. Waiting.\": fragments used for drama all the time.",
    "corrective_contrast": "\"It wasn't anger. It was something older.\": a contrast as emotional punctuation.",
    "ending_formula": "Every reply ends on a question, a cliffhanger or a profound one-liner.",
}


# ---------------------------------------------------------------------------
# Where things are kept
# ---------------------------------------------------------------------------

def is_on(user):
    return ai_client.is_enabled(user, "watch")


def set_on(user, on):
    """Switch it on or off for all their chats. Switched back on, the first-time note shows again in the next
    chat they open (what it does, and how to turn it off)."""
    setting = ai_client.get_task_setting(user, "watch")
    if on and not setting.enabled:
        mine = user_data(user)
        if mine.pop("intro_seen", None):
            save_user_data(user, mine)
    setting.enabled = bool(on)
    setting.save()


def user_data(user):
    from mainapp.models import ChatSettings
    obj = ChatSettings.objects.filter(author=user).first()
    data = dict(obj.watch or {}) if obj else {}
    data.setdefault("muted", [])
    data.setdefault("taste", [])
    data.setdefault("pace", {"n": 0, "mean": 0.0, "m2": 0.0})
    data.setdefault("fix", [])  # habits they approved for polishing (bulba/polish.py)
    data.setdefault("taste_in_preset", [])  # taste lines already put into their preset (with Bulba)
    # How Bulba's polish lands: replies kept, liked or rejected, and the rewrites they rejected (the polisher
    # is shown them as what not to do; see bulba/polish.py)
    data.setdefault("polish", {"kept": 0, "liked": 0, "rejected": 0, "examples": []})
    # Things they told Bulba they dislike ("other: <name>" -> what it means), fixed and watched like any habit
    data.setdefault("dislikes", {})
    data.setdefault("model_off", [])  # known habits of their chat model they asked Watch not to look for
    # Habits Watch saw a model itself write (not the setup, not their messages) in LEARN_AFTER chats: learned as
    # that model's own ({model id: [labels]}), fixed in its new replies like its known habits; model_seen counts
    data.setdefault("model_learned", {})
    data.setdefault("model_seen", {})
    # Known slop is rewritten out of new replies for everyone, no taste needed (Notebook page: off switch): the
    # universal tells (KNOWN_FIX) and their chat model's own known habits (the ticked ones); muted ones stay out
    data.setdefault("fix_known", True)
    # On for everyone from the start (once: if they stop it on the Notebook page it stays stopped): the model's
    # machinery (note_milestone(...), <thinking>, [OOC: ...]) tidied out of new replies
    if not data.get("defaults_v1"):
        data["defaults_v1"] = True
        if "leaked_markup" not in data["fix"]:
            data["fix"] = data["fix"] + ["leaked_markup"]
    return data


def save_user_data(user, data):
    from mainapp.models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    obj.watch = data
    obj.save(update_fields=["watch"])


def chat_data(chat_obj):
    chat_obj.refresh_from_db(fields=["watch"])  # another request may have changed it
    data = dict(chat_obj.watch or {})
    for key, empty in (("log", []), ("checked", []), ("free_checked", []), ("notices", []), ("signals", []),
                       ("pace", {})):
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


def on_reply_done(user, chat_obj, messages, char_name="the character", now=None, leak=""):
    """After every reply: start the pace clock and run the free checks. Returns the notices they raised."""
    if not is_on(user):  # off means nothing is collected
        return []
    data = chat_data(chat_obj)
    reply = str(messages[-1][2]) if messages else ""
    data["pace"].update({"reply_at": now or time.time(), "reply_words": _words(reply)})
    raised = []
    if messages and messages[-1][0] == "assistant" and not data.get("off"):
        free_checks(data, messages, leak)
        mine = user_data(user)
        raised = habits(data, mine["muted"], char_name, mine["fix"])
    save_chat_data(chat_obj, data)
    return raised


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

# ---------------------------------------------------------------------------
# Steering: when they direct more than they play, offer director mode (no AI)
# ---------------------------------------------------------------------------

STEER_RUN, STEER_HITS = 5, 3


def _directing(user):
    from mainapp import presets
    from mainapp.bulba import control
    try:
        return control.mode_of(presets.normalize(presets.get_active(user).data)) == "director"
    except Exception:
        return True  # can't tell: don't nag


DIRECTOR_TEXT = {
    "steering": "You've been steering the story with director's notes more than playing in it. Director mode makes "
                "that the default: the AI treats your messages as directions, never as your character, and replies "
                "read as chapters.",
    "messages": "Your messages lately read more like directions to the AI than your character's own lines. Director "
                "mode makes that official: the AI treats them as directions, never as your character, and replies "
                "read as chapters.",
    "book": "The book layout is only the look. Want the AI to treat you as the director too? Your messages become "
            "directions, never your character's actions.",
}


def _offer_director(user, chat_obj, data, why):
    if data.get("off") or data.get("director_offered") or _directing(user):
        return None
    mine = user_data(user)
    if mine.get("director_offered"):  # asked once already, in any chat: they know where to find it
        data["director_offered"] = True
        return None
    mine["director_offered"] = True
    save_user_data(user, mine)
    notice = {"id": uuid.uuid4().hex[:10], "kind": "director", "label": "director", "title": "Director mode?",
              "text": DIRECTOR_TEXT[why], "quotes": [], "status": "new", "time": time.time()}
    data["director_offered"] = True  # once per chat
    data["notices"].append(notice)
    return notice


def note_steering(user, chat_obj, kind):
    """kind: "note" (a director's note was sent) or "play". Whether their messages themselves read as directions
    is judged by the reader (read), which is more reliable than any word list."""
    if not is_on(user):
        return None
    data = chat_data(chat_obj)
    data["steer"] = ((data.get("steer") or []) + [kind])[-STEER_RUN:]
    notice = None
    if sum(k != "play" for k in data["steer"]) >= STEER_HITS:
        notice = _offer_director(user, chat_obj, data, "steering")
    save_chat_data(chat_obj, data)
    return notice


def offer_director_for_book(user, chat_obj):
    if not is_on(user):
        return None
    data = chat_data(chat_obj)
    notice = _offer_director(user, chat_obj, data, "book")
    save_chat_data(chat_obj, data)
    return notice


def switch_to_director(user, chat_obj, notice_id, undo=False):
    """The note's one-click switch (Pura's wording and the book layout), or putting it back."""
    import copy
    from mainapp import presets
    from mainapp.bulba import control
    from mainapp.models import Preset
    from mainapp.views import _appearance, set_layout
    data = chat_data(chat_obj)
    notice = next((n for n in data["notices"] if n["id"] == notice_id and n["kind"] == "director"), None)
    if notice is None:
        raise ValueError("No such note.")
    if undo:
        before = notice.get("undo") or {}
        Preset.objects.filter(user=user, id=before.get("preset_id")).update(data=before.get("data"))
        if before.get("layout"):
            set_layout(user, before["layout"])
        notice["status"] = "dismissed"
    else:
        active = presets.get_active(user)
        notice["undo"] = {"preset_id": active.id, "data": copy.deepcopy(active.data),
                          "layout": _appearance(user)["layout"]}
        active.data = control.apply_to_preset(presets.normalize(active.data), "director")
        active.save(update_fields=["data", "time_update"])
        set_layout(user, "book")
        notice["status"] = "director"
    save_chat_data(chat_obj, data)
    return notice


def recheck(user, chat_obj, messages):
    """Runs the free checks again on the newest reply after it changed (polished, or its fixes undone)."""
    if not is_on(user) or not messages or messages[-1][0] != "assistant":
        return
    data = chat_data(chat_obj)
    free_checks(data, messages)
    save_chat_data(chat_obj, data)


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
    return len(_replies_since(messages, min(data["upto"], len(messages)))) >= (EVERY if data["upto"] else FIRST_READ)


# ---------------------------------------------------------------------------
# Free checks (no AI), after every reply
# ---------------------------------------------------------------------------

FREE_LABELS = {"same_openings", "repeated_phrase", "leaked_markup", "same_shape", "overlong", "long_thinking"}
# About the reply as a whole: Bulba's polish can't rewrite these away; the fix belongs in the preset or settings
NO_POLISH = {"same_shape", "overlong", "long_thinking"}
OVERLONG_WORDS = 450   # a reply this long, and much longer than their messages...
OVERLONG_TIMES = 5     # ...this many times their usual length
LONG_THINKING_WORDS = 1200
IMMEDIATE = {"leaked_markup"}  # raised the first time, not once it's a habit
# The model's machinery in a story: a written function call, thinking or chat-template tags, out-of-character
# notes, unfilled macros, code fences, "As an AI"
LEAK = re.compile(
    r"\b[a-z]+_[a-z_]+\s*\(\s*(?:\w+\s*=|\{)"           # note_milestone(who=… / show_news({…
    r"|</?(?:think|thinking|reasoning|scratchpad|tool_call|function_call|response)\b[^>]*>"
    r"|<\|[a-z_]+\|>"
    r"|\[\s*(?:OOC|ooc|Note to self|System|SYSTEM|Instruction|INSTRUCTION)\s*:"
    r"|\(\s*(?:OOC|ooc)\s*:"
    r"|\{\{\s*(?:char|user|random|getvar|setvar)[^}]*\}\}"
    r"|^```"
    r"|\bAs an AI\b|\bas a language model\b",
    re.M)


def leaked(text):
    """The first bit of machinery in a reply (a short quote), or ""."""
    m = LEAK.search(text or "")
    if not m:
        return ""
    line_start = text.rfind("\n", 0, m.start()) + 1
    line_end = text.find("\n", m.end())
    line = text[line_start:line_end if line_end >= 0 else len(text)].strip()
    return line[:160] + ("…" if len(line) > 160 else "")
PHRASE_WORDS = 4
STOP = set("a an the and or but of to in on at for with as by from into he she it they we you i his her its their "
           "our your my him them me us is was were be been are am had has have do did not no so that this then there "
           "what which who when where how".split())


def raw_snippet(text, phrase):
    """The piece of the reply a found phrase came from, as written (colour tags and all), so the note can show
    it the way it looks in the chat rather than as bare words ("font color b22222 mu")."""
    words = phrase.split()
    m = re.search(r"[^\w’']+".join(re.escape(w) for w in words), str(text or ""), re.I)
    if not m:
        return ""
    start, end = m.start(), m.end()
    lt = text.rfind("<", 0, start)  # began inside a tag: take the whole tag
    if lt != -1 and text.rfind(">", 0, start) < lt:
        start = lt
    end = re.search(r"[\w’']*", text[end:]).end() + end  # finish the last word
    piece = text[start:end]
    for tag in re.findall(r"<([a-z]+)\b[^>]*>", piece, re.I):  # close what it opened (and the sentence)
        close = text.find(f"</{tag}>", end)
        if close != -1 and close - end < 200:
            end = close + len(tag) + 3
    return text[start:end][:300]


def model_text(message):
    """What the model wrote: a reply Bulba polished is judged by its original, so a habit Bulba keeps fixing
    still shows up here (and can be fixed at the source) instead of looking gone."""
    from mainapp import chats
    rec = chats.polish_of(message)
    from mainapp import html_objects  # designed objects aren't prose: Watch reads their label
    return html_objects.shrink(str(rec["original"] if rec else message[2]))


def free_checks(data, messages, extra_leak=""):
    """The same-openings and repeated-phrase checks on the newest reply; slips go into the log (and
    a phrase repeated across recent replies is logged at each of them)."""
    at = len(messages) - 1
    replies = [i for i, m in enumerate(messages) if m[0] == "assistant"][-WINDOW:]
    # A rewritten reply replaces the old version's free slips
    data["log"] = [e for e in data["log"] if not (e["at"] == at and e["label"] in FREE_LABELS)]
    data["free_checked"] = sorted(set(data.get("free_checked") or []) | {at})[-30:]
    quote = same_openings(model_text(messages[at]))
    if quote:
        data["log"].append({"label": "same_openings", "quote": quote, "at": at, "cause": "model"})
    leak = leaked(model_text(messages[at])) or (extra_leak or "")
    if leak:
        data["log"].append({"label": "leaked_markup", "quote": leak, "at": at, "cause": "model"})
    text = model_text(messages[at])
    shapes = {i: shape(model_text(messages[i])) for i in replies}
    if len(shapes[at]) >= 3:
        alike = [i for i in replies if i != at and shapes[i] == shapes[at]]
        if len(alike) >= THRESHOLD - 1:
            for i in alike[-(THRESHOLD - 1):] + [at]:
                if not any(e["label"] == "same_shape" and e["at"] == i for e in data["log"]):
                    data["log"].append({"label": "same_shape", "at": i, "cause": "model",
                                        "quote": "paragraphs: " + " → ".join(SHAPE_WORDS[k] for k in shapes[i])})
    theirs = [len(str(m[2]).split()) for m in messages[:at] if m[0] == "user"][-3:]
    words = len(text.split())
    if theirs and words >= OVERLONG_WORDS and words >= OVERLONG_TIMES * max(1, sum(theirs) / len(theirs)):
        data["log"].append({"label": "overlong", "at": at, "cause": "setup",
                            "quote": f"{words} words, to your {round(sum(theirs) / len(theirs))}"})
    from mainapp import chats as chats_mod
    thought = len(chats_mod.reasoning_of(messages[at]).split())
    if thought >= LONG_THINKING_WORDS:
        data["log"].append({"label": "long_thinking", "at": at, "cause": "setup", "quote": f"{thought} words of thinking"})
    for phrase, where in repeated_phrases({i: model_text(messages[i]) for i in replies}, at):
        for i in where:
            if not any(e["label"] == "repeated_phrase" and e["at"] == i and e["quote"] == phrase for e in data["log"]):
                data["log"].append({"label": "repeated_phrase", "quote": phrase, "at": i, "cause": "model",
                                    "shown": raw_snippet(model_text(messages[i]), phrase)})


SHAPE_WORDS = {"d": "dialogue", "a": "action", "n": "narration", "q": "ends on a question"}


def shape(text):
    """A reply's build: what each paragraph opens with (dialogue, action, narration), and a question at the end."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]
    out = []
    for p in paras:
        first = p.lstrip("_ ")[:1]
        out.append("d" if first in "\"“«„'" else "a" if p.startswith("*") else "n")
    if paras and paras[-1].rstrip("*_\"”» ").endswith("?"):
        out.append("q")
    return tuple(out)


def _grams(text):
    words = re.findall(r"[\w’']+", text.lower())
    return {" ".join(words[k:k + PHRASE_WORDS]) for k in range(len(words) - PHRASE_WORDS + 1)
            if sum(w not in STOP for w in words[k:k + PHRASE_WORDS]) >= 2}


def repeated_phrases(texts, newest):
    """Phrases of four words (two of them not filler) in the newest reply and at least THRESHOLD-1 others
    of `texts` ({message index: text}). Returns [(phrase, [indexes])], longest-running first, at most 3."""
    grams = {i: _grams(t) for i, t in texts.items()}
    found = []
    for g in grams.get(newest, ()):
        where = sorted(i for i, gs in grams.items() if g in gs)
        if len(where) >= PHRASE_THRESHOLD:
            found.append((g, where))
    found.sort(key=lambda f: (-len(f[1]), f[0]))
    picked = []
    for g, where in found:  # overlapping four-word pieces of one longer phrase count once
        if not any(set(g.split()) & set(p.split()) and where == w for p, w in picked):
            picked.append((g, where))
    return picked[:3]


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


def _established(chat_obj, character):
    """What's already established, for the contradiction check and to skip known facts: summary, pinned note,
    the lorebook's entry titles, the card's scenario."""
    from mainapp.bulba import memory
    try:
        saw = memory.what_the_ai_saw(chat_obj)
    except Exception:
        return []
    out = []
    summary = "\n".join(p["text"] for p in saw["summary"])
    if summary:
        out += ["## The story so far (summary)", summary[-2500:]]
    if saw["pinned_note"]:
        out += ["## Pinned note", saw["pinned_note"][:800]]
    if character.scenario:
        out += ["## The card's scenario", str(character.scenario)[:800]]
    if character.worldbook_id:
        from mainapp import lorebook
        try:
            entries = lorebook.load_worldbook(character.worldbook)["entries"]
            out += ["## Lore entries (titles)", "; ".join(e["comment"] or ", ".join(e["keys"][:2]) for e in entries)[:1500]]
        except Exception:
            pass
    return out


def _prompt(user, character, messages, picked, data, mine, writes_for_user, ask_directing=False, chat_obj=None):
    from mainapp import model_profiles
    _, chat_model = ai_client.resolve(user, "chat")
    profile = model_profiles.for_style(chat_model) or {}  # an unknown model: its closest relative's known habits
    habits = [h for h in (profile.get("style") or {}).get("watch_for") or [] if h not in mine["model_off"]]
    parts = [f"## The character: {character.name}",
             str(character.description or "")[:1500],
             str(character.personality or "")[:600]]
    if habits:
        parts += ["## This model's known habits", "; ".join(habits)]
    parts.append("## The AI may write their character: " + ("yes" if writes_for_user else "no"))
    if ask_directing:
        parts.append("## Also answer they_direct (see \"Are they directing?\")")
    if mine["muted"]:
        parts += ["## They said they don't mind these (don't note them)", ", ".join(mine["muted"])]
    if mine["dislikes"]:  # their own words, turned into habits: look for these too, with exactly this label
        parts += ["## They told you they dislike these (note them like any slip, with exactly this label)",
                  *[f"- {label}: {about}" for label, about in mine["dislikes"].items() if label in mine["fix"]]]
    if data["signals"]:
        parts.append("## What they did with replies")
        for s in data["signals"]:
            parts.append(f"- Rewrote this reply: “{s['before']}”" if s["type"] == "rewritten" else
                         f"- Edited a reply from “{s['before']}” to “{s['after']}”")
    if mine["taste"]:
        parts += ["## Already known about their taste", *[f"- {t}" for t in mine["taste"]]]
    if chat_obj is not None:
        parts += _established(chat_obj, character)
    parts.append("## The chat (their messages for context; note slips only in the numbered replies)")
    first = picked[0]
    start = max(0, first - 1)
    n = 0
    for i in range(start, picked[-1] + 1):
        role, text = messages[i][0], model_text(messages[i])
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
    ask_directing = not data.get("director_offered") and not _directing(user)
    answer = _parse(ai_client.complete(user, "watch", _prompt(user, character, messages, picked, data, mine,
                                                              writes_for_user, ask_directing, chat_obj),
                                       max_tokens=4000, temperature=0, response_format={"type": "json_object"}))
    # The read takes a while: the chat may have moved on meanwhile (a note shown, director mode offered), so
    # the answer goes into what's saved now, not into what was loaded before the call
    data, mine = chat_data(chat_obj), user_data(user)
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
    raised = story_notes(data, answer, picked, character.name)  # logs "getting the past wrong" slips first
    raised += habits(data, mine["muted"], character.name, mine["fix"])
    if learn_from(user, mine, chat_obj, raised):
        save_user_data(user, mine)
    taste_note = offer_taste(data, mine)
    if taste_note:
        raised.append(taste_note)
        save_user_data(user, mine)
    if ask_directing and answer.get("they_direct") is True:  # their messages read as directions: offer director mode
        notice = _offer_director(user, chat_obj, data, "messages")
        if notice:
            raised.append(notice)
    save_chat_data(chat_obj, data)
    return raised


LEARN_AFTER = 2  # chats where the model itself kept writing a habit before Watch learns it as that model's own


def chat_model(user):
    try:
        return ai_client.resolve(user, "chat")[1] or ""
    except ai_client.AIError:
        return ""


def learned(mine, model):
    """The habits learned as this model's own that still apply (not switched off or muted)."""
    off = set(mine.get("model_off") or []) | set(mine.get("muted") or [])
    return [label for label in (mine.get("model_learned") or {}).get(model, []) if label not in off]


def learn_from(user, mine, chat_obj, raised):
    """Notes just raised about a habit the model itself writes (the cause is only the model): counted per model, and
    once it's shown up in LEARN_AFTER chats it's learned as that model's own and fixed in its new replies (the note
    says so; the Notebook page undoes it). True if anything changed."""
    model = chat_model(user)
    if not model:
        return False
    changed = False
    seen = mine.setdefault("model_seen", {}).setdefault(model, {})
    known = mine.setdefault("model_learned", {}).setdefault(model, [])
    for n in raised:
        label = n.get("label")
        if (n.get("kind") != "pattern" or n.get("causes") != ["model"] or label in NO_POLISH or label in known
                or label in mine["fix"]):
            continue
        chats = seen.setdefault(label, [])
        if chat_obj.id not in chats:
            chats.append(chat_obj.id)
            del chats[:-LEARN_AFTER]
            changed = True
        if len(chats) >= LEARN_AFTER:
            known.append(label)
            if mine.get("fix_known", True):
                short = model.split("/")[-1]
                n["text"] += (f" I've now seen {short} write this in {len(chats)} different chats, so it's one of its "
                              "own habits: Bulba fixes it in its new replies from now on (undo on Bulba's notebook page).")
                n["learned"] = True
    return changed


KEEP_OFFER = 2  # new lasting facts before Bulba offers to keep them in the card or lorebook


def story_notes(data, answer, picked, char_name):
    """Contradictions (each one is worth a note) and the Story Keeper (new facts worth keeping, once a couple
    have piled up). Both come from the same read: no extra call."""
    raised = []
    found = []
    for c in (answer.get("past") or [])[:2]:
        if not isinstance(c, dict):
            continue
        quote, actually = str(c.get("quote") or "").strip()[:300], str(c.get("actually") or "").strip()[:300]
        try:
            at = picked[int(c.get("reply")) - 1]
        except (TypeError, ValueError, IndexError):
            continue
        if quote and actually:
            found.append({"quote": quote, "actually": actually, "at": at})
    # Each one is a slip too: when it keeps happening, it's a habit (a note, and something the polish can fix)
    data["log"] += [{"label": "misremembered_past", "quote": f["quote"], "at": f["at"], "cause": "model"} for f in found]
    if found:  # and a mistake worth a word straight away
        notice = {"id": uuid.uuid4().hex[:10], "kind": "continuity", "label": "continuity",
                  "title": "A reply got the past wrong",
                  "text": " ".join(f"“{f['quote']}”: actually, {f['actually']}." for f in found),
                  "quotes": [], "found": found, "status": "new", "time": time.time(), "at": found[-1]["at"]}
        data["notices"].append(notice)
        raised.append(notice)
    keep = data.setdefault("keep", [])
    known = {k["fact"].lower() for k in keep}
    for k in (answer.get("keep") or [])[:3]:
        if isinstance(k, dict) and str(k.get("fact") or "").strip() and str(k["fact"]).strip().lower() not in known:
            keep.append({"fact": str(k["fact"]).strip()[:300], "where": "lore" if k.get("where") == "lore" else "card",
                         "offered": False})
            known.add(str(k["fact"]).strip().lower())
    data["keep"] = keep[-30:]
    pending = [k for k in data["keep"] if not k["offered"]]
    if len(pending) >= KEEP_OFFER and not any(n["kind"] == "keeper" and n["status"] == "new" for n in data["notices"]):
        for k in pending:
            k["offered"] = True
        notice = {"id": uuid.uuid4().hex[:10], "kind": "keeper", "label": "keeper", "title": "Worth keeping?",
                  "text": f"The story established a few things that will matter later. Keep them in {char_name}'s "
                          "card or the lorebook, so the AI doesn't forget them?",
                  "quotes": [k["fact"] for k in pending][-5:], "facts": pending[-5:], "status": "new", "time": time.time()}
        data["notices"].append(notice)
        raised.append(notice)
    return raised


TASTE_OFFER = 3  # learned taste lines not in the preset yet before Bulba offers to put them there


def taste_pending(mine):
    return [t for t in mine["taste"] if t not in mine["taste_in_preset"]]


def offer_taste(data, mine):
    """A note offering to put what it learned about their taste into their preset (once per new batch)."""
    pending = taste_pending(mine)
    if len(pending) < TASTE_OFFER or sorted(pending) == sorted(mine.get("taste_offered") or []):
        return None
    if any(n["kind"] == "taste" and n["status"] in ("new", "opened") for n in data["notices"]):
        return None
    mine["taste_offered"] = pending
    notice = {"id": uuid.uuid4().hex[:10], "kind": "taste", "label": "taste", "title": "Your taste, in your preset?",
              "text": "I've learned a few things about what you like. Want them in your preset, so every reply "
                      "follows them? Bulba words them as instructions; you see the change before it's applied.",
              "quotes": pending[-5:], "status": "new", "time": time.time()}
    data["notices"].append(notice)
    return notice


def mark_taste_in_preset(user, lines, undo=False):
    mine = user_data(user)
    if undo:
        mine["taste_in_preset"] = [t for t in mine["taste_in_preset"] if t not in lines]
    else:
        mine["taste_in_preset"] += [t for t in lines if t in mine["taste"] and t not in mine["taste_in_preset"]]
    save_user_data(user, mine)


def habits(data, muted, char_name="the character", fixing=()):
    """New notices for slips that showed up in enough of the latest replies checked (added to `data`). The free
    checks run on every reply, the reader every few: each kind of slip is judged over the replies its check saw."""
    raised = []
    for label in dict.fromkeys(e["label"] for e in data["log"]):
        if label in muted:
            continue
        window = (data.get("free_checked") or [] if label in FREE_LABELS else data["checked"])[-WINDOW:]
        need = 1 if label in IMMEDIATE else THRESHOLD
        if len(window) < need:
            continue
        hits = [e for e in data["log"] if e["label"] == label and e["at"] in window]
        if label == "repeated_phrase":
            # A notice must demonstrate ONE repeated phrase, not pool unrelated matches.
            groups = {}
            for hit in hits:
                groups.setdefault(hit["quote"], []).append(hit)
            eligible = [group for group in groups.values()
                        if len({e["at"] for e in group}) >= PHRASE_THRESHOLD]
            hits = max(eligible, key=lambda group: len({e["at"] for e in group}), default=[])
        replies = {e["at"] for e in hits}
        if len(replies) < need:
            continue
        # Once per habit for as long as the same replies show it
        if any(n["label"] == label and (n["status"] == "new" or n.get("at", -1) >= window[0]) for n in data["notices"]):
            continue
        theirs = sum(e["cause"] == "their_messages" for e in hits) * 2 >= len(hits)
        title = LABELS.get(label, label.replace("other: ", "").capitalize()).replace("{char}", char_name)
        persisting = label in fixing  # Bulba polishes it away, but the model keeps writing it
        text = f"{title}: in {len(replies)} of the last {len(window)} replies."
        if label == "leaked_markup":
            text = (f"{title}. Models sometimes write their own instructions or tool calls into the story. "
                    "I can find what in your setup invites it and fix it, or tidy such bits out of new replies.")
        if persisting:
            text = (f"{title}: the model still writes it in {len(replies)} of the last {len(window)} replies; Bulba "
                    "has been fixing it each time. Fixing it at the source, in your preset, would stop it before "
                    "it's written (and save the polish). Want to look at it?")
        elif theirs:
            text += (" Small thing: this one may partly come from your own messages; models copy what they're "
                     "given. Want to look at it together?")
        notice = {"id": uuid.uuid4().hex[:10], "kind": "user" if theirs else "pattern", "label": label,
                  "title": title, "text": text, "quotes": list(dict.fromkeys(e.get("shown") or e["quote"] for e in reversed(hits)))[:3][::-1],
                  "causes": sorted({e["cause"] for e in hits}), "count": len(replies), "of": len(window),
                  "at": window[-1], "status": "new", "time": time.time(), "persisting": persisting,
                  "nofix": label in NO_POLISH}
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
    mine = user_data(user)
    return {"on": on, "chat_off": bool(data.get("off")), "intro": on and not mine.get("intro_seen"),
            "fixing": [title_of(m) for m in mine["fix"]] if on and not data.get("off") else [],  # the 🧹 button
            "every": EVERY, "notices": [{**{k: n.get(k) for k in ("id", "kind", "title", "text", "quotes", "index", "nofix", "count", "of")},
                                         "fixing": n.get("label") in mine["fix"]}
                                        for n in reversed(new)], "count": len(new)}


def set_notice(user, chat_obj, notice_id, status):
    """status: "opened", "dismissed", "muted" (they don't mind that habit: it's never raised again) or "fix"
    (they confirm it's unwanted: replies get polished for it from now on, see bulba/polish.py)."""
    data = chat_data(chat_obj)
    notice = next((n for n in data["notices"] if n["id"] == notice_id), None)
    if notice is None:
        raise ValueError("No such note.")
    notice["status"] = status
    if status == "fix":
        if notice["kind"] not in ("pattern", "user"):
            raise ValueError("That note isn't about a habit.")
        mine = user_data(user)
        if notice["label"] not in mine["fix"]:
            mine["fix"].append(notice["label"])
            save_user_data(user, mine)
    if status == "stop_fix":  # from a "fixes didn't land" question: stop polishing those habits
        if notice["kind"] != "polish":
            raise ValueError("That note isn't about Bulba's fixes.")
        mine = user_data(user)
        stop = set(notice.get("habits") or mine["fix"])
        mine["fix"] = [h for h in mine["fix"] if h not in stop]
        save_user_data(user, mine)
    if status == "muted" and notice["kind"] in ("pattern", "user"):
        mine = user_data(user)
        if notice["label"] not in mine["muted"]:
            mine["muted"].append(notice["label"])
            save_user_data(user, mine)
    save_chat_data(chat_obj, data)
    return notice


# ---------------------------------------------------------------------------
# Did the polish land? (bulba/polish.py)
# ---------------------------------------------------------------------------

POLISH_WHY = {
    "undid": "You put the original back.",
    "edited": "You changed the polished reply yourself.",
    "regenerated": "You asked for a new reply instead of the polished one.",
    "disliked": "You marked the fixes as not right.",
}


def polish_verdict(user, verdict):
    """A polished reply was kept (they replied to it) or liked (👍)."""
    mine = user_data(user)
    mine["polish"][verdict] = mine["polish"].get(verdict, 0) + 1
    save_user_data(user, mine)


def polish_rejected(user, chat_obj, index, why, rec, habits):
    """They undid, edited or regenerated a polished reply, or pressed 👎: remember the rewrites they turned down
    and ask right away what to do (rewrite it again, stop fixing those habits, or tell Bulba what's wrong)."""
    mine = user_data(user)
    stats = mine["polish"]
    stats["rejected"] = stats.get("rejected", 0) + 1
    fixes = [f for f in (rec or {}).get("fixes") or [] if isinstance(f, dict)]
    stats["examples"] = (stats.get("examples", []) + [{"before": str(f.get("before", ""))[:200],
                                                       "after": str(f.get("after", ""))[:200]} for f in fixes])[-8:]
    save_user_data(user, mine)
    if not is_on(user):
        return None
    data = chat_data(chat_obj)
    for n in data["notices"]:  # one question at a time
        if n.get("kind") == "polish" and n["status"] == "new":
            n["status"] = "dismissed"
    notice = {"id": uuid.uuid4().hex[:10], "kind": "polish", "label": "polish", "title": "Bulba's fixes didn't land?",
              "text": POLISH_WHY.get(why, "") + " Rewrite it again differently, stop fixing this, or tell me what's wrong?",
              "quotes": [f"{f.get('before', '')} → {f.get('after', '') or '(removed)'}" for f in fixes][:3],
              "index": index, "why": why, "habits": list(habits or []), "fixes": fixes[:8],
              "status": "new", "time": time.time()}
    data["notices"].append(notice)
    save_chat_data(chat_obj, data)
    return notice


def title_of(label, char_name="The character"):
    if label == "model_known":  # polish.MODEL_KNOWN: the chat model's own known habits
        return "Your model's known habits"
    return LABELS.get(label, label.replace("other: ", "").capitalize()).replace("{char}", char_name)


def memory(user):
    """What it learned about them, for the Extras page: their taste, the habits they said they don't mind,
    and the habits they asked to have fixed (with the model that fixes them)."""
    mine = user_data(user)
    return {"taste": list(mine["taste"]), "taste_in_preset": [t for t in mine["taste"] if t in mine["taste_in_preset"]],
            "muted": [{"label": m, "title": title_of(m)} for m in mine["muted"]],
            "fix": [{"label": m, "title": title_of(m), "about": mine["dislikes"].get(m, "")} for m in mine["fix"]],
            "fix_model": "chat" if mine.get("fix_model") == "chat" else "bulba"}


def notebook(user):
    """Bulba's notebook page: everything Watch looks for (the common habits, their chat model's own, theirs),
    what it learned about their taste, and what the whole account has spent."""
    from mainapp import model_profiles
    mine = user_data(user)
    try:
        _, chat_model = ai_client.resolve(user, "chat")
    except ai_client.AIError:  # no connection yet: the page still shows the rest
        chat_model = ""
    profile = model_profiles.for_style(chat_model) if chat_model else {}
    profile = profile or {}
    own = [label for label in mine["fix"] if label.startswith("other: ")]
    return {
        **memory(user),
        "on": is_on(user),
        "common": [{"label": label, "title": title_of(label), "about": ABOUT.get(label, ""),
                    "on": label not in mine["muted"],
                    "fixing": label in mine["fix"] or (mine.get("fix_known", True) and label in KNOWN_FIX)}
                   for label in LABELS],
        "model": {"name": (f"{chat_model} (borrowed from {profile['name']}, its closest relative)"
                           if profile.get("_borrowed") else chat_model if profile.get("_generic")
                           else profile.get("name") or chat_model or "your chat model"),
                  "items": [{"text": h, "on": h not in mine["model_off"]}
                            for h in (profile.get("style") or {}).get("watch_for") or []]
                           + [{"text": title_of(label), "key": label, "on": label not in mine["model_off"],
                               "about": "Learned by Watch: this model kept writing it in your chats."}
                              for label in (mine["model_learned"].get(chat_model) or []) if label not in mine["muted"]]},
        "own": [{"label": label, "title": title_of(label), "about": mine["dislikes"].get(label, "")} for label in own],
        "fix_known": mine.get("fix_known", True),
        "known_fix": [title_of(label) for label in KNOWN_FIX if label not in mine["muted"]],
        "muted_other": [{"label": m, "title": title_of(m)} for m in mine["muted"] if m not in LABELS],
        "spent": ai_client.spent_total(user),
        "month": ai_client.spent_this_month(user),
    }


DISLIKE_PROMPT = (
    "Someone using a roleplay app describes something they dislike in the AI's writing, in their own words. Turn "
    "it into a habit an editor can spot and fix. Answer only with JSON: {\"name\": \"2 to 5 words, lower case\", "
    "\"about\": \"one plain sentence: what to look for in a reply, concretely (not why it's bad)\"}. Keep their "
    "meaning; don't widen it. No 'ensure', 'immersive', 'vivid'.")


def word_dislike(user, raw):
    """Bulba's wording for a dislike in their own words: {"name", "about"} (their words as they are if it fails)."""
    raw = str(raw or "").strip()[:500]
    if not raw:
        raise ValueError("Write what you dislike first, in your own words.")
    fallback = {"name": raw[:40].lower(), "about": raw}
    try:
        text = ai_client.complete(user, "bulba", [{"role": "system", "content": DISLIKE_PROMPT},
                                                   {"role": "user", "content": raw}],
                                  max_tokens=1500, temperature=0.3, response_format={"type": "json_object"})
    except ai_client.AIError:
        return fallback
    data = _parse(text)
    name, about = str(data.get("name") or "").strip()[:40], str(data.get("about") or "").strip()[:300]
    return {"name": name.lower(), "about": about} if name and about else fallback


def add_dislike(user, name, about):
    """Adds it to the habits Bulba fixes (and Watch looks for). Returns its label."""
    name, about = str(name or "").strip().lower()[:40], str(about or "").strip()[:300]
    if not name:
        raise ValueError("Give it a short name.")
    label = "other: " + name
    mine = user_data(user)
    mine["dislikes"][label] = about or name
    if label not in mine["fix"]:
        mine["fix"].append(label)
    if label in mine["muted"]:
        mine["muted"].remove(label)
    save_user_data(user, mine)
    return label


def change_memory(user, op, old="", new=""):
    """op: "edit" (reword a taste line), "forget" (remove one), "unmute" (raise that habit again), "stop_fix"
    (stop polishing for a habit) or "fix_model" ("bulba" or "chat", in `new`).
    `old` is the line or habit as they saw it, so a change made elsewhere meanwhile can't hit the wrong one."""
    mine = user_data(user)
    new = str(new or "").strip()[:200]
    if op in ("edit", "forget"):
        if old not in mine["taste"]:
            raise ValueError("That line is gone; reload the page.")
        i = mine["taste"].index(old)
        if op == "forget":
            mine["taste"].pop(i)
        elif not new:
            raise ValueError("Write something, or remove it instead.")
        else:
            mine["taste"][i] = new
    elif op == "unmute":
        if old not in mine["muted"]:
            raise ValueError("That one is gone; reload the page.")
        mine["muted"].remove(old)
    elif op == "stop_fix":
        if old not in mine["fix"]:
            raise ValueError("That one is gone; reload the page.")
        mine["fix"].remove(old)
        mine["dislikes"].pop(old, None)
    elif op == "mute":  # a built-in habit switched off on Bulba's notebook page: not looked for, not fixed
        if old not in LABELS:
            raise ValueError("That isn't one of the built-in habits.")
        if old not in mine["muted"]:
            mine["muted"].append(old)
        mine["fix"] = [f for f in mine["fix"] if f != old]
    elif op in ("model_off", "model_on"):
        if not old or len(old) > 200:
            raise ValueError("Which habit?")
        mine["model_off"] = [h for h in mine["model_off"] if h != old] + ([old] if op == "model_off" else [])
    elif op == "fix_known":  # the Notebook page's switch: rewrite the known slop out of new replies
        mine["fix_known"] = bool(new)
    elif op == "fix_model":
        if new not in ("bulba", "chat"):
            raise ValueError("Pick Bulba's model or your chat model.")
        mine["fix_model"] = new
    else:
        raise ValueError("Unknown change.")
    save_user_data(user, mine)


def intro_seen(user, keep_on):
    set_on(user, keep_on)
    mine = user_data(user)
    mine["intro_seen"] = True
    save_user_data(user, mine)


def set_chat_off(chat_obj, off):
    data = chat_data(chat_obj)
    data["off"] = bool(off)
    save_chat_data(chat_obj, data)


# ---------------------------------------------------------------------------
# Bulba in a chat can switch it ("turn Watch off", "not in this chat")
# ---------------------------------------------------------------------------

def tool_set_watch(session, args):
    on = bool(args.get("on"))
    scope = "chat" if args.get("scope") == "this_chat" else "all"
    if scope == "chat":
        if session.chat is None:
            return {"error": "There's no chat here; use scope everywhere."}, []
        set_chat_off(session.chat, not on)
        if on and not is_on(session.user):
            set_on(session.user, True)
        done = "on in this chat" if on else "off in this chat (still on in their other chats)"
    else:
        set_on(session.user, on)
        if on and session.chat is not None:
            set_chat_off(session.chat, False)
        done = "on in all their chats" if on else "off in all their chats; nothing is read or collected"
    state = page_state(session.user, session.chat) if session.chat is not None else None
    return {"done": f"Bulba Watch is {done}.", "where_else": "Extras page, or the pen menu → This chat"}, (
        [{"type": "watch", "watch": state}] if state else [])


def tool_defs(fn, STR):
    return [fn("set_watch", "Switch Bulba Watch (your quiet reading of replies for habits, and the polish) on or off "
               "when they ask: everywhere, or only in this chat. It happens at once, no Apply.",
               {"on": {"type": "boolean"}, "scope": {"type": "string", "enum": ["everywhere", "this_chat"]}},
               ["on", "scope"]),
            fn("add_dislike", "Add something they dislike in the replies to the habits Bulba fixes in every new reply "
               "(and Bulba Watch looks for). Word it with them first: a short name and one concrete sentence of what "
               "to look for, keeping their meaning. Use when they say they hate or keep seeing something.",
               {"name": {"type": "string", "description": "2 to 5 words, lower case"},
                "about": {"type": "string", "description": "One sentence: what it looks like in a reply"}},
               ["name", "about"])]


def tool_add_dislike(session, args):
    try:
        label = add_dislike(session.user, args.get("name"), args.get("about"))
    except ValueError as e:
        return {"error": str(e)}, []
    state = page_state(session.user, session.chat) if session.chat is not None else None
    return {"added": title_of(label), "note": "New replies get it rewritten (🧹 shows on replies), and Bulba Watch "
            "looks for it. They can remove it on the Extras page."}, ([{"type": "watch", "watch": state}] if state else [])


HANDLERS = {"set_watch": tool_set_watch, "add_dislike": tool_add_dislike}


def for_bulba(notice):
    """What Bulba (in the chat) is told when they open a note."""
    if notice["kind"] == "polish":
        fixes = "\n".join(f"- “{f.get('before')}” → “{f.get('after') or '(removed)'}”" for f in notice.get("fixes") or [])
        return (f"[They turned down your polish on reply {notice.get('index')}: {POLISH_WHY.get(notice.get('why'), '')}\n"
                f"Your fixes were:\n{fixes}\nThey want to tell you what's wrong. Ask in one line what didn't work (too "
                "much changed, the voice got lost, the habit isn't a problem for them, something else). Then act on it: "
                "polish_message on that reply with their words as the habit; or, if they don't mind the habit after all, "
                "say they can stop fixing it with the button on the note or on the Extras page. What they say also "
                "teaches you their taste.]")
    if notice["kind"] == "keeper":
        facts = "\n".join(f"- {f['fact']} (belongs in the {'lorebook' if f['where'] == 'lore' else 'card'})"
                          for f in notice.get("facts") or [])
        return (f"[Bulba Watch noted new lasting facts from the story:\n{facts}\nThey want them kept. Check the card "
                "(and read_lorebook for world facts); skip anything already there. Then propose the smallest addition: "
                "propose_card_edit for the character's own facts (add to the right field, keep the rest word for word), "
                "propose_lore_edit (or propose_lorebook if there's none) for world facts. One short message first.]")
    if notice["kind"] == "continuity":
        found = "\n".join(f"- “{f['quote']}”; actually: {f['actually']}" for f in notice.get("found") or [])
        return (f"[Bulba Watch noticed a recent reply getting the past wrong (retelling it inaccurately, leaving out "
                f"what mattered, or inventing details):\n{found}\nThey opened the note. Check it "
                "(read_memory, the card, read_lorebook): if the reply is wrong, offer polish_message to correct those "
                "words; if the summary, pinned note or lore is wrong instead, propose the fix there. If it's not "
                "really a contradiction (a lie, a change of mind), say so in a line.]")
    if notice["kind"] == "taste":
        lines = "\n".join(f"- {q}" for q in notice.get("quotes") or [])
        return (f"[Bulba Watch learned these about their taste (they checked them on the Extras page):\n{lines}\n"
                "They want them in their preset. Read the preset outline (and its 'Your taste' block if there is "
                "one, with read_block). Then propose_preset_edit: turn each line into a plain instruction to the "
                "model (append to 'Your taste', or add that block), borrowing tested library wording first "
                "(find_practice), skipping what the preset already says and anything that contradicts it (say "
                "which). Pass from_taste with the exact lines you covered. One short message, then the proposal.]")
    if notice["kind"] == "pace":
        return (f"[Bulba Watch noticed: {notice['title']}. {notice['text']} They opened the note. Ask lightly how "
                "it's going (no lecture, they may just be busy) and offer concrete help with offer_choices: ideas "
                "for what could happen next, a short recap, or writing their next message for them to change.]")
    quotes = "\n".join(f"- “{q}”" for q in notice.get("quotes") or [])
    causes = ", ".join(notice.get("causes") or [])
    if notice.get("persisting"):
        return (f"[Bulba Watch: {notice['title']} keeps coming back in what the model writes (in "
                f"{notice.get('count')} of the last {notice.get('of')} replies), although you polish it away each "
                f"time they see it. Examples, as the model wrote them:\n{quotes}\nThey opened the note. In two "
                "sentences: polishing hides it, but the model hasn't stopped. Offer the fix at the source: a preset "
                "change (propose_preset_edit, inspect relevant research with find_practice; or the model settings if "
                "it's a repetition problem). If the polish itself let some through, also offer polish_message on "
                "the latest replies. Keeping the polish as it is stays a fine answer.]")
    return (f"[Bulba Watch noticed a habit: {notice['title']} (in {notice.get('count')} of the last "
            f"{notice.get('of')} replies). Examples:\n{quotes}\nLikely source: {causes}. They opened the note. "
            "In two or three sentences, show them the habit with one quote and say where it comes from (the "
            "model, the preset or card, or their own messages: if theirs, say it gently and as a shared thing, "
            "never as blame). Then propose one fix the usual way, using a relevant research principle. A good reply "
            "can still have a slip or two: the point is that it keeps repeating.]")
