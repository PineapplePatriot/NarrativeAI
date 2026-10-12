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
}


def approved(user):
    """The habits they asked to have fixed (Watch must be on)."""
    return list(watch.user_data(user).get("fix") or []) if watch.is_on(user) else []


def due(user, chat_obj, messages):
    """Should the newest reply be polished? Free when it can be decided in code."""
    habits = approved(user)
    if not habits or not messages or messages[-1][0] != "assistant" or watch.chat_data(chat_obj).get("off"):
        return False
    if set(habits) <= watch.FREE_LABELS:  # every habit has a free check: only call when one hits
        return bool(_free_hits(messages, habits))
    return True


def _free_hits(messages, habits):
    text = str(messages[-1][2])
    hits = []
    if "same_openings" in habits and watch.same_openings(text):
        hits.append("same_openings")
    if "repeated_phrase" in habits:
        replies = [i for i, m in enumerate(messages) if m[0] == "assistant"][-watch.WINDOW:]
        if watch.repeated_phrases({i: str(messages[i][2]) for i in replies}, len(messages) - 1):
            hits.append("repeated_phrase")
    return hits


def _examples(chat_obj, label):
    quotes = [e["quote"] for e in watch.chat_data(chat_obj)["log"] if e["label"] == label]
    return quotes[-2:]


def _prompt(user, character, chat_obj, messages, summary, habits):
    lines = []
    for label in habits:
        title = watch.LABELS.get(label, label.replace("other: ", "").capitalize()).replace("{char}", character.name)
        line = f"- {title}: {MEANING.get(label, 'a habit they noticed in this chat')}"
        examples = _examples(chat_obj, label)
        if examples:
            line += ". Seen in this chat: " + "; ".join(f"“{q}”" for q in examples)
        lines.append(line)
    if "repeated_phrase" in habits:
        replies = [i for i, m in enumerate(messages) if m[0] == "assistant"][-watch.WINDOW:]
        found = watch.repeated_phrases({i: str(messages[i][2]) for i in replies}, len(messages) - 1)
        if found:
            lines.append("  (in this reply, repeated from earlier: " + "; ".join(f"“{p}”" for p, _ in found) + ")")
    parts = [f"## The character: {character.name}",
             "## The story so far (summary)\n" + (summary.strip()[:3000] or "(no summary yet)"),
             "## Habits to fix\n" + "\n".join(lines),
             "## The reply\n" + str(messages[-1][2])]
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


def polish(user, character, chat_obj, messages, summary=""):
    """Polishes the newest reply. Returns (new text, fixes kept); the text is unchanged when nothing passed."""
    habits = approved(user)
    text = str(messages[-1][2])
    if set(habits) <= watch.FREE_LABELS:
        habits = _free_hits(messages, habits) or habits
    answer = ai_client.complete(user, "polish", _prompt(user, character, chat_obj, messages, summary, habits),
                                max_tokens=2000, temperature=0, response_format={"type": "json_object"})
    return apply_fixes(text, _parse(answer))


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
