"""
Bulba's polish (the "desloppifier"): once they've told Bulba Watch that a habit is unwanted ("Fix this
automatically" on its note), every new reply (a swipe, a regenerated reply, a continued one) gets a quick
pass that rewrites just the sentences with that habit, before they read on.

- Only the habits they approved, and only when there are any. When every approved habit can be spotted for
  free (same openings, a repeated phrase) and this reply has none, nothing is called.
- The rewriter (Bulba's model by default, or their chat model if they pick it on the Extras page) sees the
  reply, the habits with real quotes from this chat, and the chat's summary: not the whole chat.
- It answers with small find-and-replace fixes. Code checks each one (the words must be there exactly once;
  story-extra markers and colour tags must survive; not too much may change) and drops any that fail.
- The original is kept with the reply (chats.polish_of), so "Show original" and "Undo fixes" always work.
"""
import json
import re
from pathlib import Path

from mainapp import ai_client
from mainapp.bulba import watch

INSTRUCTIONS = Path(__file__).resolve().parent.parent / "data" / "bulba" / "polish.md"
MAX_FIXES = 8
MAX_CHANGED = 0.4  # at most this share of the reply may change...
MAX_CHANGED_SHORT = 300  # ...or this many characters, so a short reply can still get a sentence fixed
PROTECTED = re.compile(r"\[\[extra \d+\]\]|<[^>]{1,80}>|\{\{(?:char|user)\}\}")

# What each habit means, for the rewriter (watch.md has the full version for the reader)
MEANING = {
    "same_openings": "sentence after sentence starts the same way (he… he… he…)",
    "overworked_metaphor": "a small gesture or object stretched into a showy figure of speech",
    "forced_callback": "describing something by pointing back at an earlier scene instead of describing it here",
    "unearned_depth": "a profound line or life lesson the moment and the relationship haven't earned",
    "overexplaining": "spelling out subtext, feelings or jokes the reader already got",
    "detail_fixation": "lingering on small physical details while the scene waits",
    "out_of_character": "the character acting or speaking against who they are",
    "echoing_user": "repeating or paraphrasing the person's own words back at them",
    "writing_for_user": "deciding what the person's character says, does or feels",
    "pet_phrase": "a stock phrase this model keeps using",
    "repeated_phrase": "the same phrase, word for word, as in recent replies",
    "misremembered_past": "retelling earlier events inaccurately, leaving out what mattered, or inventing details "
                          "of the past (correct it to what the summary says happened)",
}


def approved(user):
    """The habits they asked to have fixed (Watch must be on)."""
    return list(watch.user_data(user).get("fix") or []) if watch.is_on(user) else []


# Habits that can't apply to the person's own message ("Write my message")
NOT_FOR_THEIR_MESSAGE = {"writing_for_user", "echoing_user", "out_of_character"}


def due(user, chat_obj, messages):
    """Should the newest reply be polished? Free when it can be decided in code."""
    habits = approved(user)
    if not habits or not messages or messages[-1][0] != "assistant" or watch.chat_data(chat_obj).get("off"):
        return False
    if set(habits) <= watch.FREE_LABELS:  # every habit has a free check: only call when one hits
        return bool(_free_hits(messages, habits))
    return True


def others_before(messages, index, role="assistant"):
    """The texts of the earlier messages of the same role (for the repeated-phrase check)."""
    return [str(m[2]) for m in messages[:index] if m[0] == role]


def free_hits_text(text, others, habits):
    hits = []
    if "same_openings" in habits and watch.same_openings(text):
        hits.append("same_openings")
    if "repeated_phrase" in habits and _repeated(text, others):
        hits.append("repeated_phrase")
    return hits


def _repeated(text, others):
    texts = dict(enumerate(others[-(watch.WINDOW - 1):]))
    texts[-1] = text
    return watch.repeated_phrases(texts, -1)


def _free_hits(messages, habits):
    return free_hits_text(str(messages[-1][2]), others_before(messages, len(messages) - 1), habits)


def _examples(chat_obj, label):
    quotes = [e["quote"] for e in watch.chat_data(chat_obj)["log"] if e["label"] == label]
    return quotes[-2:]


def _prompt(character, chat_obj, text, others, summary, habits, whose="reply"):
    lines = []
    for label in habits:
        if label in watch.LABELS or label.startswith("other: "):
            line = f"- {watch.title_of(label, character.name)}: {MEANING.get(label, 'a habit they noticed in this chat')}"
            examples = _examples(chat_obj, label)
            if examples:
                line += ". Seen in this chat: " + "; ".join(f"“{q}”" for q in examples)
        else:  # something they asked Bulba for in their own words
            line = f"- What they asked for: {label}"
        lines.append(line)
    if "repeated_phrase" in habits:
        found = _repeated(text, others)
        if found:
            lines.append("  (repeated from earlier messages: " + "; ".join(f"“{p}”" for p, _ in found) + ")")
    heading = ("## The reply" if whose == "reply" else
               "## Their message (the AI wrote it for them with \"Write my message\"; fix the same habits in it)")
    parts = [f"## The character: {character.name}",
             "## The story so far (summary)\n" + (summary.strip()[:3000] or "(no summary yet)"),
             "## Habits to fix\n" + "\n".join(lines),
             heading + "\n" + text]
    return [{"role": "system", "content": INSTRUCTIONS.read_text(encoding="utf-8")},
            {"role": "user", "content": "\n\n".join(parts)}]


def _parse(text):
    data = watch._parse(text)
    fixes = data.get("fixes") if isinstance(data, dict) else None
    return [f for f in (fixes or []) if isinstance(f, dict)][:MAX_FIXES]


def apply_fixes(text, fixes):
    """Applies the fixes that pass the checks. Returns (new text, [the fixes kept])."""
    kept, new = [], text
    for f in fixes:
        find, replace = str(f.get("find") or ""), str(f.get("replace") or "")
        if not find.strip() or find == replace or new.count(find) != 1:
            continue  # not there, or not exactly once
        if sorted(PROTECTED.findall(find)) != sorted(PROTECTED.findall(replace)):
            continue  # a story-extra marker, a colour tag or a name placeholder would be lost or added
        new = new.replace(find, replace, 1)
        kept.append({"habit": str(f.get("habit") or "")[:80], "before": find, "after": replace})
    changed = sum(len(k["before"]) for k in kept)
    if not kept or changed > max(MAX_CHANGED * len(text), MAX_CHANGED_SHORT):
        return text, []  # nothing usable, or too much rewritten: keep the original
    new = re.sub(r"[ \t]{2,}", " ", new)
    new = re.sub(r"\n{3,}", "\n\n", new).strip()
    return new, kept


def polish_text(user, character, chat_obj, text, others, summary, habits, whose="reply"):
    """One polish pass over `text`. Returns (new text, fixes kept); the text is unchanged when nothing passed."""
    answer = ai_client.complete(user, "polish", _prompt(character, chat_obj, text, others, summary, habits, whose),
                                max_tokens=2000, temperature=0, response_format={"type": "json_object"})
    return apply_fixes(text, _parse(answer))


def polish(user, character, chat_obj, messages, summary=""):
    """Polishes the newest reply with the habits they approved."""
    habits = approved(user)
    if set(habits) <= watch.FREE_LABELS:
        habits = _free_hits(messages, habits) or habits
    return polish_text(user, character, chat_obj, str(messages[-1][2]),
                       others_before(messages, len(messages) - 1), summary, habits)


def habits_for_draft(user, chat_obj, text, others):
    """The approved habits worth a pass over a "Write my message" text ([] = no call)."""
    if watch.chat_data(chat_obj).get("off"):
        return []
    habits = [h for h in approved(user) if h not in NOT_FOR_THEIR_MESSAGE]
    if habits and set(habits) <= watch.FREE_LABELS:
        return free_hits_text(text, others, habits)
    return habits


def record(original, fixes):
    """What's kept with the reply: its text before polishing and what changed."""
    return {"original": original, "fixes": fixes}


def model_choice(user):
    return "chat" if watch.user_data(user).get("fix_model") == "chat" else "bulba"


def page_payload(rec):
    """For the page: how many fixes, what they were, and the original."""
    if not rec:
        return None
    return {"count": len(rec.get("fixes") or []), "fixes": rec.get("fixes") or [], "original": rec.get("original", "")}


def dumps(rec):
    return json.dumps(page_payload(rec) or {}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Bulba in a chat: fix one message when asked, or start fixing a habit automatically
# ---------------------------------------------------------------------------

def _habit_names(args):
    out = []
    for h in args.get("habits") or []:
        h = str(h).strip()
        if h:
            out.append(h if h in watch.LABELS else h[:200])
    return out[:6]


def tool_polish_message(session, args):
    """Fixes habits in one of the chat's messages; Apply puts the fixed text in the chat (the original is kept)."""
    from mainapp import chats
    from mainapp.bulba import agent
    chat = session.chat
    data = chats.read(chat)
    messages = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    habits = _habit_names(args)
    if not habits:
        return {"error": "Say which habits to fix (names from the list, or their words)."}, []
    role = "user" if args.get("whose") == "theirs" else "assistant"
    picks = [i for i, m in enumerate(messages) if m[0] == role]
    try:
        back = max(1, int(args.get("message") or 1))
        index = picks[-back]
    except (TypeError, ValueError, IndexError):
        return {"error": "There's no such message.", "messages_of_that_kind": len(picks)}, []
    agent._check_budget(session)
    agent.set_activity(session, "Fixing the message…")
    text = str(messages[index][2])
    try:
        new, fixes = polish_text(session.user, chat.character, chat, text, others_before(messages, index, role),
                                 data.get("summary") or "", habits, whose="reply" if role == "assistant" else "theirs")
    except ai_client.AIError as e:
        return {"error": str(e)}, [{"type": "error", "text": str(e)}]
    if not fixes:
        return {"result": "No fixes: the message doesn't have those habits, or the rewrite failed the safety checks. "
                          "Tell them plainly."}, []
    summary = []
    for f in fixes:
        summary += [f"{f['habit'] or 'Fix'}:", f"  Before: {f['before']}", f"  After: {f['after'] or '(removed)'}"]
    p = agent._proposal(session, "message_fix", f"Fixed {'reply' if role == 'assistant' else 'message'} "
                        f"({len(fixes)} change{'s' if len(fixes) != 1 else ''})", summary,
                        {"chat_id": chat.id, "index": index, "original": text, "text": new, "fixes": fixes})
    return {"proposal": p["id"], "status": "waiting for Apply (it replaces the message in the chat; the original "
            "stays one click away)"}, [{"type": "proposal", "id": p["id"]}]


def tool_fix_automatically(session, args):
    """Proposes adding habits to the polish list (they press Apply: that's their approval)."""
    from mainapp.bulba import agent
    labels = [h for h in _habit_names(args) if h in watch.LABELS]
    if not labels:
        return {"error": "Use habit names from the list: " + ", ".join(watch.LABELS)}, []
    mine = watch.user_data(session.user)
    new = [h for h in labels if h not in mine["fix"]]
    if not new:
        return {"result": "Those are already fixed automatically."}, []
    who = "your chat model" if mine.get("fix_model") == "chat" else "Bulba's model"
    summary = ["From now on, every new reply gets a quick polish for:", *[f"  {watch.title_of(h)}" for h in new],
               f"Rewritten by {who}: a small extra call when a reply needs it. Stop any time on the Extras page."]
    p = agent._proposal(session, "auto_fix", "Fix automatically: " + ", ".join(watch.title_of(h).lower() for h in new),
                        summary, {"labels": new})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def apply(session, p):
    from mainapp import chats
    data = p["payload"]
    if p["kind"] == "auto_fix":
        mine = watch.user_data(session.user)
        added = [h for h in data["labels"] if h not in mine["fix"]]
        mine["fix"] += added
        watch.save_user_data(session.user, mine)
        p["undo"] = {"added": added}
        return "Done: new replies get polished for that from now on."
    chat = session.chat
    saved = chats.read(chat)
    messages = saved.get("messages") or []
    i = data["index"]
    if not (0 <= i < len(messages)) or messages[i][2] != data["original"]:
        raise ValueError("That message changed since; ask me again.")
    messages[i] = list(chats.with_polish(tuple(messages[i]), data["text"], record(data["original"], data["fixes"])))
    saved["messages"] = messages
    chats.write(chat, saved)
    if i == len(messages) - 1:
        watch.recheck(session.user, chat, [tuple(m) for m in messages])
    return "The fixed version is in the chat now (the original is one click away under it)."


def undo(session, p):
    from mainapp import chats
    data = p["payload"]
    if p["kind"] == "auto_fix":
        mine = watch.user_data(session.user)
        mine["fix"] = [h for h in mine["fix"] if h not in (p.get("undo") or {}).get("added", [])]
        watch.save_user_data(session.user, mine)
        return
    saved = chats.read(session.chat)
    messages = saved.get("messages") or []
    i = data["index"]
    if 0 <= i < len(messages) and messages[i][2] == data["text"]:
        messages[i] = list(chats.with_polish(tuple(messages[i]), data["original"], None))
        saved["messages"] = messages
        chats.write(session.chat, saved)


KINDS = ("message_fix", "auto_fix")
HANDLERS = {"polish_message": tool_polish_message, "fix_automatically": tool_fix_automatically}
TURN_ENDING = set(HANDLERS)


def tool_defs(fn, STR):
    habits = {"type": "array", "items": STR, "maxItems": 6,
              "description": "Habit names: " + ", ".join(watch.LABELS) + "; or, for polish_message only, their "
                             "own words (e.g. 'fewer metaphors')"}
    return [
        fn("polish_message", "Fix habits in one message of this chat, sentence by sentence, keeping everything else. "
           "Shows a proposal with before and after; Apply replaces the message in the chat (the original is kept "
           "under it). Use when they ask to clean up a reply, or their own message written with 'Write my message'.",
           {"habits": habits,
            "message": {"type": "integer", "description": "Which one, counting back: 1 = the latest (default)"},
            "whose": {"type": "string", "enum": ["reply", "theirs"], "description": "The AI's reply (default) or their message"},
            "why": STR}, ["habits"]),
        fn("fix_automatically", "Start fixing habits automatically in every new reply (Bulba's polish). Only when "
           "they say they want that habit gone for good; they confirm with Apply.",
           {"habits": habits, "why": STR}, ["habits"]),
    ]
