"""
Bulba inside a chat: "my replies are too long", "he sounds like a therapist". Bulba sees the recent chat,
what the model thought before its last reply, the active preset and the character card, works out what
causes the problem, and proposes one small change: a preset block edit or a card edit. retry_reply shows
the last reply rewritten with that change before they apply it.

Runs through agent.run_turn (same loop, money limits and proposals as setup); this module supplies the
instructions, the context and the tools for sessions with mode "chat".
"""
import copy
import uuid
from pathlib import Path

from mainapp import ai_client, chats, extras, game, presets, thinking
from mainapp.bulba import control, library, lore, tune

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "bulba"
CARD_FIELDS = ("description", "personality", "scenario", "example_dialogue", "initial_message")
RECENT = 6           # messages of the chat Bulba sees
MESSAGE_CHARS = 1500
THOUGHTS_CHARS = 2500


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

def _clip(text, n):
    text = str(text or "")
    return text if len(text) <= n else text[:n] + " […]"


def _preset_outline(preset):
    lines = []
    for b in preset["blocks"]:
        if b["kind"] == "header":
            lines.append(f"  -- {b['name']} --")
        elif b["kind"] == "marker":
            lines.append(f"  [{'on' if b['enabled'] else 'off'}] slot: {b['name']}")
        else:
            words = len(b["content"].split())
            chance = ", adds chance" if library.CHANCE.search(b["content"]) else ""
            lines.append(f"  [{'on' if b['enabled'] else 'off'}] {b['name']} ({words} words{chance})")
    return "\n".join(lines)


def _lore_line(character):
    if not character.worldbook_id:
        return "None."
    from mainapp import lorebook
    entries = lorebook.load_worldbook(character.worldbook)["entries"]
    titles = [e["comment"] or ", ".join(e["keys"][:2]) for e in entries][:30]
    return f"“{character.worldbook.title}”, {len(entries)} entries: " + "; ".join(titles)


def context(session):
    from mainapp.views import prompt_names
    chat = session.chat
    character = chat.character
    user = session.user
    data = chats.read(chat)
    messages = [m for m in data.get("messages") or [] if isinstance(m, (list, tuple)) and len(m) > 2]
    persona = data.get("persona") if isinstance(data.get("persona"), dict) else {}
    names = prompt_names(user, character, persona)
    active = presets.get_active(user)
    preset = presets.normalize(active.data)

    recent = []
    for m in messages[-RECENT:]:
        who = names["user"] if m[0] == "user" else character.name
        recent.append(f"{who}: {_clip(m[2], MESSAGE_CHARS)}")
    last_ai = next((m for m in reversed(messages) if m[0] == "assistant"), None)
    thoughts = chats.reasoning_of(last_ai) if last_ai else ""
    _, model = ai_client.resolve(user, "chat")

    parts = [
        f"## This chat\nCharacter: {character.name}. The user plays {names['user']}. Chat model: {model}. "
        f"Messages so far: {len(messages)}. Dice and inventory: "
        f"{game.MODE_LABELS[game.mode_for(user, character)].lower()} (Extras page; per character on its Trackers page). "
        f"Story extras: {', '.join(extras.KINDS[k].lower() for k in extras.kinds_for(user)) or 'off'}.",
        "### Character card\n" + "\n\n".join(
            f"{f}: {_clip(getattr(character, f), 2500)}" for f in CARD_FIELDS if getattr(character, f)),
        "### Lorebook\n" + _lore_line(character),
        "### The user in this chat\n" + _clip(
            (persona.get("description") if persona.get("name") else getattr(user, "persona_description", "")) or
            "(no description)", 800),
        f"### Active preset: {active.name}\n{_preset_outline(preset)}\n"
        "(read_block shows a block's text; text rules: "
        f"{sum(1 for r in preset['regex'] if r['enabled'])} on)",
        "### The last messages\n" + ("\n\n".join(recent) if recent else "(none yet)"),
        "### What the model thought before its last reply\n" + (_clip(thoughts, THOUGHTS_CHARS) if thoughts
                                                                  else "(nothing: this model didn't send its thinking)"),
    ]
    return "\n\n".join(parts)


def system_prompt(session):
    from mainapp.bulba import agent
    text = (DATA_DIR / "doctor.md").read_text(encoding="utf-8")
    profile = agent.target_profile(session)
    guides = [(DATA_DIR / "guides" / f"{g}.md").read_text(encoding="utf-8") for g in ("presets", "characters", "lore", "writing", "tuning")]
    pending = [f"- {p['id']} {p['kind']}: {p['title']} ({p['status']})" for p in session.proposals]
    return "\n\n".join(filter(None, [
        text, *guides,
        agent.model_knowledge(profile) if profile else "",
        context(session),
        f"## Session\nBudget: ${session.spent:.2f} of ${session.budget:.2f} spent.",
        "Proposals so far:\n" + "\n".join(pending) if pending else "",
    ]))


def opening(session):
    character = session.chat.character.name
    session.events = [{"type": "bulba", "text": (
        f"Hi. Something off in your chat with {character}? Tell me what bugs you, in your own words, "
        "and I'll look at the chat, the preset and the card to find what causes it."),
        "choices": [{"label": "Replies are too long"}, {"label": "Replies are too short"},
                    {"label": f"{character} sounds off"}, {"label": "It writes my actions for me"},
                    {"label": "Nothing happens in the story"}]}]
    session.messages = [{"role": "assistant", "content": session.events[0]["text"]}]
    session.stage = "chat"


# ---------------------------------------------------------------------------
# Edits
# ---------------------------------------------------------------------------

EDIT_ACTIONS = ("replace", "append", "enable", "disable", "add")


def apply_edits(preset, edits):
    """A copy of the normalized preset with block edits applied. Raises ValueError on a bad edit."""
    preset = copy.deepcopy(preset)
    for e in edits:
        action, name = e.get("action"), str(e.get("block") or "").strip()
        if action not in EDIT_ACTIONS:
            raise ValueError(f"Unknown edit action: {action}")
        if action == "add":
            if any(b["name"] == name for b in preset["blocks"]):
                raise ValueError(f"“{name}” is already in the preset; switch it on or edit it instead.")
            if not str(e.get("content") or "").strip():
                raise ValueError("A new block needs content.")
            block = presets.normalize_block({"name": name or "Bulba's fix", "kind": "prompt",
                                             "content": e["content"]})
            history = next((i for i, b in enumerate(preset["blocks"]) if b.get("marker") == "chat_history"),
                           len(preset["blocks"]))
            preset["blocks"].insert(history, block)
            continue
        block = next((b for b in preset["blocks"] if b["name"] == name and b["kind"] != "header"), None)
        if block is None:
            raise ValueError(f"No block called “{name}” in the active preset.")
        if action in ("enable", "disable"):
            block["enabled"] = action == "enable"
        else:
            if block["kind"] != "prompt":
                raise ValueError(f"“{name}” is a slot, not text; it can only be switched on or off.")
            text = str(e.get("content") or "")
            if not text.strip():
                raise ValueError("The edit needs text.")
            for macro in ("{{char}}", "{{user}}"):
                if action == "replace" and macro in block["content"] and macro not in text:
                    raise ValueError(f"Your replacement for “{name}” dropped {macro}; keep it.")
            block["content"] = text if action == "replace" else (block["content"].rstrip() + "\n" + text.strip())
    return preset


def _edit_line(e):
    action, name = e.get("action"), e.get("block") or "Bulba's fix"
    if action in ("enable", "disable"):
        return f"Switch {'on' if action == 'enable' else 'off'}: {name}"
    verb = {"replace": "Rewrite", "append": "Add to", "add": "New block"}[action]
    return f"{verb}: {name}\n  {_clip(e.get('content'), 600)}"


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def tool_read_block(session, args):
    preset = presets.normalize(presets.get_active(session.user).data)
    name = str(args.get("block") or "").strip()
    block = next((b for b in preset["blocks"] if b["name"] == name), None)
    if block is None:
        return {"error": f"No block called “{name}”. The outline lists the names."}, []
    return {"block": name, "on": block["enabled"], "kind": block["kind"],
            "content": block["content"][:8000] if block["kind"] == "prompt" else "(a slot filled by the app)"}, []


def tool_propose_preset_edit(session, args):
    from mainapp.bulba.agent import _proposal
    edits = [e for e in (args.get("edits") or []) if isinstance(e, dict)][:6]
    if not edits:
        return {"error": "No edits."}, []
    for e in edits:  # a library block goes in word for word
        if e.get("from_library"):
            block = library.get(e["from_library"])
            if block is None:
                return {"error": f"No library block “{e['from_library']}”; use find_practice for the exact name."}, []
            if library.needs_filling(block):
                return {"error": "That wording has [bracketed] parts: fill them in and add it as content instead."}, []
            e.update(action="add", block=block["name"], content=block["content"])
            e.pop("from_library")
    active = presets.get_active(session.user)
    try:
        apply_edits(presets.normalize(active.data), edits)
    except ValueError as e:
        return {"error": str(e)}, []
    p = _proposal(session, "preset_edit", f"Preset change: {active.name}",
                  [*(_edit_line(e) for e in edits), "Why:", str(args.get("why") or "")[:400]],
                  {"preset_id": active.id, "edits": edits})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_propose_card_edit(session, args):
    from mainapp.bulba.agent import _proposal
    fields = {f: str(args.get(f)).strip()[:40000] for f in CARD_FIELDS if isinstance(args.get(f), str) and args.get(f).strip()}
    if not fields:
        return {"error": "Change at least one field (description, personality, scenario, example_dialogue)."}, []
    character = lore.target_character(session)
    if character is None:
        return {"error": "There's no character to change yet."}, []
    summary = []
    for f, text in fields.items():
        summary += [f"{f.replace('_', ' ').capitalize()}:", text]
    summary += ["Why:", str(args.get("why") or "")[:400]]
    p = _proposal(session, "card_edit", f"Card change: {character.name}", summary,
                  {"character_id": character.id, "fields": fields})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_retry_reply(session, args):
    """The last reply again, with a proposal's change applied only for this try."""
    from mainapp.bulba import agent
    from mainapp.views import build_chat_request
    chat = session.chat
    preset, character = None, None
    proposal = next((p for p in session.proposals if p["id"] == args.get("from_proposal")), None)
    if args.get("from_proposal") and proposal is None:
        return {"error": "No proposal with that id."}, []
    if proposal and proposal["kind"] == "preset_edit":
        try:
            preset = apply_edits(presets.normalize(presets.get_active(session.user).data), proposal["payload"]["edits"])
        except ValueError as e:
            return {"error": str(e)}, []
    elif proposal and proposal["kind"] == "card_edit":
        character = copy.copy(chat.character)
        for f, text in proposal["payload"]["fields"].items():
            setattr(character, f, text)
    agent._check_budget(session)
    model_name = (agent.target_profile(session) or {}).get("name", "your model")
    agent.set_activity(session, f"Rewriting the last reply with {model_name}…")
    try:
        built = build_chat_request(session.user, chat, preset=preset, character=character)
        message, cost = ai_client.complete_message(session.user, "chat", built["messages"], **built["params"])
    except ai_client.AIError as e:
        return {"error": str(e)}, [{"type": "error", "text": str(e)}]
    session.spent += cost or 0
    text = thinking.split(message.get("content") or "")[1].strip()
    label = "With the change" if proposal else "Again, as it is"
    return ({"rewritten_reply": text, "note": "They see it as a single sample with Like / Not quite buttons."},
            [{"type": "samples", "model": model_name, "character": chat.character.name, "scenario": "",
              "user_turn": "", "samples": [{"label": label, "text": text}]}])


STR = {"type": "string"}


def _fn(name, description, properties, required=()):
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


CARD_EDIT_TOOL = _fn("propose_card_edit", "Propose changes to this character's card (only the fields you change).",
            {"description": STR, "personality": STR, "scenario": STR, "example_dialogue": STR,
             "initial_message": {"type": "string", "description": "The first message (only new chats start with it)"},
             "why": STR}, ["why"])


def tools():
    from mainapp.bulba import agent
    keep = {"offer_choices", "record_preference", "get_starter", "find_practice", "read_practice", "look_up",
            "propose_lorebook", "propose_extras", "read_lorebook", "propose_lore_edit", "propose_theme",
            "offer_downloads", *tune.HANDLERS}
    base = [t for t in agent.TOOLS if t["function"]["name"] in keep]
    return base + [
        _fn("read_block", "The full text of one block of the active preset (names are in the outline).",
            {"block": STR}, ["block"]),
        _fn("propose_preset_edit", "Propose changes to the active preset (they press Apply; Undo puts it back). "
            "Smallest change that fixes the problem; read a block before rewriting it.",
            {"edits": {"type": "array", "maxItems": 6, "items": {"type": "object", "properties": {
                "action": {"type": "string", "enum": list(EDIT_ACTIONS),
                           "description": "replace a block's text, append to it, switch it on/off, or add a new block"},
                "block": {"type": "string", "description": "The block's name (for add: the new block's name)"},
                "content": {"type": "string", "description": "New text (replace/append/add)"},
                "from_library": {"type": "string", "description": "Instead of content: add this library block "
                                 "word for word (exact name from find_practice)"}},
                "required": ["action", "block"]}},
             "why": STR}, ["edits", "why"]),
        CARD_EDIT_TOOL,
        *control.tool_defs(_fn, STR),
        _fn("retry_reply", "Rewrite the last AI reply of this chat with their chat model: with a proposal's change "
            "applied just for this try (from_proposal), or as things are now. Costs one reply.",
            {"from_proposal": {"type": "string", "description": "A preset or card proposal id; leave out to retry as is"}}),
    ]


HANDLERS = {"read_block": tool_read_block, "propose_preset_edit": tool_propose_preset_edit, **lore.HANDLERS,
            **tune.HANDLERS,
            **control.HANDLERS,
            "propose_card_edit": tool_propose_card_edit, "retry_reply": tool_retry_reply}


# ---------------------------------------------------------------------------
# Apply / undo
# ---------------------------------------------------------------------------

def apply(session, p):
    from mainapp.models import Character, Preset
    user, data = session.user, p["payload"]
    if p["kind"] == "preset_edit":
        obj = Preset.objects.filter(user=user, id=data["preset_id"]).first()
        if obj is None:
            raise ValueError("That preset is gone.")
        before = copy.deepcopy(obj.data)
        obj.data = apply_edits(presets.normalize(obj.data), data["edits"])
        obj.save(update_fields=["data", "time_update"])
        p["undo"] = {"preset_id": obj.id, "data": before}
        return f"“{obj.name}” changed. The next reply uses it."
    if p["kind"] == "card_edit":
        character = Character.objects.filter(author=user, id=data["character_id"]).first()
        if character is None:
            raise ValueError("That character is gone.")
        p["undo"] = {"character_id": character.id, "fields": {f: getattr(character, f) for f in data["fields"]}}
        for f, text in data["fields"].items():
            setattr(character, f, text)
        character.save()
        return f"{character.name}'s card changed. The next reply uses it."
    raise ValueError("Unknown proposal.")


def undo(session, p):
    from mainapp.models import Character, Preset
    before = p.get("undo") or {}
    if p["kind"] == "preset_edit":
        Preset.objects.filter(user=session.user, id=before.get("preset_id")).update(data=before.get("data"))
    elif p["kind"] == "card_edit":
        character = Character.objects.filter(author=session.user, id=before.get("character_id")).first()
        if character:
            for f, text in (before.get("fields") or {}).items():
                setattr(character, f, text)
            character.save()
