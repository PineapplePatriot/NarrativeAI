"""
🧵 World texture: a small built-in library of concrete, varied specifics about the things stories keep touching
(luxury, clothes, food, science, politics, genre tropes), so replies reach for something real and different instead
of the same stock detail. It works like a lorebook every chat has: an entry wakes when the recent messages mention
it, and the reply request gets a short note with what it's really like, the tired version to avoid, and three
specifics picked at random from its pool (a different three each time, so nothing becomes a tic).

- At most MOST entries per reply. One specific keyword wakes an entry; short, common ones ("tea", "heat",
  "blood") need a second keyword from the same entry, so a hot day doesn't wake the omegaverse.
- Entries marked mature only wake when mature content is on.
- The story's own card and lorebook always win (the note says so).
- Free: no AI call. Bulba can read it too (look_up_texture), for cards, personas and lore.

The entries are in data/texture/library.json; edit or add them there.
"""
import json
import random
import re
from functools import lru_cache
from pathlib import Path

FILE = Path(__file__).resolve().parent / "data" / "texture" / "library.json"
MOST = 2           # entries per reply
SPECIFICS = 3      # specifics shown from an entry's pool
STRONG = 6         # a keyword this long (or longer) wakes an entry on its own


@lru_cache(maxsize=1)
def entries():
    try:
        return json.loads(FILE.read_text(encoding="utf-8")).get("entries") or []
    except (OSError, ValueError):
        return []


def _hits(text, keys):
    found = set()
    for k in keys:
        k = k.lower()
        if re.search(r"(?<![^\W_])" + re.escape(k.strip()), text) if k.strip() else False:
            found.add(k.strip())
    return found


def woken(text, mature=False, most=MOST):
    """The entries `text` (the recent messages) wakes, the clearest first."""
    text = (text or "").lower()
    scored = []
    for e in entries():
        if e.get("mature") and not mature:
            continue
        hits = _hits(text, e.get("keys") or [])
        if any(len(h) >= STRONG for h in hits) or len(hits) >= 2:
            scored.append((len(hits), sum(len(h) for h in hits), e))
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [e for _, _, e in scored[:most]]


def note(found, rng=None):
    """The reply request's note for the woken entries ("" for none)."""
    if not found:
        return ""
    rng = rng or random
    parts = []
    for e in found:
        pool = list(e.get("pool") or [])
        picked = rng.sample(pool, min(SPECIFICS, len(pool)))
        parts.append(f"{e['title']}: {e['gist']} The tired version: {e['avoid']}. If it fits, draw on one specific "
                     f"like these (or something as concrete; never list them): " + "; ".join(picked) + ".")
    return ("[World texture, for concrete and varied detail. The story's card and lorebook come first; use this only "
            "where it fits and doesn't contradict them.\n" + "\n".join(parts) + "]")


def for_reply(user, recent_texts):
    """The note for a reply, from the last few messages (and the one being answered)."""
    from mainapp import mature
    try:
        adult = mature.wanted(user)
    except Exception:
        adult = False
    return note(woken("\n".join(t for t in recent_texts if t), mature=adult))


def look_up(query, mature=False):
    """Bulba's look-up: the entries for words like "regency dress" or "vampires", whole (every specific)."""
    found = woken(query, mature=mature, most=3)
    if not found:  # by topic or title
        q = (query or "").lower()
        found = [e for e in entries() if (q in e["topic"] or q in e["title"].lower()) and (mature or not e.get("mature"))][:3]
    return [{"title": e["title"], "gist": e["gist"], "avoid": e["avoid"], "specifics": e["pool"]} for e in found]
