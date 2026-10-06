"""
Story extras drawn by the app (function calling): letters and notes, phone screens, relationship milestones.

The model doesn't write HTML: it calls a tool with the content, and the app draws it from a fixed template
(templates/mainapp/partials/story_extra.html), so the layout never breaks and costs no prose. Ops are kept
on the reply like dice rolls (mainapp/game.py), so each swipe has its own. Ideas and wording from
docs/research/preset-second-pass-interactive.md (sections 4A, 4B and 4E).
"""
import re

from django.template.loader import render_to_string

KINDS = {"documents": "Letters, notes and signs", "messages": "Phone and message screens",
         "milestones": "Relationship milestones", "news": "News and rumours", "keepsakes": "Scrapbook keepsakes",
         "choices": "Suggested actions"}
DOC_KINDS = ("letter", "note", "sign", "newspaper", "receipt", "page", "poster", "card")


def kinds_for(user):
    """Which extras the user turned on (Extras page). None by default."""
    from mainapp.models import ChatSettings
    s = ChatSettings.objects.filter(author=user).first()
    chosen = (s.appearance or {}).get("story_extras") if s else None
    return [k for k in KINDS if k in (chosen or [])]


def set_kinds(user, kinds):
    from mainapp.models import ChatSettings
    s, _ = ChatSettings.objects.get_or_create(author=user)
    s.appearance = {**(s.appearance or {}), "story_extras": [k for k in KINDS if k in (kinds or [])]}
    s.save(update_fields=["appearance"])


def ideas_on(user):
    """Bulba's ideas button next to the message box (Extras page). Off by default."""
    from mainapp.models import ChatSettings
    s = ChatSettings.objects.filter(author=user).first()
    return bool((s.appearance or {}).get("bulba_ideas")) if s else False


def set_ideas(user, on):
    from mainapp.models import ChatSettings
    s, _ = ChatSettings.objects.get_or_create(author=user)
    s.appearance = {**(s.appearance or {}), "bulba_ideas": bool(on)}
    s.save(update_fields=["appearance"])


def _fn(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": {
        "type": "object", "properties": properties, "required": list(required)}}}


STR = {"type": "string"}
TOOLS = {
    "documents": _fn(
        "show_document", "Show a readable object the scene really includes (a letter, note, sign, newspaper...). "
        "The app draws it; you still write the scene.",
        {"kind": {"type": "string", "enum": list(DOC_KINDS)},
         "label": {"type": "string", "description": "A few words: what it is and where, e.g. 'Folded note, under the door'"},
         "text": {"type": "string", "description": "Exactly what it says"},
         "detail": {"type": "string", "description": "Optional: what's notable about it (a crossed-out signature, a stain)"}},
        ["kind", "label", "text"]),
    "messages": _fn(
        "show_messages", "Show a phone or message screen when a character checks a device or a message arrives "
        "that the scene would notice.",
        {"owner": {"type": "string", "description": "Whose device it is"},
         "with_whom": {"type": "string", "description": "The other side of the conversation"},
         "messages": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
             "from": STR, "text": STR, "time": {"type": "string", "description": "Story time, e.g. 23:41"},
             "status": {"type": "string", "enum": ["sent", "received", "unsent draft"]}},
             "required": ["from", "text"]}}},
        ["owner", "messages"]),
    "milestones": _fn(
        "note_milestone", "Note a meaningful change between two characters (trust earned or broken, a first, a "
        "confession). Not every reply; it can go backwards.",
        {"who": {"type": "string", "description": "The character whose feelings changed"},
         "toward": {"type": "string", "description": "Toward whom"},
         "now": {"type": "string", "description": "Where things stand now, in plain words, e.g. 'trusts you, warily'"},
         "because": {"type": "string", "description": "The event that caused it"}},
        ["who", "now", "because"]),
    "news": _fn(
        "show_news", "Show news the characters come across (a paper, a noticeboard, gossip, a feed), with where "
        "each item comes from and how sure it is.",
        {"medium": {"type": "string", "description": "Where it's seen or heard, e.g. 'station noticeboard'"},
         "items": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
             "headline": STR, "source": STR,
             "status": {"type": "string", "enum": ["confirmed", "claim", "rumour"]}},
             "required": ["headline", "status"]}}},
        ["medium", "items"]),
    "keepsakes": _fn(
        "note_keepsake", "Add a keepsake to the scrapbook when something becomes a shared memory worth keeping "
        "(not every reply).",
        {"title": {"type": "string", "description": "A few words, e.g. 'First terrible pancakes'"},
         "detail": {"type": "string", "description": "One specific detail of it, e.g. 'kept the scorched recipe card'"}},
        ["title"]),
    "choices": _fn(
        "suggest_actions", "After your reply, suggest a few things the user's character could do next. They are "
        "only suggestions: never act on them.",
        {"actions": {"type": "array", "minItems": 2, "maxItems": 4, "items": {"type": "string"},
                     "description": "Short, distinct, plausible actions in the user's voice, e.g. 'Ask about the "
                                    "missing page'"}},
        ["actions"]),
}
TOOL_KIND = {t["function"]["name"]: kind for kind, t in TOOLS.items()}

RULES = {
    "documents": "Readable objects (drawn by the app): when the scene genuinely includes something readable, you "
                 "may call show_document. Its wording, date or damage should carry information that matters; keep "
                 "ordinary narration outside it. Don't invent a document just to show one, and don't add one to "
                 "every reply.",
    "messages": "Phone screens (drawn by the app): call show_messages only when a character consults a device or "
                "a notification arrives that the scene would notice. Use the sender, a story time (not real time) "
                "and short texts; mark unsent drafts. Others know a message's contents only if they see it or are "
                "told.",
    "news": "News (drawn by the app): when the characters come across a news source (a paper, a noticeboard, "
            "gossip at the bar, a feed), you may call show_news with up to three relevant items. Say where each "
            "comes from and whether it's confirmed, a claim or a rumour: a rumour can be wrong. News can matter "
            "later without interrupting the current exchange.",
    "keepsakes": "Scrapbook (kept by the app): when an event becomes a meaningful shared memory, call "
                 "note_keepsake with a short title and one specific detail. Use what actually happened; don't "
                 "invent a sentimental moment, and not every reply.",
    "choices": "Suggested actions (shown as buttons): after writing your reply, call suggest_actions with two to "
               "four distinct, plausible things {{user}} could do next, in their voice. They are only "
               "suggestions: the story never treats them as done until {{user}} writes or picks one.",
    "milestones": "Relationship milestones (drawn by the app): after a meaningful change between characters, call "
                  "note_milestone with where things stand in ordinary words and the event behind it. Affection, "
                  "trust and closeness can move differently; don't reward every reply with progress.",
}


def tools_for(kinds):
    return [TOOLS[k] for k in kinds]


PLACING = ("Each of these tools answers with a marker like [[extra 1]]: put it on its own line in your reply where "
           "the object appears in the story, and write the scene around it as usual.")


def rules_for(kinds):
    return "\n\n".join([RULES[k] for k in kinds] + ([PLACING] if kinds else []))


def _s(value, n):
    return str(value or "").strip()[:n]


def run_tool(name, args):
    """Turn a call into an op (validated and trimmed). Returns (result for the model, ops)."""
    if name == "show_document":
        if not _s(args.get("text"), 10):
            return {"error": "The document needs its text."}, []
        kind = args.get("kind") if args.get("kind") in DOC_KINDS else "note"
        op = {"type": "document", "kind": kind, "label": _s(args.get("label"), 120) or kind.capitalize(),
              "text": _s(args.get("text"), 3000), "detail": _s(args.get("detail"), 300)}
        return {"shown": True}, [op]
    if name == "show_messages":
        msgs = [{"from": _s(m.get("from"), 60), "text": _s(m.get("text"), 600), "time": _s(m.get("time"), 20),
                 "status": m.get("status") if m.get("status") in ("sent", "received", "unsent draft") else "received"}
                for m in (args.get("messages") or [])[:8] if isinstance(m, dict) and _s(m.get("text"), 600)]
        if not msgs:
            return {"error": "No messages to show."}, []
        owner = _s(args.get("owner"), 60)
        for m in msgs:  # the owner's own messages sit on the right
            m["mine"] = m["from"].lower() == owner.lower()
        op = {"type": "messages", "owner": owner, "with_whom": _s(args.get("with_whom"), 60), "messages": msgs}
        return {"shown": True}, [op]
    if name == "note_milestone":
        if not (_s(args.get("who"), 60) and _s(args.get("now"), 120)):
            return {"error": "Say who and where things stand."}, []
        op = {"type": "milestone", "who": _s(args.get("who"), 60), "toward": _s(args.get("toward"), 60),
              "now": _s(args.get("now"), 120), "because": _s(args.get("because"), 300)}
        return {"noted": True}, [op]
    if name == "show_news":
        items = [{"headline": _s(i.get("headline"), 200), "source": _s(i.get("source"), 80),
                  "status": i.get("status") if i.get("status") in ("confirmed", "claim", "rumour") else "rumour"}
                 for i in (args.get("items") or [])[:3] if isinstance(i, dict) and _s(i.get("headline"), 200)]
        if not items:
            return {"error": "No news items."}, []
        return {"shown": True}, [{"type": "news", "medium": _s(args.get("medium"), 80) or "News", "items": items}]
    if name == "note_keepsake":
        if not _s(args.get("title"), 80):
            return {"error": "The keepsake needs a title."}, []
        return {"kept": True}, [{"type": "keepsake", "title": _s(args.get("title"), 80),
                                 "detail": _s(args.get("detail"), 300)}]
    if name == "suggest_actions":
        actions = [_s(a, 160) for a in (args.get("actions") or [])[:4] if _s(a, 160)]
        if len(actions) < 2:
            return {"error": "Suggest two to four actions."}, []
        return {"shown": True, "note": "No marker needed: these appear as buttons under the reply."}, [
            {"type": "choices", "actions": actions}]
    return {"error": f"No tool called {name}."}, []


EXTRA_TYPES = ("document", "messages", "milestone", "news", "keepsake", "choices")
UNPLACED = ("choices",)  # always under the reply, never in the text, never in the story's memory
MARKER = re.compile(r"\[\[extra (\d+)\]\]")


def marker(n):
    return f"[[extra {n}]]"


def place(text, ops):
    """Make sure each extra has its marker in the reply: where the model put it, else after the paragraph it
    was shown in (if the model had already written some), else at the end. The page puts the drawing there."""
    have = {int(n) for n in MARKER.findall(text)}
    for op in sorted((o for o in ops if is_extra(o) and o.get("type") not in UNPLACED
                      and o.get("n") not in have and o.get("n")),
                     key=lambda o: -o.get("at", 0)):
        at = op.get("at", 0)
        if 0 < at < len(text):
            cut = text.find("\n\n", at)
            cut = len(text) if cut < 0 else cut
            text = text[:cut].rstrip() + f"\n\n{marker(op['n'])}\n\n" + text[cut:].lstrip()
        else:
            text = text.rstrip() + f"\n\n{marker(op['n'])}"
    return text


def compact(op):
    """What the model reads back in later turns, instead of the drawing."""
    if op.get("type") == "document":
        return f"[{op['kind'].capitalize()} shown: {op['label']}. It reads: {op['text']}" + (
            f" ({op['detail']})" if op.get("detail") else "") + "]"
    if op.get("type") == "messages":
        lines = "; ".join(f"{m['from']}{' (unsent)' if m['status'] == 'unsent draft' else ''}: {m['text']}"
                          for m in op["messages"])
        return f"[{op['owner']}'s phone{', with ' + op['with_whom'] if op.get('with_whom') else ''}: {lines}]"
    if op.get("type") == "news":
        return f"[{op['medium']}: " + "; ".join(
            f"{i['headline']} ({i['status']}{', ' + i['source'] if i['source'] else ''})" for i in op["items"]) + "]"
    if op.get("type") == "keepsake":
        return f"[Keepsake: {op['title']}{' - ' + op['detail'] if op.get('detail') else ''}]"
    if op.get("type") == "milestone":
        return f"[Milestone: {op['who']}{' toward ' + op['toward'] if op.get('toward') else ''} now {op['now']}" + (
            f", after {op['because']}" if op.get("because") else "") + "]"
    return ""


def for_prompt(text, ops):
    """A saved reply as the model should read it later: markers become short descriptions of what was shown."""
    by_n = {o.get("n"): o for o in ops if is_extra(o) and o.get("type") not in UNPLACED}
    if not by_n:
        return text
    text = MARKER.sub(lambda m: compact(by_n[int(m.group(1))]) if int(m.group(1)) in by_n else "", text)
    missing = [compact(o) for n, o in by_n.items() if not n]  # older extras without a number
    return "\n\n".join([text.rstrip()] + missing) if missing else text


def strip_markers(text):
    return MARKER.sub("", text)


def is_extra(op):
    return op.get("type") in EXTRA_TYPES


def render(op):
    return render_to_string("mainapp/partials/story_extra.html", {"op": op})


def milestones(messages):
    """The latest milestone for each pair, from the replies on screen (for the Milestones tracker)."""
    from mainapp import chats
    latest = {}
    for m in messages:
        for op in chats.game_of(m):
            if op.get("type") == "milestone":
                latest[(op["who"].lower(), op.get("toward", "").lower())] = {
                    "who": op["who"], "toward": op.get("toward", ""), "now": op["now"], "because": op.get("because", "")}
    return list(latest.values())


def keepsakes(messages):
    """Every keepsake from the replies on screen, oldest first (for the Scrapbook tracker)."""
    from mainapp import chats
    found = {}
    for m in messages:
        for op in chats.game_of(m):
            if op.get("type") == "keepsake":
                found[op["title"].lower()] = {"title": op["title"], "detail": op.get("detail", "")}
    return list(found.values())
