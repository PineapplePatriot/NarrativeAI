"""
Bulba makes custom chat looks (mainapp/chat_looks.py): from what they describe, or from an inspiration picture
they send (Bulba's eyes describe its colours, fonts, shapes and decorations: mainapp/bulba/vision.py).

- read_look_options: every choice the recipe has (fonts and what they feel like, bubble shapes, frames,
  backgrounds, textures, effects, sounds), and the character's current look.
- propose_chat_look: the recipe, as a card they Apply (it becomes the character's chat style; Undo puts the old
  one back). The chat page shows it after Apply.
"""
from mainapp import chat_looks


def _character(session):
    from mainapp.bulba import lore
    return lore.target_character(session)


def tool_read_look_options(session, args):
    from mainapp import media_library, translation
    character = _character(session)
    current = chat_looks.clean((character.theme or {}).get("look")) if character else None
    reading = translation.reading_language(session.user)
    pictures = media_library.built_in("backgrounds")
    if character and (character.theme or {}).get("bg"):
        pictures = [{"name": f"{character.name}'s own background", "url": character.theme["bg"]}] + pictures
    return {"options": chat_looks.guide(), "color_keys": list(chat_looks.COLOR_KEYS),
            "current_look": current, "character": character.name if character else None,
            "backgrounds": pictures,
            "their_shelf": [{"name": i["look"]["name"], "look": i["look"]} for i in chat_looks.shelf(session.user)][:10],
            "shelf_note": ("Their shelf holds every look they've made; any chat can wear one (pen menu → Your looks). "
                           "To give this character one of them, propose_chat_look with that look."),
            "reading_language": reading or "English",
            "cyrillic": ("They read the story in a language with Cyrillic letters: prefer fonts that have them. If the "
                         "look they want needs one that doesn't (the options say which), say so in one line and offer "
                         "the nearest one with Cyrillic; keeping theirs is fine too (Cyrillic shows in its partner)."
                         if reading in ("uk", "ru", "be", "bg", "sr", "mk", "kk") else ""),
            "how": ("Colours are #rrggbb. page/page2/page3: the background (and its blobs or pattern); surface: header, "
                    "input and panels; bubble_ai / bubble_user: the message bubbles; text and muted: the writing (keep "
                    "strong contrast with the bubbles); accent / accent2: name tags, buttons, highlights; outline: "
                    "lines and hard shadows; effect: the light effect's colour. base 'light' or 'dark' is the overall "
                    "brightness. From a picture: match its palette and mood first, then its shapes (hand-drawn lines "
                    "→ wobbly + sketch; stickers → sticker frame and buttons, offset shadows), its lettering (pick the "
                    "nearest font), and its decorations (sparkles, petals...).")}, []


def tool_propose_chat_look(session, args):
    from mainapp.bulba.agent import _proposal
    character = _character(session)
    if character is None:
        return {"error": "There's no character to dress yet: the look belongs to a character's chats."}, []
    current = chat_looks.clean((character.theme or {}).get("look"))
    if isinstance(args.get("changes"), dict) and current:  # a small change to the look they have
        recipe = chat_looks.merge(current, args["changes"])
        summary = [f"Changes to “{current['name']}”:"] + chat_looks.changes(current, recipe)
    else:
        recipe = chat_looks.clean(args.get("look"))
        if recipe is None:
            return {"error": "Give the whole look (look), or for the look they have, only what changes (changes)."}, []
        summary = chat_looks.summary(recipe)
    summary += (["Why:", str(args["why"])[:400]] if args.get("why") else [])
    p = _proposal(session, "chat_look", f"Chat look for {character.name}", summary,
                  {"character_id": character.id, "look": recipe})
    return {"proposal": p["id"], "status": "waiting for Apply",
            "note": "After Apply the chat page reloads with it; they can switch back in the pen menu (Chat style)."}, \
        [{"type": "proposal", "id": p["id"]}]


def apply(session, p):
    from mainapp.models import Character
    data = p["payload"]
    character = Character.objects.filter(author=session.user, id=data["character_id"]).first()
    if character is None:
        raise ValueError("That character is gone.")
    theme = dict(character.theme or {})
    p["undo"] = {"character_id": character.id, "look": theme.get("look"), "skin": theme.get("skin")}
    theme["look"], theme["skin"] = chat_looks.clean(data["look"]), "custom"
    character.theme = theme
    character.save(update_fields=["theme"])
    chat_looks.keep(session.user, theme["look"])  # and on their shelf, to wear in any chat
    return f"{character.name}'s chats now wear “{theme['look']['name']}” (pen menu → Chat style to switch)."


def undo(session, p):
    from mainapp.models import Character
    before = p.get("undo") or {}
    character = Character.objects.filter(author=session.user, id=before.get("character_id")).first()
    if character is None:
        return
    theme = dict(character.theme or {})
    for key in ("look", "skin"):
        if before.get(key):
            theme[key] = before[key]
        else:
            theme.pop(key, None)
    character.theme = theme
    character.save(update_fields=["theme"])


_enum = lambda values, about="": {"type": "string", "enum": list(values), **({"description": about} if about else {})}
_hex = {"type": "string", "description": "#rrggbb"}
# Every choice spelled out, so the model picks from the lists (fonts by key: read_look_options says what each feels like
# and which have Cyrillic letters)
RECIPE_SCHEMA = {
    "name": {"type": "string"}, "base": _enum(("light", "dark")),
    "colors": {"type": "object", "properties": {k: _hex for k in chat_looks.COLOR_KEYS}},
    "font": _enum(chat_looks.FONTS, "the font key for the text"), "heading_font": _enum(chat_looks.FONTS, "for names and titles"),
    "size": _enum(chat_looks.SIZES), "bold": {"type": "boolean"},
    "bubble": {"type": "object", "properties": {"shape": _enum(chat_looks.SHAPES), "outline": _enum(chat_looks.OUTLINES),
                                                "shadow": _enum(chat_looks.SHADOWS), "name_tag": _enum(chat_looks.NAME_TAGS),
                                                "wide": {"type": "boolean"}}},
    "frame": _enum(chat_looks.FRAMES), "background": _enum(chat_looks.BACKGROUNDS), "texture": _enum(chat_looks.TEXTURES),
    "effect": _enum(chat_looks.EFFECTS), "buttons": _enum(chat_looks.BUTTONS), "sound": _enum(chat_looks.SOUNDS),
    "picture": {"type": "string", "description": "for background 'picture': a URL from read_look_options backgrounds"},
    "veil": {"type": "integer", "description": "0-90"},
}


def tool_defs(fn, STR):
    return [
        fn("read_look_options", "Every choice a custom chat look has (fonts, bubble shapes, outlines, name tags, "
           "picture frames, backgrounds, textures, effects, sounds) and the character's current look. Read it "
           "before proposing a look.", {}),
        fn("propose_chat_look", "A custom look for the chat page (colours, fonts, bubbles, frames, effects, sound), "
           "from what they described or an inspiration picture they sent. They press Apply; it becomes the "
           "character's chat style. For a small change to the look they have (another background colour, a picture "
           "behind the chat, a different font), give only `changes`: the keys that change, e.g. "
           "{\"colors\": {\"page\": \"#2a2140\"}} or {\"background\": \"picture\", \"picture\": url, \"veil\": 40}.",
           {"look": {"type": "object", "properties": RECIPE_SCHEMA, "description": (
               "{name, base: light|dark, colors: {page, page2, page3, surface, bubble_ai, bubble_user, text, muted, "
               "accent, accent2, outline, effect} as #rrggbb, font, heading_font, size: small|normal|large, bold, "
               "bubble: {shape, outline, shadow, name_tag, wide}, frame, background, texture, effect, buttons, "
               "sound, picture, veil}: values from read_look_options")},
            "changes": {"type": "object", "properties": RECIPE_SCHEMA, "description": "Only what changes in their current look (same keys)"},
            "why": STR}, []),
    ]


HANDLERS = {"read_look_options": tool_read_look_options, "propose_chat_look": tool_propose_chat_look}
TURN_ENDING = {"propose_chat_look"}
