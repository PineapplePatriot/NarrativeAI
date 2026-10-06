"""Tested blocks Bulba can borrow from the community presets we ship (word for word, before writing its own)."""
import json
import re
from functools import lru_cache
from pathlib import Path

from mainapp import starters

# The presets Anya provided. Later files only add blocks the earlier ones don't have.
SOURCES = ["mimo-frankenstein", "gemini-frankenstein", "mimo-frankenstein-pico"]
# Original candidate wording from the research cookbook (docs/research/): untested, so it comes after the presets
CANDIDATES = Path(__file__).resolve().parent.parent / "data" / "bulba" / "candidates.json"
CANDIDATE_SOURCE = "Research cookbook (untested candidate)"
PLACEHOLDER = re.compile(r"\[[a-z][^\]]*\]")
NOTE = re.compile(r"\{\{//(.*?)\}\}", re.S)


def _summary(content):
    """The author's own note at the top of a block ({{// ...}}), or its first line."""
    m = NOTE.search(content)
    text = m.group(1) if m else next((l for l in content.splitlines() if l.strip()), "")
    return " ".join(text.split())[:300]


@lru_cache(maxsize=1)
def blocks():
    found = {}
    for sid in SOURCES:
        starter = starters.get(sid)
        if not starter:
            continue
        for b in starter["preset"]["blocks"]:
            name, content = b.get("name", "").strip(), b.get("content") or ""
            if b.get("kind", "prompt") != "prompt" or b.get("marker") or len(content.strip()) < 80:
                continue  # slots, dividers ("=Pick one ..."), empty blocks
            if "README" in name or "====" in name or name in found:
                continue
            found[name] = {"name": name, "source": starter["title"], "content": content,
                           "summary": _summary(content), "on_in_source": bool(b.get("enabled"))}
    for c in json.loads(CANDIDATES.read_text(encoding="utf-8")):
        for form, label in (("natural", "story wording"), ("structured", "rule wording")):
            name = f"Cookbook: {c['problem']} ({label})"
            found[name] = {"name": name, "source": CANDIDATE_SOURCE, "content": c[form],
                           "summary": f"{c['problem']}. {c['notes']}", "on_in_source": False}
    return found


def needs_filling(block):
    """Candidate wording with [placeholders] can't go in word for word."""
    return bool(PLACEHOLDER.search(block["content"]))


STOP = {"the", "and", "for", "with", "that", "this", "too", "much", "what", "say", "says", "said", "keeps",
        "words", "it's", "its", "they", "them", "make", "more", "less", "about", "replies", "reply"}


def _stem(word):
    """Crude: 'repeats', 'repeating', 'repeated' all become 'repeat'."""
    for end in ("ing", "ed", "es", "s"):
        if word.endswith(end) and len(word) - len(end) >= 4:
            word = word[: -len(end)]
            break
    return word[:6] if len(word) > 7 else word  # 'therapist' finds 'therapy' too


def search(query, limit=12):
    """Blocks whose name or text matches the query's words, best first. An empty query lists every name."""
    lib = blocks()
    words = {_stem(w) for w in re.findall(r"\w+", (query or "").lower()) if len(w) > 2 and w not in STOP}
    if not words:
        return [{"name": b["name"], "summary": b["summary"][:120]} for b in lib.values()]
    scored = []
    for b in lib.values():
        name, note, body = b["name"].lower(), b["summary"].lower(), b["content"].lower()
        score = sum(4 * (w in name) + 2 * (w in note) + (w in body) for w in words)
        if b["source"] == CANDIDATE_SOURCE:
            score *= 0.8  # tested preset blocks first
        if score:
            scored.append((score, b))
    scored.sort(key=lambda s: -s[0])
    return [{"name": b["name"], "from": b["source"], "summary": b["summary"], "size": len(b["content"])}
            for _, b in scored[:limit]]


def get(name):
    return blocks().get(str(name or "").strip())


def tool_find_practice(session, args):
    return {"blocks": search(args.get("query", ""))}, []


def tool_read_practice(session, args):
    b = get(args.get("block"))
    if b is None:
        return {"error": "No such block in the library; use find_practice for the exact name."}, []
    result = {"block": b["name"], "from": b["source"], "content": b["content"][:12000]}
    if b["source"] == CANDIDATE_SOURCE:
        result["note"] = ("Untested wording from research; the story and rule wordings are alternatives, never both. "
                          + ("Fill in the [bracketed] parts and add it as your own text." if needs_filling(b) else ""))
    return result, []


def tool_defs(fn, STR):
    return [
        fn("find_practice", "Search the tested blocks of the community presets (Realistic Frankenstein) for one "
           "that already does what you need: anti-echo, dialogue, pacing, NPC behaviour, dice and stats, "
           "inventories, relationship meters, in-story graphics, coloured speech... Empty query lists them all. "
           "Check here before writing an instruction yourself.", {"query": STR}),
        fn("read_practice", "The full text of one library block (exact name from find_practice).",
           {"block": STR}, ["block"]),
    ]


HANDLERS = {"find_practice": tool_find_practice, "read_practice": tool_read_practice}
