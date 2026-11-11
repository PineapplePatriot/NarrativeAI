"""
Speech colours by character: each character's spoken lines keep one colour, set by the user or learned from the
first line the AI coloured for them. The AI tags coloured lines with the speaker
(<font color="#hex" data-who="Name">); the chat redraws each tagged line in that name's colour (chat_page.js), so
a colour set here wins over whatever hex the AI wrote, in old messages too.
Kept on the character (theme["speaker_colors"]), so every chat with them agrees.
"""
import re

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
TAG = re.compile(r"<font\b[^>]*>", re.I)
COLOR_ATTR, WHO_ATTR = re.compile(r"""color\s*=\s*["']?(#[0-9a-fA-F]{6})""", re.I), re.compile(r"""data-who\s*=\s*["']([^"']{1,60})["']""", re.I)
MAX = 24


def of(character):
    raw = (getattr(character, "theme", None) or {}).get("speaker_colors") or {}
    return {str(k)[:60]: v for k, v in raw.items() if isinstance(v, str) and HEX.match(v)} if isinstance(raw, dict) else {}


def clean(raw):
    out = {}
    for name, color in (raw.items() if isinstance(raw, dict) else []):
        name = " ".join(str(name or "").split())[:60]
        if name and isinstance(color, str) and HEX.match(color) and len(out) < MAX:
            out[name] = color
    return out


def learn(character, text):
    """Names the AI coloured for the first time get that colour kept (saved on the character). Returns the map."""
    colors = of(character)
    changed = False
    for tag in TAG.findall(text or ""):
        c, w = COLOR_ATTR.search(tag), WHO_ATTR.search(tag)
        if c and w:
            name = " ".join(w.group(1).split())[:60]
            if name and name not in colors and len(colors) < MAX:
                colors[name] = c.group(1)
                changed = True
    if changed:
        character.theme = {**(character.theme or {}), "speaker_colors": colors}
        character.save(update_fields=["theme"])
    return colors


def for_prompt(colors):
    if not colors:
        return ""
    return ("Speech colours (keep them exactly; tag each coloured line with its speaker, "
            "<font color=\"#hex\" data-who=\"Name\">): " + "; ".join(f"{n} {c}" for n, c in colors.items())
            + ". Anyone new gets a new colour that isn't on this list, kept the same from then on.")
