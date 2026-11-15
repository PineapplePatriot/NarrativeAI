from django import template

register = template.Library()

@register.filter
def startswith(text, starts):
    if isinstance(text, str):
        return text.startswith(starts)
    return False


@register.filter
def names(text, character):
    """Shows {{char}}/{{user}} in card text as the character's and the owner's names."""
    from mainapp.cards import fill_names, user_name
    return fill_names(text, character.name, user_name(character.author))



@register.filter
def tagline(text):
    """A card description as a one-line preview: drops label-only lines like "Identity:" and labels at the start."""
    import re
    text = re.sub(r"(?m)^\s*[\w'{} ]{1,40}:\s*$", "", text or "")
    text = re.sub(r"(?m)^\s*\[[^\]\n]{1,40}\]\s*$", "", text)  # "[Identity]" headings
    text = re.sub(r"^\s*(Identity|Description|Summary)\s*:\s*", "", text.strip(), flags=re.I)
    return " ".join(text.split())


@register.filter
def blurb(character):
    """The one-line preview of a character: the theme's tagline if it has one, else the description's start."""
    return (character.theme or {}).get("tagline") or tagline(names(character.description, character))


@register.filter
def split(text, sep=","):
    return str(text or "").split(sep)


@register.filter
def card_look(character):
    """How a character's card is dressed (the Characters page and the chat's quick view): its colour, its
    background, a second picture for hover, what kind of card it is and the route its relationships lean to."""
    import re
    from mainapp import card_sections, speaker_colors
    theme = character.theme or {}
    color = str(theme.get("dialogue_color") or "")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        cast = theme.get("speech_cast") or {}
        named = cast.get(character.name) if isinstance(cast, dict) else None
        color = speaker_colors.PALETTE[named][0] if named in speaker_colors.PALETTE else "#8b5cf6"
    data = card_sections.clean(character.sections) if character.sections else None
    kind, people, route = "character", [], "basic"
    if data:
        kind = data["kind"]
        people = [p["name"] for p in data["people"] if p["name"]]
        route = data["people"][0]["temperament"]["route"] if data["people"] else "basic"
    elif character.is_mult and character.second_name:
        kind, people = "ensemble", [character.name, character.second_name]
    badge = {"character": "", "ensemble": f"👥 {max(2, len(people))}", "simulation": "🌍 World"}[kind]
    icons = {"romance": "💗", "enemies": "⚔️", "enemies_to_lovers": "🗡️💗", "mentor": "📜", "rivals": "🏁", "family": "🏡"}
    return {
        "color": color,
        "bg": theme.get("bg") or "",
        "hover": character.photo_happy.url if character.photo_happy else "",
        "kind": kind, "badge": badge,
        "route": "" if route == "basic" else f"{icons.get(route, '')} {card_sections.ROUTES[route][0]}",
        "structured": bool(data),
    }
