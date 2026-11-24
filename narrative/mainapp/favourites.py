"""
⭐ Voice examples from starred replies: when someone stars a reply, its spoken lines are kept on the character
(theme["voice_lines"], up to MOST_KEPT), and every reply request shows the model a few of them as "how they sound
at their best". Models copy an example far better than they follow a description of a voice. Only lines of
speech are kept, never the narration, so no place, object or event from that scene carries into another.
"""
import random
import re

MOST_KEPT = 24      # lines kept per character
SHOWN = 4           # lines shown per reply
LONGEST = 220       # characters per line

QUOTED = re.compile(r"[\"“«„]([^\"”»“\n]{8,400})[\"”»“]")


def lines_of(text):
    """The spoken lines of a reply (what's in quotes), trimmed."""
    out = []
    for m in QUOTED.finditer(re.sub(r"</?[a-z]+(?::[a-z]+)?>", "", text or "")):
        line = " ".join(m.group(1).split())
        if len(line) > LONGEST:
            line = line[:LONGEST].rsplit(" ", 1)[0] + "…"
        out.append(line)
    return out


def remember(character, text, starred=True):
    """Keep (or, unstarred, drop) a reply's spoken lines on the character. Saves the character."""
    theme = dict(character.theme or {})
    kept = [x for x in theme.get("voice_lines") or [] if isinstance(x, str)]
    lines = lines_of(text)
    if starred:
        kept = (kept + [line for line in lines if line not in kept])[-MOST_KEPT:]
    else:
        kept = [x for x in kept if x not in lines]
    theme["voice_lines"] = kept
    character.theme = theme
    character.save(update_fields=["theme"])


def note(character, rng=None):
    """The request's note: a few of their starred lines ("" when there are none)."""
    kept = [x for x in (character.theme or {}).get("voice_lines") or [] if isinstance(x, str)]
    if not kept:
        return ""
    picked = (rng or random).sample(kept, min(SHOWN, len(kept)))
    return (f"[How {character.name} sounds at their best: lines from replies the person starred. Take the voice "
            "(rhythm, word choice, how they dodge or commit), never the words or what they were about:\n"
            + "\n".join(f"— \"{line}\"" for line in picked) + "]")


def insert_before_chat(messages, text):
    """`text` as a system message after the leading system messages (before the chat)."""
    if not text:
        return messages
    at = next((i for i, m in enumerate(messages) if m.get("role") != "system"), len(messages))
    return messages[:at] + [{"role": "system", "content": text}] + messages[at:]
