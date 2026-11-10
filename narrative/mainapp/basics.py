"""
The preset's "Basics" block: plain, fixed lines for how the story is written (point of view, tense, speech
format, inner thoughts, pacing...). Both ways in write it the same way: the Quick setup form and Bulba's basics
form (the full setup). Each answer owns its own line; changing one answer replaces only that line, so what the
other form (or Bulba) set stays.

The questions and their wording live in bulba/agent.py (BASICS).
"""
import json
from functools import lru_cache
from pathlib import Path

from mainapp import experiences, presets

FORM_FILE = Path(__file__).resolve().parent / "data" / "bulba" / "basics_form.json"

BLOCK = "Basics"
# Answers written as Basics lines (the rest go elsewhere: length → Reply length, control → Your character,
# modules and module voices → their blocks, mature → the 18+ rule, language → the profile)
LINE_KEYS = ("pov", "tense", "format", "interior", "colors", "pacing", "initiative", "invention", "genres",
             "voice", "author", "keep_out")
GENRE_HEAD = "Lean the story toward "
AUTHOR_HEAD = "Write in the style of "
KEEP_OUT_HEAD = "Keep out: "


def _basics():
    from mainapp.bulba.agent import BASICS
    return BASICS


def line_for(key, value):
    """The Basics line for one answer, or "" (no preference, or an answer that isn't a line)."""
    options = _basics()[key][1]
    if key == "genres":
        picked = [g for g in (value or []) if isinstance(g, str) and g in options][:6]
        return (GENRE_HEAD + "; ".join(options[g] for g in picked) + ".") if picked else ""
    value = str(value or "").strip()[:300]
    if not value:
        return ""
    if key == "author":
        return f"{AUTHOR_HEAD}{value}: their diction, rhythm and conventions, not their plots."
    if key == "keep_out":
        return f"{KEEP_OUT_HEAD}{value}."
    if key == "voice" and f"voice_{value}" in experiences.catalog()["modules"]:
        return ""  # a narration-voice module, switched on as a block
    return (options or {}).get(value, "")


def _owner(line):
    """Which answer a line belongs to (None: a line someone wrote themselves)."""
    for key in LINE_KEYS:
        if key == "genres" and line.startswith(GENRE_HEAD):
            return key
        if key == "author" and line.startswith(AUTHOR_HEAD):
            return key
        if key == "keep_out" and line.startswith(KEEP_OUT_HEAD):
            return key
        if line in {t for t in (_basics()[key][1] or {}).values() if t} and key not in ("genres",):
            return key
    return None


def _block(preset):
    return next((b for b in preset["blocks"] if b.get("name") == BLOCK and b.get("kind") == "prompt"), None)


def read(preset):
    """The answers the Basics block holds now: {"pov": "third", "genres": ["romance"], "author": "Le Guin"...}."""
    block = _block(preset)
    out = {}
    for line in ((block or {}).get("content") or "").splitlines():
        line = line.strip()
        key = _owner(line)
        if key == "genres":
            options = _basics()["genres"][1]
            parts = line[len(GENRE_HEAD):].rstrip(".").split("; ")
            out[key] = [g for g, text in options.items() if text in parts]
        elif key == "author":
            out[key] = line[len(AUTHOR_HEAD):].split(": their diction")[0]
        elif key == "keep_out":
            out[key] = line[len(KEEP_OUT_HEAD):].rstrip(".")
        elif key:
            out[key] = next(v for v, t in _basics()[key][1].items() if t == line)
    return out


def set_answers(preset, answers):
    """The preset with these answers' lines replaced (an empty answer removes its line). Lines for answers not
    given, and lines someone wrote themselves, stay. Changes `preset` in place and returns it."""
    answers = {k: v for k, v in answers.items() if k in LINE_KEYS}
    if not answers:
        return preset
    block = _block(preset)
    lines = [l for l in ((block or {}).get("content") or "").splitlines() if l.strip()]
    kept = [l for l in lines if _owner(l.strip()) not in answers]
    new = [line_for(k, answers[k]) for k in LINE_KEYS if k in answers]
    content = "\n".join(kept + [l for l in new if l])
    if block is None:
        if not content:
            return preset
        block = presets.normalize_block({"name": BLOCK, "kind": "prompt", "content": ""})
        at = next((i for i, b in enumerate(preset["blocks"]) if b.get("marker") == "chat_history"),
                  len(preset["blocks"]))
        preset["blocks"].insert(at, block)
    block["content"] = content
    block["enabled"] = bool(content)
    return preset


@lru_cache(maxsize=1)
def form():
    """The questions both forms ask (Bulba's basics form and Quick setup), with the story modules taken from the
    module catalog (the ones that aren't on anyway, voices apart: those are their own question)."""
    spec = json.loads(FORM_FILE.read_text(encoding="utf-8"))
    mods = [(k, m) for k, m in experiences.catalog()["modules"].items()
            if not m["default"] and not k.startswith("voice_")]
    for f in spec:
        if f.get("key") == "modules":
            f["multi"] = [[k, m["title"]] for k, m in mods if k not in experiences.ADULT]
            f["adult"] = [[k, m["title"]] for k, m in mods if k in experiences.ADULT]
    return spec


def question(key):
    return next((f for f in form() if f.get("key") == key), None)
