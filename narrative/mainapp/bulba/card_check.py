"""
A look at a card before it's shown (propose_character): the two things short cards kept getting wrong.

- No appearance: the guide says a card always has a short plain Appearance part (the story and the pictures rely
  on it), but compact cards dropped it first. A card without one goes back to Bulba.
- Types instead of a person: stock epithets ("a predator's smile", "the cold genius", "a viper in silk") are
  labels the model already has; they flatten anyone into the same performance. Found ones go back to Bulba to
  rewrite as plain behaviour.

It returns the problem in words Bulba acts on, once: a card sent back already (the conversation says so) goes
through on the next try with whatever is left, so it never loops.
"""
import re

MARK = "CARD CHECK"
APPEARANCE = re.compile(r"(^|\n)\s*[#\[*]*\s*(appearance|looks?|physical description|зовнішність|вигляд)\b", re.I)
EPITHETS = [
    r"predator'?s (smile|grin|gaze)", r"predatory (smile|grin|gaze|eyes)", r"cold genius", r"cunning (banker|mastermind|schemer)",
    r"silk[- ]smooth", r"a viper in", r"velvet[- ]wrapped", r"smiles? that (doesn'?t|didn'?t|never) reach(es)? (his|her|their) eyes",
    r"dangerous glint", r"mysterious aura", r"aura of (danger|mystery|power|menace)", r"commanding presence", r"piercing (gaze|eyes|stare)",
    r"cold and calculating", r"heart of gold", r"brooding", r"enigmatic", r"devilish(ly)? (charm|smile|grin)", r"wolf in sheep'?s clothing",
    r"iron will", r"steely (gaze|eyes|resolve)", r"a storm (behind|in) (his|her|their) eyes", r"walking contradiction",
    r"tsundere", r"yandere", r"bad boy", r"femme fatale", r"lone wolf",
]
EPITHET = re.compile(r"\b(" + "|".join(EPITHETS) + r")\b", re.I)


MIN_WORDS = 40  # a real card; a one-line description they dictated goes through as it is


def problems(description, sections=None):
    found = []
    if len(str(description or "").split()) < MIN_WORDS:
        return found
    if sections:  # written as sections: each person needs an Appearance (a simulation's recurring people too)
        missing = [p["name"] or "someone" for p in sections.get("people", [])
                   if not ((p.get("sections") or {}).get("appearance") or {}).get("text")]
        if missing:
            found.append(f"No Appearance section for: {', '.join(missing)}. Every person gets one, whatever the "
                         "card's size: a short plain paragraph (build, face, hair, eyes, what they usually wear, how "
                         "they move); canon characters from canon. Trim Background before you trim Appearance.")
    elif not APPEARANCE.search(description or ""):
        found.append("It has no Appearance part. Every card has one, whatever its size: a short plain paragraph "
                     "(build, face, hair, eyes, what they usually wear, how they move); canon characters from canon. "
                     "In a compact card, trim Background before you trim Appearance.")
    labels = sorted({m.group(0).lower() for m in EPITHET.finditer(description or "")})
    if labels:
        found.append("It leans on stock labels the model already has: " + ", ".join(f"“{l}”" for l in labels)
                     + ". Replace each with what this person actually does (when, to whom, at what cost), the way the "
                       "guide's 'A person, not a type' says. Keep the card's length.")
    return found


def sent_back_before(session, name):
    """Has this card (by name) been sent back already in this conversation?"""
    needle = f"{MARK}: {name}"
    for m in session.messages or []:
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, str) and needle in content:
            return True
    return False


def review(session, name, description, sections=None):
    """None when it can be shown; else the error for Bulba to fix first."""
    found = problems(description, sections)
    if not found or sent_back_before(session, name):
        return None
    return (f"{MARK}: {name}. Not shown yet; fix this and call propose_character again with the whole card:\n- "
            + "\n- ".join(found))
