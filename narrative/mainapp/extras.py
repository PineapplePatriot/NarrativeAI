"""
Story extras drawn by the app (function calling): letters and notes, phone screens, relationship milestones.

The model doesn't write HTML: it calls a tool with the content, and the app draws it from a fixed template
(templates/mainapp/partials/story_extra.html), so the layout never breaks and costs no prose. Ops are kept
on the reply like dice rolls (mainapp/game.py), so each swipe has its own. Ideas and wording from
docs/research/preset-second-pass-interactive.md (sections 4A, 4B and 4E).
"""
from django.template.loader import render_to_string

KINDS = {"documents": "Letters, notes and signs", "messages": "Phone and message screens",
         "milestones": "Relationship milestones"}
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
    "milestones": "Relationship milestones (drawn by the app): after a meaningful change between characters, call "
                  "note_milestone with where things stand in ordinary words and the event behind it. Affection, "
                  "trust and closeness can move differently; don't reward every reply with progress.",
}


def tools_for(kinds):
    return [TOOLS[k] for k in kinds]


def rules_for(kinds):
    return "\n\n".join(RULES[k] for k in kinds)


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
    return {"error": f"No tool called {name}."}, []


EXTRA_TYPES = ("document", "messages", "milestone")


def is_extra(op):
    return op.get("type") in EXTRA_TYPES


def render(op):
    return render_to_string("mainapp/partials/story_extra.html", {"op": op})
