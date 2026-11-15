"""
Custom chat looks: a chat page dressed the way they describe it, or like a picture they show Bulba.

Bulba never writes code. It fills a *recipe*: colours, a font from the list below, the shape and outline of the
bubbles, name tags, a frame for the character's pictures, a background, a texture, a light effect and an
optional sound. Every value is checked here (colours as #rrggbb, everything else from fixed lists), and the app
turns the recipe into the page's styles: nothing can break the page or run anything.

A look belongs to a character (Character.theme["look"]) and shows as the chat style "✨ <its name>": the
character's style by default, or picked per chat in the pen menu like the four ready styles.
"""
import json
import re
from urllib.parse import quote

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Google Fonts the page may load: {key: (family, css fallback, weights, what it feels like)}
FONTS = {
    "gaegu": ("Gaegu", "cursive", "400;700", "chunky handwriting, cute, a diary or a cosy game"),
    "patrick_hand": ("Patrick Hand", "cursive", "400", "neat handwriting, friendly"),
    "caveat": ("Caveat", "cursive", "400;700", "quick pen handwriting, notes in a margin"),
    "shantell": ("Shantell Sans", "cursive", "400;700", "bouncy marker handwriting, playful"),
    "gochi": ("Gochi Hand", "cursive", "400", "marker on a whiteboard, casual"),
    "kalam": ("Kalam", "cursive", "400;700", "soft pencil handwriting"),
    "nunito": ("Nunito", "sans-serif", "400;700", "round and soft, clean"),
    "quicksand": ("Quicksand", "sans-serif", "400;700", "light, airy, rounded"),
    "fredoka": ("Fredoka", "sans-serif", "400;600", "chunky, bubbly, toy-like"),
    "dynapuff": ("DynaPuff", "cursive", "400;700", "puffy cartoon letters"),
    "comfortaa": ("Comfortaa", "sans-serif", "400;700", "geometric, rounded, calm"),
    "outfit": ("Outfit", "sans-serif", "400;700", "modern, neutral, sleek"),
    "josefin": ("Josefin Sans", "sans-serif", "400;700", "elegant, art deco"),
    "lora": ("Lora", "serif", "400;700", "a book: warm serif"),
    "garamond": ("EB Garamond", "serif", "400;700", "an old novel, literary"),
    "cormorant": ("Cormorant Garamond", "serif", "500;700", "delicate, aristocratic, romantic"),
    "playfair": ("Playfair Display", "serif", "400;700", "fashion magazine, dramatic"),
    "cinzel": ("Cinzel", "serif", "400;700", "carved capitals: epic fantasy, temples"),
    "crimson": ("Crimson Pro", "serif", "400;700", "a printed page, scholarly"),
    "space_mono": ("Space Mono", "monospace", "400;700", "terminal, sci-fi"),
    "plex_mono": ("IBM Plex Mono", "monospace", "400;700", "lab reports, technical"),
    "vt323": ("VT323", "monospace", "400", "an old CRT screen"),
    "press_start": ("Press Start 2P", "monospace", "400", "8-bit game (small and loud: names only)"),
    "silkscreen": ("Silkscreen", "monospace", "400", "pixel font"),
    "pirata": ("Pirata One", "serif", "400", "gothic blackletter, pirates, old seals"),
    "uncial": ("Uncial Antiqua", "serif", "400", "celtic manuscript, druids"),
    "system": ("", "system-ui, sans-serif", "", "the app's own font"),
}
SHAPES = ("rounded", "pill", "square", "wobbly", "cut", "cloud", "scroll")
OUTLINES = ("none", "thin", "thick", "double", "dashed", "sketch")
SHADOWS = ("none", "soft", "offset", "glow")
NAME_TAGS = ("none", "tab", "ribbon", "plain")
FRAMES = ("circle", "rounded", "square", "hexagon", "arch", "diamond", "polaroid", "sticker")
BACKGROUNDS = ("solid", "gradient", "blobs", "dots", "grid", "stripes", "checker")
TEXTURES = ("none", "grain", "paper", "scanlines", "halftone")
EFFECTS = ("none", "sparkles", "stars", "petals", "hearts", "bubbles", "snow", "fireflies", "embers", "leaves", "glitter")
BUTTONS = ("rounded", "pill", "square", "sticker")
SOUNDS = ("none", "soft", "chime", "bubble", "typewriter", "retro")
SIZES = ("small", "normal", "large")

COLOR_KEYS = ("page", "page2", "page3", "surface", "bubble_ai", "bubble_user", "text", "muted", "accent", "accent2",
              "outline", "effect")
DEFAULTS = {
    "light": {"page": "#e9e2f5", "page2": "#cbbbe9", "page3": "#f3e6f2", "surface": "#f4effb", "bubble_ai": "#f7f3fd",
              "bubble_user": "#ece4fa", "text": "#2b2440", "muted": "#6d6488", "accent": "#7c5cc4", "accent2": "#e58fb0",
              "outline": "#3a3150", "effect": "#ffffff"},
    "dark": {"page": "#14121f", "page2": "#2a2145", "page3": "#1d2a40", "surface": "#1e1b2e", "bubble_ai": "#262238",
             "bubble_user": "#2c2442", "text": "#ece8f6", "muted": "#a39cbc", "accent": "#a78bfa", "accent2": "#f0a6c8",
             "outline": "#5b4f86", "effect": "#ffe9a8"},
}


def clean(recipe):
    """A checked recipe (every value from the lists, colours as #rrggbb), or None."""
    if not isinstance(recipe, dict):
        return None
    pick = lambda value, options, default: value if value in options else default
    base = pick(recipe.get("base"), ("light", "dark"), "dark")
    given = recipe.get("colors") if isinstance(recipe.get("colors"), dict) else {}
    colors = {k: (given.get(k) if isinstance(given.get(k), str) and HEX.match(given.get(k)) else DEFAULTS[base][k]).lower()
              for k in COLOR_KEYS}
    bubble = recipe.get("bubble") if isinstance(recipe.get("bubble"), dict) else {}
    font = pick(recipe.get("font"), FONTS, "system")
    return {
        "name": re.sub(r"[^\w '&.,!?-]", "", str(recipe.get("name") or "Custom look"), flags=re.U).strip()[:40] or "Custom look",
        "base": base,
        "colors": colors,
        "font": font,
        "heading_font": pick(recipe.get("heading_font"), FONTS, font),
        "size": pick(recipe.get("size"), SIZES, "normal"),
        "bold": bool(recipe.get("bold")),
        "bubble": {"shape": pick(bubble.get("shape"), SHAPES, "rounded"),
                   "outline": pick(bubble.get("outline"), OUTLINES, "thin"),
                   "shadow": pick(bubble.get("shadow"), SHADOWS, "soft"),
                   "name_tag": pick(bubble.get("name_tag"), NAME_TAGS, "none"),
                   "wide": bool(bubble.get("wide"))},
        "frame": pick(recipe.get("frame"), FRAMES, "circle"),
        "background": pick(recipe.get("background"), BACKGROUNDS, "gradient"),
        "texture": pick(recipe.get("texture"), TEXTURES, "none"),
        "effect": pick(recipe.get("effect"), EFFECTS, "none"),
        "buttons": pick(recipe.get("buttons"), BUTTONS, "rounded"),
        "sound": pick(recipe.get("sound"), SOUNDS, "none"),
    }


def fonts_url(recipe):
    """The Google Fonts stylesheet for the look's fonts ("" for the app's own)."""
    recipe = clean(recipe)
    if not recipe:
        return ""
    families = []
    for key in dict.fromkeys((recipe["font"], recipe["heading_font"])):
        family, _, weights, _ = FONTS[key]
        if family:
            families.append(f"family={quote(family)}" + (f":wght@{weights}" if ";" in weights or weights != "400" else ""))
    return ("https://fonts.googleapis.com/css2?" + "&".join(families) + "&display=swap") if families else ""


def _font(key):
    family, fallback, _, _ = FONTS[key]
    return f"'{family}', {fallback}" if family else fallback


def _css_string(text):
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")[:60] + '"'


RADIUS = {"rounded": "16px", "pill": "26px", "square": "4px", "wobbly": "255px 18px 225px 18px / 18px 225px 18px 255px",
          "cut": "0", "cloud": "30px 30px 30px 10px", "scroll": "6px"}
FRAME = {"circle": "50%", "rounded": "28%", "square": "4px", "hexagon": "0", "arch": "50% 50% 10% 10%", "diamond": "0",
         "polaroid": "3px", "sticker": "50%"}
GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'>"
         "<feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/></filter>"
         "<rect width='100%' height='100%' filter='url(%23n)' opacity='.55'/></svg>\")")


def css(recipe, char_name="", user_name=""):
    """The page's styles for this look, all under body.skin-custom."""
    r = clean(recipe)
    if not r:
        return ""
    c, b = r["colors"], r["bubble"]
    S = "body.skin-custom"
    light = r["base"] == "light"
    out = [f"""{S} {{ --bg-primary: {c['page']}; --ui-primary: {c['surface']}; --ui-secondary: {c['bubble_ai']};
  --ui-tertiary: {c['bubble_user']}; --accent-1: {c['accent']}; --accent-2: {c['accent2']}; --text-primary: {c['text']};
  --text-secondary: {c['muted']}; --text-muted: {c['muted']}; --border-color: {c['outline']}40;
  --look-outline: {c['outline']}; --look-effect: {c['effect']};
  --look-char: {_css_string(char_name)}; --look-you: {_css_string(user_name or 'You')};
  color: {c['text']}; font-family: {_font(r['font'])}; font-size: {dict(small='15px', normal='16px', large='19px')[r['size']]}; }}"""]
    # The look's font through the chat (the page sets its own on every element): not code, not the top bar
    out.append(f"{S} .chat-container *:not(code):not(pre):not(.icon), {S} .character-panel *, {S} .tracker-panel * "
               f"{{ font-family: {_font(r['font'])}; }}")
    if r["bold"]:  # chunky handwriting reads best heavy
        out.append(f"{S} .message-content .message-text, {S} .input-field, {S} .character-details h3 {{ font-weight: 700; }}")
    pattern = {
        "solid": c["page"],
        "gradient": f"linear-gradient(160deg, {c['page']}, {c['page2']} 55%, {c['page3']})",
        "blobs": (f"radial-gradient(38% 30% at 10% 14%, {c['page2']} 0 97%, transparent 100%), "
                  f"radial-gradient(30% 36% at 92% 78%, {c['page2']} 0 97%, transparent 100%), "
                  f"radial-gradient(26% 22% at 70% 8%, {c['page3']} 0 96%, transparent 100%), "
                  f"radial-gradient(22% 26% at 18% 92%, {c['page3']} 0 96%, transparent 100%), {c['page']}"),
        "dots": f"radial-gradient({c['page2']} 2px, transparent 2.5px) 0 0 / 22px 22px, {c['page']}",
        "grid": (f"linear-gradient({c['page2']}66 1px, transparent 1px) 0 0 / 26px 26px, "
                 f"linear-gradient(90deg, {c['page2']}66 1px, transparent 1px) 0 0 / 26px 26px, {c['page']}"),
        "stripes": f"repeating-linear-gradient(135deg, {c['page']} 0 18px, {c['page2']} 18px 36px)",
        "checker": f"repeating-conic-gradient({c['page']} 0 25%, {c['page2']} 0 50%) 0 0 / 44px 44px",
    }[r["background"]]
    out.append(f"{S}, {S} .chat-container, {S} .messages-container, {S} .character-panel {{ background: {pattern}; background-attachment: fixed; }}")
    out.append(f"{S} .messages-container {{ background: transparent; }}")
    # Header, input, panels
    edge = f"2px solid {c['outline']}" if b["outline"] != "none" else f"1px solid {c['outline']}33"
    out.append(f"{S} .chat-header, {S} .input-container {{ background: {c['surface']}e6; border-color: {c['outline']}55; color: {c['text']}; }}")
    out.append(f"{S} .character-info-panel {{ background: {c['surface']}ee; border: {edge}; color: {c['text']}; }}")
    out.append(f"{S} .character-name {{ background: none; -webkit-text-fill-color: {c['accent']}; color: {c['accent']}; font-family: {_font(r['heading_font'])}; }}")
    out.append(f"{S} .character-details h3, {S} .message-name, {S} .na-title {{ font-family: {_font(r['heading_font'])}; }}")
    out.append(f"{S} .input-field {{ background: {c['bubble_ai']}; color: {c['text']}; border: {edge}; font-family: inherit; }}")
    out.append(f"{S} .input-field::placeholder {{ color: {c['muted']}; }}")
    # Bubbles
    border = {"none": "0", "thin": f"1.5px solid {c['outline']}", "thick": f"3px solid {c['outline']}",
              "double": f"4px double {c['outline']}", "dashed": f"2px dashed {c['outline']}",
              "sketch": f"2.5px solid {c['outline']}"}[b["outline"]]
    shadow = {"none": "none", "soft": "0 6px 18px rgba(0,0,0,.16)", "offset": f"4px 5px 0 {c['outline']}",
              "glow": f"0 0 20px {c['accent']}55"}[b["shadow"]]
    out.append(f"""{S} .message-content {{ background: {c['bubble_ai']}; color: {c['text']}; border: {border};
  border-radius: {RADIUS[b['shape']]}; box-shadow: {shadow}; {'max-width: 88%;' if b['wide'] else ''} }}
{S} .user .message-content {{ background: {c['bubble_user']}; }}
{S} .message-content .message-text {{ color: {c['text']}; }}
{S} .message-content em, {S} .message-content i {{ color: {c['muted']}; }}""")
    if b["shape"] == "cut":
        out.append(f"{S} .message-content {{ clip-path: polygon(14px 0, 100% 0, 100% calc(100% - 14px), calc(100% - 14px) 100%, 0 100%, 0 14px); }}")
    if b["shape"] == "scroll":
        out.append(f"{S} .message-content {{ border-left-width: 0; border-right-width: 0; border-top-width: 5px; border-bottom-width: 5px; }}")
    if b["outline"] == "sketch":  # a second, slightly offset hand-drawn line
        out.append(f"""{S} .message-content::after {{ content: ''; position: absolute; inset: -3px -2px -2px -3px; pointer-events: none;
  border: 1.5px solid {c['outline']}aa; border-radius: 225px 22px 255px 18px / 22px 255px 18px 225px; transform: rotate(-.4deg); }}""")
    if b["name_tag"] == "none":
        out.append(f"{S} .message-content::before {{ display: none; }}")
    else:
        tag = {"tab": f"top: -18px; left: 18px; padding: 3px 14px; border-radius: 10px 10px 4px 4px; background: {c['accent']}; color: #fff; border: 2px solid {c['outline']}; box-shadow: 2px 3px 0 {c['outline']};",
               "ribbon": f"top: -12px; left: -6px; padding: 2px 14px 2px 10px; background: {c['accent']}; color: #fff; clip-path: polygon(0 0, 100% 0, 92% 50%, 100% 100%, 0 100%);",
               "plain": f"top: -20px; left: 4px; padding: 0; background: none; color: {c['accent']};"}[b["name_tag"]]
        out.append(f"""{S} .message-content {{ margin-top: 20px; }}
{S} .message-content::before {{ display: block; position: absolute; width: auto; height: auto; border: 0; right: auto;
  font-family: {_font(r['heading_font'])}; font-size: .85rem; font-weight: 700; line-height: 1.4; white-space: nowrap; z-index: 2; {tag} }}
{S} .assistant .message-content::before {{ content: var(--look-char); }}
{S} .user .message-content::before {{ content: var(--look-you); left: auto; right: 18px; background: {c['accent2'] if b['name_tag'] != 'plain' else 'none'}; }}
{S} .note .message-content::before {{ display: none; }}""")
    # The character's pictures: avatars in the header and by the messages
    frame = FRAME[r["frame"]]
    pics = f"{S} .chat-header .character-avatar, {S} .message-avatar"
    out.append(f"{pics} {{ border-radius: {frame}; object-fit: cover; }}")
    if r["frame"] == "hexagon":
        out.append(f"{pics} {{ clip-path: polygon(25% 3%, 75% 3%, 100% 50%, 75% 97%, 25% 97%, 0 50%); }}")
    elif r["frame"] == "diamond":
        out.append(f"{pics} {{ clip-path: polygon(50% 0, 100% 50%, 50% 100%, 0 50%); }}")
    elif r["frame"] == "polaroid":
        out.append(f"{pics} {{ border: 3px solid #fff; border-bottom-width: 8px; box-shadow: 0 3px 8px rgba(0,0,0,.3); transform: rotate(-3deg); }}")
    elif r["frame"] == "sticker":
        out.append(f"{pics} {{ border: 3px solid #fff; box-shadow: 2px 3px 0 {c['outline']}; }}")
    else:
        out.append(f"{pics} {{ box-shadow: 0 0 0 2px {c['outline']}; }}")
    # Buttons
    br = {"rounded": "12px", "pill": "999px", "square": "4px", "sticker": "14px"}[r["buttons"]]
    btn = f"{S} .send-btn, {S} .tools-btn, {S} .header-btn"
    out.append(f"{btn} {{ border-radius: {br}; }}")
    out.append(f"{S} .send-btn, {S} .tools-btn {{ background: {c['accent']}; color: #fff; border: 2px solid {c['outline']}; }}")
    if r["buttons"] == "sticker":
        out.append(f"{btn} {{ border: 2px solid {c['outline']}; box-shadow: 2px 3px 0 {c['outline']}; }}")
        out.append(f"{S} .header-btn {{ background: {c['surface']}; color: {c['text']}; }}")
    else:
        out.append(f"{S} .header-btn {{ border-color: {c['outline']}66; color: {c['text']}; }}")
    # Readable speech colours on a light look
    if light:
        out.append(f"{S} {{ --speech-app: var(--dialogue-light, color-mix(in srgb, var(--dialogue-color, {c['accent']}) 45%, {c['text']})); }}")
    # Texture over everything, very faint
    texture = {"none": "", "grain": f"background-image: {GRAIN}; opacity: .18; mix-blend-mode: multiply;",
               "paper": f"background-image: {GRAIN}; opacity: .28; mix-blend-mode: soft-light;",
               "scanlines": "background: repeating-linear-gradient(0deg, rgba(0,0,0,.08) 0 1px, transparent 1px 3px);",
               "halftone": f"background: radial-gradient({c['outline']}22 1px, transparent 1.5px) 0 0 / 6px 6px;"}[r["texture"]]
    if texture:
        out.append(f"{S}::after {{ content: ''; position: fixed; inset: 0; pointer-events: none; z-index: 900; {texture} }}")
    out.append(f"{S} .look-fx {{ color: {c['effect']}; }}")
    return "\n".join(out)


def page_data(recipe):
    """What the page's script needs (the effect, the sound), as JSON."""
    r = clean(recipe)
    return {"effect": r["effect"], "sound": r["sound"], "name": r["name"]} if r else {}


def summary(recipe):
    """The look in words, for Bulba's proposal card."""
    r = clean(recipe)
    c = r["colors"]
    return [f"“{r['name']}”: a {r['base']} look",
            f"Colours: page {c['page']}, bubbles {c['bubble_ai']} / {c['bubble_user']}, text {c['text']}, accent {c['accent']}, outlines {c['outline']}",
            f"Font: {FONTS[r['font']][0] or 'the app’s'}" + (f", names in {FONTS[r['heading_font']][0]}" if r['heading_font'] != r['font'] else ""),
            f"Bubbles: {r['bubble']['shape']}, {r['bubble']['outline']} outline, {r['bubble']['shadow']} shadow"
            + (f", name tags ({r['bubble']['name_tag']})" if r['bubble']['name_tag'] != "none" else ""),
            f"Pictures: {r['frame']} frame · Background: {r['background']}" + (f" · Texture: {r['texture']}" if r['texture'] != "none" else ""),
            f"Effect: {r['effect']} · Sound: {r['sound']}"]


def guide():
    """For Bulba: the recipe's choices in a few lines."""
    fonts = "; ".join(f"{k} ({v[3]})" for k, v in FONTS.items())
    return (f"fonts: {fonts}. shapes: {', '.join(SHAPES)}. outlines: {', '.join(OUTLINES)}. shadows: {', '.join(SHADOWS)}. "
            f"name tags: {', '.join(NAME_TAGS)}. frames: {', '.join(FRAMES)}. backgrounds: {', '.join(BACKGROUNDS)}. "
            f"textures: {', '.join(TEXTURES)}. effects: {', '.join(EFFECTS)}. buttons: {', '.join(BUTTONS)}. "
            f"sounds: {', '.join(SOUNDS)}. sizes: {', '.join(SIZES)}. bold: true for chunky handwriting or a heavy look.")
