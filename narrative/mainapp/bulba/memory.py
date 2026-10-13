"""
The chat's memory, as the AI sees it: the story summary (its pieces), the pinned note, the trackers and the lore
that fired for the last reply. Bulba in a chat reads it (a short version always, read_memory for everything) and
can propose fixes to the summary or the pinned note (Apply/Undo). The pen menu's "What the AI saw" shows the same.
"""
from mainapp import chats

SUMMARY_IN_CONTEXT = 2500  # characters of the summary Bulba always sees


def _clip(text, n):
    text = str(text or "")
    return text if len(text) <= n else text[:n].rsplit(" ", 1)[0] + " …"


def what_the_ai_saw(chat):
    """What the next reply (or a rewrite of the last one) gets besides the preset and the messages."""
    from mainapp.utils import build_ai_request
    from mainapp.views import pinned_note
    character, user = chat.character, chat.character.author
    data = chats.read(chat)
    messages = data.get("messages") or []
    parts = chats.summary_parts(data, len(messages))
    worldbook = character.worldbook.slug if character.worldbook and character.worldbook.author_id == user.id else None
    built = build_ai_request(user, character, chat=chat, worldbook_slug=worldbook, message=None, guidance=None,
                             persistent_guides=data.get("context_guides") or {}, summary=chats.summary_text(parts))
    report = built.get("LoreReport") or {}
    fired = [r for r in report.get("report") or [] if isinstance(r, dict) and r.get("status") == "included"]
    persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    return {
        "summary": [{"piece": i, "from": p["from"], "to": p["to"], "text": p["text"]} for i, p in enumerate(parts)],
        "pinned_note": pinned_note(data.get("context_guides") or {}),
        "trackers": built["SystemPrompts"].get("StoryState", ""),
        "lore": {"book": report.get("book") or "", "fired": [_entry_title(r) for r in fired][:30],
                 "notes": report.get("notes") or []},
        "persona": persona.get("name") or "",
        "recalled": [r for r in data.get("last_recall") or [] if isinstance(r, dict)],
    }


def _entry_title(r):
    return str(r.get("label") or "entry")


def context_section(chat):
    """The short version for Bulba's context."""
    try:
        saw = what_the_ai_saw(chat)
    except Exception:  # never let a broken lorebook or tracker stop Bulba
        return ""
    summary = "\n\n".join(p["text"] for p in saw["summary"])
    lines = ["### What the AI saw for the last reply (besides the preset and the messages)",
             f"Story summary ({len(saw['summary'])} piece{'s' if len(saw['summary']) != 1 else ''}; read_memory for all "
             "of it with piece numbers): " + (_clip(summary, SUMMARY_IN_CONTEXT) if summary else "none yet"),
             "Pinned note: " + (_clip(saw["pinned_note"], 800) if saw["pinned_note"] else "none"),
             "Trackers: " + (_clip(saw["trackers"], 1200) if saw["trackers"] else "none"),
             "Lore that fired: " + (", ".join(saw["lore"]["fired"]) if saw["lore"]["fired"] else
                                    ("nothing" if saw["lore"]["book"] else "no lorebook")),
             "Old messages brought back by recall (they had fallen out of the context): "
             + ("; ".join(_clip(f"{r.get('who')}: {r.get('text')}", 200) for r in saw["recalled"]) or "none")]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_read_memory(session, args):
    saw = what_the_ai_saw(session.chat)
    return saw, []


def tool_propose_memory_edit(session, args):
    from mainapp.bulba.agent import _proposal
    saw = what_the_ai_saw(session.chat)
    why = str(args.get("why") or "")[:400]
    if "summary_piece" in args:
        try:
            piece = saw["summary"][int(args["summary_piece"])]
        except (TypeError, ValueError, IndexError):
            return {"error": "No such summary piece (read_memory lists them)."}, []
        text = str(args.get("text") or "").strip()[:6000]
        if not text:
            return {"error": "Write the corrected piece."}, []
        p = _proposal(session, "memory_edit", f"Story summary, piece {piece['piece'] + 1}",
                      ["Before:", piece["text"], "After:", text, "Why:", why],
                      {"what": "summary", "piece": piece["piece"], "from": piece["from"], "to": piece["to"],
                       "before": piece["text"], "text": text})
    elif "pinned_note" in args:
        text = str(args.get("pinned_note") or "").strip()[:4000]
        p = _proposal(session, "memory_edit", "Pinned note",
                      ["Before:", saw["pinned_note"] or "(none)", "After:", text or "(none)", "Why:", why],
                      {"what": "pinned", "before": saw["pinned_note"], "text": text})
    else:
        return {"error": "Give summary_piece and text, or pinned_note."}, []
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def _write(session, what, text, expect, piece=None, span=None):
    data = chats.read(session.chat)
    messages = data.get("messages") or []
    if what == "pinned":
        from mainapp.views import pinned_note
        if pinned_note(data.get("context_guides") or {}) != expect:
            raise ValueError("The pinned note changed since; ask me again.")
        data["context_guides"] = {"note": text}
    else:
        parts = chats.summary_parts(data, len(messages))
        if not (0 <= piece < len(parts)) or parts[piece]["text"] != expect or (parts[piece]["from"], parts[piece]["to"]) != span:
            raise ValueError("The summary changed since; ask me again.")
        parts[piece] = {**parts[piece], "text": text}
        data["summary_parts"] = parts
        data["summary"] = chats.summary_text(parts)
        data["summary_upto"] = chats.summary_upto(parts)
    chats.write(session.chat, data)


def apply(session, p):
    d = p["payload"]
    _write(session, d["what"], d["text"], d["before"], d.get("piece"), (d.get("from"), d.get("to")))
    return "Saved: the next reply uses it."


def undo(session, p):
    d = p["payload"]
    _write(session, d["what"], d["before"], d["text"], d.get("piece"), (d.get("from"), d.get("to")))


KINDS = ("memory_edit",)
HANDLERS = {"read_memory": tool_read_memory, "propose_memory_edit": tool_propose_memory_edit}
TURN_ENDING = {"propose_memory_edit"}


def tool_defs(fn, STR):
    return [
        fn("read_memory", "The chat's memory as the AI gets it: every story summary piece (numbered, with the messages "
           "it covers), the pinned note, the trackers, and the lore that fired for the last reply.", {}),
        fn("propose_memory_edit", "Fix the chat's memory: one summary piece (summary_piece + text: the whole corrected "
           "piece) or the pinned note (pinned_note: the whole new note, '' to clear it). They see before and after "
           "and press Apply. Use when the summary got something wrong or left out something that matters, or the "
           "pinned note is stale or fights the story.",
           {"summary_piece": {"type": "integer"}, "text": STR, "pinned_note": STR, "why": STR}, ["why"]),
    ]
