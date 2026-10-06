"""Bulba and the story's world: an uploaded card, and lorebooks it writes from wiki research."""
import copy

from mainapp import lorebook

MAX_ENTRIES = 25


def target_character(session):
    """The character Bulba is working on: the chat's, or the newest one made or imported in this setup."""
    from mainapp.models import Character
    if session.chat_id:
        return session.chat.character
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
    rules = regex_rules.for_chat({}, character)
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


def tool_offer_card_upload(session, args):
    return {"status": "upload box shown; they'll send the file or answer"}, [{"type": "card_upload"}]


def tool_defs(fn, STR):
    entry = {"type": "object", "properties": {
        "title": STR,
        "keys": {"type": "array", "items": STR, "description": "Names, aliases and terms that bring it into the story"},
        "content": {"type": "string", "description": "The facts, written as plain description of the world"},
        "always": {"type": "boolean", "description": "Always in the story (only for the core premise, 1-3 entries)"}},
        "required": ["content"]}
    return [
        fn("propose_lorebook", "Propose lore entries for the character's world (added to its lorebook, or a new one). "
           "Research canon with look_up first.",
           {"title": STR, "description": STR, "entries": {"type": "array", "maxItems": MAX_ENTRIES, "items": entry},
            "why": STR}, ["entries", "why"]),
        fn("offer_card_upload", "Show an upload box for a character card they already have (.png or .json from "
           "SillyTavern, Chub and similar). Write your message first.", {}),
    ]


HANDLERS = {"propose_lorebook": tool_propose_lorebook, "offer_card_upload": tool_offer_card_upload}
