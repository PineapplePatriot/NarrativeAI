"""
Speech colours. Each character picks one of two ways (kept on the character's theme, so every chat with them agrees):

- "app" (App colour): the model is never told about colours; the chat paints all speech in one colour from the
  palette below (theme["dialogue_color"]), over any colour the model wrote anyway.
- "story" (Story colours): the model colours speech itself with short named tags, <plum>"Words."</plum>, and the
  chat turns each name into its shade (a brighter one on dark chat styles, a deeper one on light ones). The cast
  list (who has which colour) goes into every request so the colours stay the same; side characters the model
  meets later take a free colour from the palette themselves.
- Either way, the user's own colour (theme["you_color"]) paints the speech in their messages, and in story mode the
  model and Write for me use it for {{user}}'s lines.
- Optional tone marks (theme["speech_tones"]): <plum:whisper>"..."</plum> also changes how the line looks.

New characters set up with Bulba start in story mode; older ones (no "speech" key) stay on the app colour.
"""
import re

# name → (shade on dark chat styles, shade on light ones: parchment, lab)
PALETTE = {
    "plum": ("#c792ea", "#7b3f9e"),
    "ember": ("#ff8a65", "#b4441f"),
    "saffron": ("#ffd166", "#8a6100"),
    "moss": ("#a5d6a7", "#2e6b34"),
    "lagoon": ("#4dd0e1", "#00707e"),
    "frost": ("#b3e5fc", "#2b6a8f"),
    "lilac": ("#d1b3ff", "#6a42b0"),
    "rosewood": ("#f48fb1", "#a3285a"),
    "honey": ("#e6b980", "#7d5326"),
    "fern": ("#7ed6a0", "#1f7a4a"),
    "cobalt": ("#82aaff", "#2848a8"),
    "garnet": ("#ff6b81", "#a0172f"),
    "peony": ("#ffb3d9", "#a33a76"),
    "jade": ("#64d8b4", "#127358"),
    "dusk": ("#b8a4d6", "#574379"),
    "pearl": ("#e8e6e3", "#4a4642"),
}
# tone → what it means (for the model); the chat styles each one (chat_page.css, .sc.t-<tone>)
TONES = {
    "whisper": "hushed, under the breath",
    "shout": "loud, raised",
    "drawl": "slow, stretched out",
    "tremble": "shaky, unsteady",
    "sharp": "clipped, cutting",
}
MODES = ("story", "app")
MAX_CAST = 24
DEFAULT_APP = "#e594f2"
TAG = re.compile(r"<(/?)([a-z]+)(?::([a-z]+))?>")


def name_of(value):
    """A palette name from a name or one of its shades ("" when it isn't one)."""
    value = str(value or "").strip().lower()
    if value in PALETTE:
        return value
    return next((n for n, shades in PALETTE.items() if value in shades), "")


def light_of(color):
    """The light-style shade of an app colour, when it's one of the palette's ("" otherwise: mixed in CSS)."""
    n = name_of(color)
    return PALETTE[n][1] if n else ""


def settings(character):
    """{"mode", "cast": {name: colour}, "you": colour or "", "tones": bool} for this character."""
    theme = (getattr(character, "theme", None) or {}) if character is not None else {}
    mode = theme.get("speech") if theme.get("speech") in MODES else ("story" if theme.get("dialogue_color") == "preset"
                                                                      else "app")
    return {"mode": mode, "cast": clean(theme.get("speech_cast")), "you": name_of(theme.get("you_color")),
            "tones": bool(theme.get("speech_tones"))}


def clean(raw):
    out = {}
    for name, color in (raw.items() if isinstance(raw, dict) else []):
        name = " ".join(str(name or "").split())[:60]
        color = name_of(color)
        if name and color and len(out) < MAX_CAST:
            out[name] = color
    return out


def first_free(cast, you=""):
    taken = set(cast.values()) | {you}
    return next((n for n in PALETTE if n not in taken), "plum")


def for_prompt(s, user_name="{{user}}"):
    """The story-mode instruction (empty in app mode: the model isn't told about colours)."""
    if s["mode"] != "story":
        return ""
    given = [f"{n}: {c}" for n, c in s["cast"].items()]
    if s["you"]:
        given.append(f"{user_name}: {s['you']}")
    free = [n for n in PALETTE if n not in set(s["cast"].values()) | {s["you"]}]
    lines = ["### Speech colours",
             "Wrap every spoken line in its speaker's colour tag; the tag's name is the colour: "
             "<plum>\"Spoken words.\"</plum>. Only the quoted words go inside: never narration, actions or who said "
             "it. One line, one tag, closed right after the closing quote.",
             ("Colours already given (keep them exactly, every time): " + "; ".join(given) + ".") if given else "",
             "Anyone else who speaks takes a colour nobody has yet, from: " + ", ".join(free or PALETTE)
             + "; and keeps it for the rest of the story.",
             "Use only these names as tags: no hex codes, no <font> or <span> tags for speech."]
    if s["tones"]:
        lines.append("Where the delivery matters, add a tone after the colour: <plum:whisper>\"...\"</plum> "
                     "(closing tag without it). Tones: " + "; ".join(f"{t} ({m})" for t, m in TONES.items())
                     + ". Most lines need none.")
    return "\n".join(l for l in lines if l)


def for_writing_user(s, user_name="{{user}}"):
    """What Write for me (and the director) hear about the user's own colour in story mode."""
    if s["mode"] != "story" or not s["you"]:
        return ""
    return (f"{user_name}'s spoken lines are coloured with <{s['you']}>\"...\"</{s['you']}>; "
            "anyone else who speaks keeps their own colour tag.")


def tag_greeting(text, color):
    """A greeting written before colours were chosen: its untagged spoken lines take the character's colour."""
    if not text or not color or TAG.search(text) and any(m.group(2) in PALETTE for m in TAG.finditer(text)):
        return text
    parts = re.split(r"(<[^>]*>|`+[^`]*`+)", text)
    for i in range(0, len(parts), 2):
        parts[i] = re.sub(r"\"([^\"\n]+)\"", lambda m: f"<{color}>\"{m.group(1)}\"</{color}>", parts[i])
        parts[i] = re.sub(r"“([^”\n]+)”", lambda m: f"<{color}>“{m.group(1)}”</{color}>", parts[i])
    return "".join(parts)


def strip_tags(text):
    """The text without colour tags (for reading aloud, copying and background jobs that quote it)."""
    return TAG.sub(lambda m: "" if m.group(2) in PALETTE else m.group(0), text or "")


def css():
    """The palette's shades for the chat page (dark styles, then the light ones: body.light-style, parchment and lab)."""
    dark = "".join(f".sc-{n}{{--sc:{d}}}body.you-{n}{{--you:{d}}}" for n, (d, _) in PALETTE.items())
    light = "".join(f"body.light-style .sc-{n}{{--sc:{l}}}body.light-style.you-{n}{{--you:{l}}}"
                    for n, (_, l) in PALETTE.items())
    return dark + light


def page_data():
    return {"palette": {n: list(s) for n, s in PALETTE.items()}, "tones": list(TONES)}
