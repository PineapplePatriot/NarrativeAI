"""
In-story objects the AI designs itself (scene banners, letters, screens, rumour boards...): the preset's
"In-story objects" modules ask for them as ```html fenced blocks in the reply.

- The chat draws each block in a sealed frame (chat_page.js, renderChatMessage): styles and small scripts work,
  but the frame can't reach the page, the account or the network (sandbox without same-origin, plus a strict
  content policy).
- The AI rereads only the last couple of objects in full (to keep their look consistent); older ones, and
  everything background jobs read (summaries, trackers, ideas, voices), get a one-line label instead.
- An AI-designed kind switches off the app-drawn story extra for the same thing (REPLACES), never both.
"""
import html
import re

# A closed ```html block (``` html, ```HTML... too)
FENCE = re.compile(r"```[ \t]*html[ \t]*\r?\n(.*?)\r?\n[ \t]*```", re.S | re.I)
TAG = re.compile(r"<[^>]+>")
DROP = re.compile(r"<(script|style|head)\b.*?</\1\s*>", re.S | re.I)
TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
LABEL = re.compile(r"""data-label\s*=\s*["']([^"']+)["']""", re.I)

# Module key → the app-drawn story extras it takes over while it's on (mainapp/extras.py KINDS)
REPLACES = {
    "html_letters": {"documents"},
    "html_screens": {"messages"},
    "html_rumours": {"news"},
    "html_objects": {"documents", "messages", "news"},
}
KEEP_FULL = 2  # the AI's most recent replies whose objects it rereads in full
CUSTOM_MARK = "The object they asked for:"


def has_objects(text):
    return bool(FENCE.search(text or ""))


def label(code):
    """A short description of one object: its data-label or <title>, else the start of its visible text."""
    for pattern in (LABEL, TITLE):
        m = pattern.search(code)
        if m and m.group(1).strip():
            return " ".join(html.unescape(m.group(1)).split())[:120]
    words = " ".join(html.unescape(TAG.sub(" ", DROP.sub(" ", code))).split())
    return (words[:117] + "...") if len(words) > 120 else words or "a designed object"


def shrink(text):
    """The reply with each object as a one-line label (what the AI and background jobs read for older replies)."""
    return FENCE.sub(lambda m: f"[Shown to the reader as a designed object: {label(m.group(1))}]", text or "")


def strip(text):
    """The reply without its objects (read aloud)."""
    return re.sub(r"\n{3,}", "\n\n", FENCE.sub("", text or "")).strip()


def replaced_kinds(preset):
    """App-drawn story extras that this preset's AI-designed objects take over."""
    from mainapp import experiences
    on = {m["key"] for m in experiences.module_states(preset) if m["on"]}
    return set().union(*[REPLACES.get(k, set()) for k in on])


def custom_text(block_content):
    """What they described for "My own object" (kept at the end of its block)."""
    head, _, tail = (block_content or "").partition(CUSTOM_MARK)
    return tail.strip()


def with_custom(block_content, description):
    head = (block_content or "").partition(CUSTOM_MARK)[0].rstrip()
    description = " ".join(str(description or "").split())[:600]
    return f"{head}\n{CUSTOM_MARK} {description}" if description else head


# --- Keeping each kind of object's look ---------------------------------------------------------------
# The first design of each kind in a chat (a scene banner, a letter...) is remembered and shown to the AI as
# the one to reuse, so the look doesn't change from reply to reply. Editing an object in a message replaces it.
MAX_DESIGNS = 6
MAX_DESIGN_CHARS = 4000


def kind_of(code):
    """The kind of object, from its data-label's first part ("Scene banner: the docks" → "scene banner")."""
    return label(code).split(":")[0].strip().lower()[:40] or "object"


def remember(designs, text, replace=False):
    """Note the designs in `text` (in place): new kinds always; known kinds only with replace (their edit)."""
    changed = False
    for m in FENCE.finditer(text or ""):
        code = m.group(1).strip()
        kind = kind_of(code)
        if (kind not in designs and len(designs) < MAX_DESIGNS) or (replace and kind in designs and designs[kind] != code[:MAX_DESIGN_CHARS]):
            designs[kind] = code[:MAX_DESIGN_CHARS]
            changed = True
    return changed


def designs_for_prompt(designs):
    if not designs:
        return ""
    parts = [f"- {kind}:\n```html\n{code}\n```" for kind, code in designs.items()]
    return ("### Designed objects already used in this story\nWhen you show one of these kinds again, reuse its design "
            "exactly (layout, colours, fonts, frame, data-label wording) and change only the contents. A new kind "
            "gets its own design, kept the same way from then on.\n" + "\n".join(parts))
