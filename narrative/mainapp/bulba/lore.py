"""Bulba and the story's world: an uploaded card, and lorebooks it writes from wiki research."""
import copy

from mainapp import lorebook

MAX_ENTRIES = 25


def target_character(session):
    """The character Bulba is working on: the chat's, the one they asked about, or the newest one made or
    imported in this setup."""
    from mainapp.models import Character
    if session.chat_id:
        return session.chat.character
    if session.focus_id and session.focus.author_id == session.user_id:
        return session.focus
    for p in reversed(session.proposals):
        if p["kind"] == "character" and p["status"] == "applied" and (p.get("result") or {}).get("slug"):
            character = Character.objects.filter(author=session.user, slug=p["result"]["slug"]).first()
            if character:
                return character
    return None


# ---------------------------------------------------------------------------
# A card they already have
# ---------------------------------------------------------------------------

def _clip(text, n):
    text = (text or "").strip()
    return text if len(text) <= n else text[:n] + " […]"


def card_report(character):
    """What Bulba reads about an imported card (it then checks it against the character guide)."""
    from mainapp import regex_rules
    lines = [f"Name: {character.name}",
             f"Description ({len(character.description)} characters):\n{_clip(character.description, 4000)}"]
    for label, value, n in (("Personality", character.personality, 800), ("Scenario", character.scenario, 1200),
                            ("First message", character.initial_message, 2000),
                            ("Example dialogue", character.example_dialogue, 1500)):
        lines.append(f"{label}: {_clip(value, n) if value.strip() else '(empty)'}")
    if character.alternate_greetings:
        lines.append(f"Alternate first messages: {len(character.alternate_greetings)}")
    if character.worldbook:
        book = lorebook.load_worldbook(character.worldbook)
        titles = [e["comment"] or ", ".join(e["keys"][:2]) for e in book["entries"]][:30]
        lines.append(f"Lorebook “{character.worldbook.title}” with {len(book['entries'])} entries: " + "; ".join(titles))
    else:
        lines.append("Lorebook: none")
    if character.system_prompt or character.post_history_instructions:
        lines.append("The card has its own instructions, which replace the preset's main prompt:\n"
                     + _clip(character.system_prompt + "\n" + character.post_history_instructions, 1500))
    rules = regex_rules.card_rules(character)
    if rules:
        lines.append(f"Text rules (regex) on the card: {len(rules)}")
    return "\n\n".join(lines)


def import_card(session, upload):
    """Their card becomes a character, recorded like an applied character proposal (so Undo and Chat now work)."""
    from mainapp import cards
    from mainapp.bulba.agent import _proposal
    character = cards.import_file(session.user, upload.read(), upload.name)
    p = _proposal(session, "character", f"Character: {character.name} (your card)",
                  ["Imported from your file. Bulba can suggest changes; nothing else was touched."],
                  {"imported": True, "name": character.name})
    p["status"] = "applied"
    p["undo"] = {"created": character.id, "worldbook": character.worldbook_id}
    p["result"] = {"slug": character.slug}
    return character, p


# ---------------------------------------------------------------------------
# Lorebooks
# ---------------------------------------------------------------------------

def _entries(raw):
    entries = []
    for i, e in enumerate(raw or []):
        if not isinstance(e, dict):
            continue
        content = str(e.get("content") or "").strip()[:2500]
        keys = [str(k).strip() for k in (e.get("keys") or []) if str(k).strip()][:10]
        always = bool(e.get("always"))
        if not content or not (keys or always):
            continue
        entries.append({"uid": i, "comment": str(e.get("title") or (keys[0] if keys else "Always")).strip()[:120],
                        "keys": keys, "content": content, "constant": always})
    return entries[:MAX_ENTRIES]


def tool_propose_lorebook(session, args):
    from mainapp.bulba.agent import _proposal
    character = target_character(session)
    if character is None:
        return {"error": "There's no character yet; a lorebook is attached to one. Make or import the character first."}, []
    entries = _entries(args.get("entries"))
    if not entries:
        return {"error": "No usable entries: each needs content and either keys or always=true."}, []
    title = str(args.get("title") or f"{character.name}'s world").strip()[:120]
    adding = bool(character.worldbook_id)
    summary = [f"{'Added to' if adding else 'New lorebook for'} {character.name}"
               + (f" (“{character.worldbook.title}”)" if adding else f": {title}")]
    for e in entries:
        trigger = "always in the story" if e["constant"] else "when someone mentions " + ", ".join(e["keys"])
        summary += [f"{e['comment']}:", f"  ({trigger}) {e['content']}"]
    summary += ["Why:", str(args.get("why") or "")[:400]]
    p = _proposal(session, "lorebook", f"Lore: {title}", summary,
                  {"character_id": character.id, "title": title,
                   "description": str(args.get("description") or "").strip()[:500], "entries": entries})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def apply(session, p):
    from django.utils.text import slugify
    from mainapp.models import Character, Worldbook
    data = p["payload"]
    character = Character.objects.filter(author=session.user, id=data["character_id"]).first()
    if character is None:
        raise ValueError("That character is gone.")
    if character.worldbook_id:
        wb = character.worldbook
        book = lorebook.load_worldbook(wb)
        p["undo"] = {"worldbook": wb.id, "book": copy.deepcopy(book)}
        start = max([e["uid"] for e in book["entries"]], default=-1) + 1
        book["entries"] += [{**e, "uid": start + i} for i, e in enumerate(data["entries"])]
        lorebook.save_worldbook(wb, book)
        return f"{len(data['entries'])} entries added to “{wb.title}”."
    base = slugify(data["title"]) or "lorebook"
    slug, n = base, 2
    while Worldbook.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    wb = Worldbook(title=data["title"], slug=slug, description=data["description"], author=session.user)
    lorebook.save_worldbook(wb, {"title": data["title"], "description": data["description"], "entries": data["entries"]})
    character.worldbook = wb
    character.save(update_fields=["worldbook"])
    p["undo"] = {"created": wb.id, "character_id": character.id}
    return f"Lorebook “{wb.title}” made and attached to {character.name}."


def undo(session, p):
    from mainapp.models import Character, Worldbook
    before = p.get("undo") or {}
    if before.get("created"):
        Character.objects.filter(author=session.user, id=before.get("character_id")).update(worldbook=None)
        Worldbook.objects.filter(author=session.user, id=before["created"]).delete()
    elif before.get("worldbook"):
        wb = Worldbook.objects.filter(author=session.user, id=before["worldbook"]).first()
        if wb:
            lorebook.save_worldbook(wb, before["book"])


# ---------------------------------------------------------------------------
# Changing what exists: pick a character, read and edit its lorebook
# ---------------------------------------------------------------------------

def tool_work_on_character(session, args):
    """Setup only: point Bulba at one of the user's existing characters (its card and lorebook)."""
    from mainapp.models import Character
    name = str(args.get("name") or "").strip()
    mine = Character.objects.filter(author=session.user)
    character = mine.filter(name__iexact=name).first() if name else None
    if character is None:
        return {"error": f"No character called “{name}”." if name else "Which one?",
                "characters": list(mine.values_list("name", flat=True)[:50])}, []
    session.focus = character
    return {"working_on": character.name, "card": card_report(character)}, []


def _entry_view(e):
    return {"entry": e["uid"], "title": e["comment"], "keys": e["keys"], "always": e["constant"],
            "on": e["enabled"], "content": e["content"]}


def tool_read_lorebook(session, args):
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    if not character.worldbook_id:
        return {"lorebook": None, "note": f"{character.name} has no lorebook; propose_lorebook makes one."}, []
    book = lorebook.load_worldbook(character.worldbook)
    return {"lorebook": character.worldbook.title, "entries": [_entry_view(e) for e in book["entries"]][:80]}, []


LORE_EDIT_ACTIONS = ("replace", "delete", "disable", "enable")


def edit_book(book, edits):
    """A copy of the book with the edits applied. Raises ValueError on a bad edit."""
    book = copy.deepcopy(book)
    by_uid = {e["uid"]: e for e in book["entries"]}
    for ed in edits:
        action = ed.get("action")
        if action not in LORE_EDIT_ACTIONS:
            raise ValueError(f"Unknown action {action}: use {', '.join(LORE_EDIT_ACTIONS)}.")
        try:
            entry = by_uid[int(ed.get("entry"))]
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"No entry {ed.get('entry')}; read_lorebook lists them.")
        if action == "delete":
            book["entries"].remove(entry)
        elif action in ("disable", "enable"):
            entry["enabled"] = action == "enable"
        else:
            if "content" in ed and str(ed["content"]).strip():
                entry["content"] = str(ed["content"]).strip()[:2500]
            if isinstance(ed.get("keys"), list):
                entry["keys"] = [str(k).strip() for k in ed["keys"] if str(k).strip()][:10]
            if ed.get("title"):
                entry["comment"] = str(ed["title"]).strip()[:120]
            if "always" in ed:
                entry["constant"] = bool(ed["always"])
            if not entry["keys"] and not entry["constant"]:
                raise ValueError(f"Entry {entry['uid']} would never fire: give it keys or make it always on.")
    return book


def tool_propose_lore_edit(session, args):
    from mainapp.bulba.agent import _proposal
    character = target_character(session)
    if character is None or not character.worldbook_id:
        return {"error": "There's no lorebook to change; propose_lorebook makes one."}, []
    edits = [e for e in (args.get("edits") or []) if isinstance(e, dict)][:15]
    if not edits:
        return {"error": "No edits."}, []
    book = lorebook.load_worldbook(character.worldbook)
    try:
        edit_book(book, edits)
    except ValueError as e:
        return {"error": str(e)}, []
    titles = {e["uid"]: e["comment"] or ", ".join(e["keys"][:2]) for e in book["entries"]}
    summary = []
    for ed in edits:
        label = titles.get(int(ed["entry"]), ed["entry"])
        if ed["action"] == "replace":
            summary += [f"Change “{label}”:"] + [f"  {k}: {ed[k]}" for k in ("title", "keys", "content", "always") if k in ed]
        else:
            summary.append(f"{ed['action'].capitalize()}: “{label}”")
    summary += ["Why:", str(args.get("why") or "")[:400]]
    p = _proposal(session, "lore_edit", f"Lore changes: {character.worldbook.title}", summary,
                  {"worldbook_id": character.worldbook_id, "edits": edits})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def apply_lore_edit(session, p):
    from mainapp.models import Worldbook
    wb = Worldbook.objects.filter(author=session.user, id=p["payload"]["worldbook_id"]).first()
    if wb is None:
        raise ValueError("That lorebook is gone.")
    book = lorebook.load_worldbook(wb)
    p["undo"] = {"worldbook": wb.id, "book": copy.deepcopy(book)}
    lorebook.save_worldbook(wb, edit_book(book, p["payload"]["edits"]))
    return f"“{wb.title}” changed. The next reply uses it."


# ---------------------------------------------------------------------------
# A character's theme: background, music and dialogue colour (all optional)
# ---------------------------------------------------------------------------

def tool_propose_theme(session, args):
    import re
    from mainapp import media_library
    from mainapp.bulba.agent import _proposal
    character = target_character(session)
    if character is None:
        return {"error": "No character yet."}, []
    theme, summary = {}, []
    for kind, key, label in (("backgrounds", "background", "Background"), ("music", "music", "Music")):
        name = str(args.get(key) or "").strip()
        if not name:
            continue
        if name.lower() == "none":
            theme[key] = None
            summary.append(f"{label}: none")
            continue
        item = media_library.find(kind, name)
        if item is None:
            return {"error": f"No built-in {key} called “{name}”.",
                    "choices": [i["name"] for i in media_library.built_in(kind)]}, []
        theme[key] = item
        summary.append(f"{label}: {item['name']}")
    color = str(args.get("dialogue_color") or "").strip()
    if color:
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            return {"error": "dialogue_color is a hex colour like #67e8f9."}, []
        theme["dialogue_color"] = color
        summary.append(f"Dialogue colour: {color}")
    if not theme:
        return {"error": "Choose at least a background, music or colour."}, []
    summary += ["Why:", str(args.get("why") or "")[:300]]
    p = _proposal(session, "theme", f"Theme: {character.name}", summary,
                  {"character_id": character.id, "theme": theme})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def apply_theme(session, p):
    from mainapp.models import Character
    data = p["payload"]
    character = Character.objects.filter(author=session.user, id=data["character_id"]).first()
    if character is None:
        raise ValueError("That character is gone.")
    p["undo"] = {"character_id": character.id, "theme": dict(character.theme or {})}
    theme = dict(character.theme or {})
    t = data["theme"]
    if "background" in t:
        theme["bg"] = t["background"]["url"] if t["background"] else ""
    if "music" in t:
        theme["music"] = {"url": t["music"]["url"], "name": t["music"]["name"]} if t["music"] else {}
    if t.get("dialogue_color"):
        theme["dialogue_color"] = t["dialogue_color"]
    character.theme = theme
    character.save(update_fields=["theme"])
    return f"{character.name}'s theme is set; chats with them open with it (unless a chat picked its own)."


def undo_theme(session, p):
    from mainapp.models import Character
    before = p.get("undo") or {}
    Character.objects.filter(author=session.user, id=before.get("character_id")).update(theme=before.get("theme") or {})


def tool_offer_downloads(session, args):
    """Download links for what they have: the active preset, and the character's card and lorebook."""
    from django.urls import reverse
    from mainapp import presets
    want = set(args.get("what") or ["preset", "card", "lorebook"])
    links = []
    if "preset" in want:
        preset = presets.get_active(session.user)
        url = reverse("preset_export", args=[preset.id])
        links += [{"label": f"Preset “{preset.name}”", "url": url},
                  {"label": "Preset for SillyTavern", "url": url + "?format=sillytavern"}]
    character = target_character(session)
    if character and "card" in want:
        url = reverse("character_export", args=[character.slug])
        links += [{"label": f"{character.name}'s card (.png)", "url": url},
                  {"label": f"{character.name}'s card (.json)", "url": url + "?format=json"}]
    if character and character.worldbook_id and "lorebook" in want:
        links.append({"label": f"Lorebook “{character.worldbook.title}” (SillyTavern)",
                      "url": reverse("worldbook_export", args=[character.worldbook.slug]) + "?format=sillytavern"})
    if not links:
        return {"error": "Nothing to download yet."}, []
    return {"shown": [l["label"] for l in links]}, [{"type": "downloads", "links": links}]


def tool_offer_card_upload(session, args):
    return {"status": "upload box shown; they'll send the file or answer"}, [{"type": "card_upload"}]


def tool_defs(fn, STR, setup=True):
    entry = {"type": "object", "properties": {
        "title": STR,
        "keys": {"type": "array", "items": STR, "description": "Names, aliases and terms that bring it into the story"},
        "content": {"type": "string", "description": "The facts, written as plain description of the world"},
        "always": {"type": "boolean", "description": "Always in the story (only for the core premise, 1-3 entries)"}},
        "required": ["content"]}
    edits = {"type": "array", "maxItems": 15, "items": {"type": "object", "properties": {
        "entry": {"type": "integer", "description": "The entry's number from read_lorebook"},
        "action": {"type": "string", "enum": list(LORE_EDIT_ACTIONS)},
        "title": STR, "keys": {"type": "array", "items": STR},
        "content": {"type": "string", "description": "New text (replace)"},
        "always": {"type": "boolean"}}, "required": ["entry", "action"]}}
    from mainapp import media_library
    defs = [
        fn("propose_theme", "Optional: the character's look in chats, from the app's built-in backgrounds and music "
           "(names below; \"none\" clears one) and a dialogue colour. Match them to the character and setting.",
           {"background": {"type": "string", "enum": [i["name"] for i in media_library.built_in("backgrounds")] + ["none"]},
            "music": {"type": "string", "enum": [i["name"] for i in media_library.built_in("music")] + ["none"]},
            "dialogue_color": {"type": "string", "description": "Hex, e.g. #67e8f9; readable on a dark background"},
            "why": STR}, ["why"]),
        fn("read_lorebook", "The character's lorebook entries (numbers, keys, text), before changing any.", {}),
        fn("offer_downloads", "Show download buttons for their preset, the character's card and its lorebook "
           "(each a separate file; SillyTavern-compatible).",
           {"what": {"type": "array", "items": {"type": "string", "enum": ["preset", "card", "lorebook"]},
                     "description": "Leave out for all three"}}, []),
        fn("propose_lore_edit", "Change existing lore entries: rewrite text or keys, switch off, or delete. "
           "Research canon with look_up first when facts are in doubt; new entries go through propose_lorebook.",
           {"edits": edits, "why": STR}, ["edits", "why"]),
        fn("propose_lorebook", "Propose lore entries for the character's world (added to its lorebook, or a new one). "
           "Research canon with look_up first.",
           {"title": STR, "description": STR, "entries": {"type": "array", "maxItems": MAX_ENTRIES, "items": entry},
            "why": STR}, ["entries", "why"]),
    ]
    if setup:
        defs += [
            fn("offer_card_upload", "Show an upload box for a character card they already have (.png or .json from "
               "SillyTavern, Chub and similar). Write your message first.", {}),
            fn("work_on_character", "Work on one of their existing characters (its card and lorebook). Returns the "
               "card; an unknown or empty name returns the list of their characters.", {"name": STR}),
        ]
    return defs


HANDLERS = {"propose_lorebook": tool_propose_lorebook, "offer_card_upload": tool_offer_card_upload,
            "work_on_character": tool_work_on_character, "read_lorebook": tool_read_lorebook,
            "propose_lore_edit": tool_propose_lore_edit, "propose_theme": tool_propose_theme,
            "offer_downloads": tool_offer_downloads}
