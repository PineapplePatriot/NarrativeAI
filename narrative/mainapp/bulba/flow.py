"""
🥔 The order Bulba sets a story up in, and the reminders about proposals still waiting for Apply. One place, used by
every Bulba (the setup, Bulba in a chat, Bulba on the Screen), so they all agree.
"""

# 📚 What kind of lorebook: asked before writing one (and the most entries each may have)
LORE_TYPES = {
    "essentials": ("Essentials", 8, "the few things the story can't do without: the main places, groups and terms, "
                   "an entry or two of what's going on; short entries"),
    "exposition": ("Exposition", 25, "the world explained: places, factions, customs, history and the people "
                   "around the character, each in a solid paragraph"),
    "loredump": ("Loredump", 60, "long, wiki-like coverage of the world: every notable place, person, faction, "
                 "event and term, for someone who wants it all"),
}
# 👋 What kind of first message: asked before writing one
GREETING_TYPES = {
    "short": ("Short", "two to four lines: straight into the moment, a line of speech, room to answer"),
    "descriptive": ("Descriptive", "the scene set properly: place, light, sound, what the character is doing, then "
                    "them speaking"),
    "in_motion": ("In the middle of things", "already happening: a chase, an argument, a job going wrong"),
    "dialogue": ("Dialogue first", "they speak first, almost no narration"),
    "letter": ("A note or message", "it opens with a letter, a text, a note left behind"),
}


def _types_line(types, with_size=False):
    return "; ".join(f"{v[0]} ({v[-1]}{', up to ' + str(v[1]) + ' entries' if with_size else ''})" for v in types.values())


STEPS = [
    ("character", "The character: the card itself, and any corrections to it (propose_character, then "
                  "propose_card_edit for each correction)"),
    ("persona", "Who the user is in this story, and corrections (propose_persona: their usual persona, one just for "
                "this story, or just for one chat)"),
    ("scenario", "Where the story starts, written for this character AND this persona (propose_card_edit: scenario)"),
    ("greeting", "The first message, built on that scenario (propose_card_edit: initial_message / greetings). First "
                 "ask which kind with offer_choices: " + _types_line(GREETING_TYPES)),
    ("lorebook", "The world: a lorebook for this story (write one, check the one that came with the card, or none). "
                 "Before writing one, ask which kind with offer_choices: " + _types_line(LORE_TYPES, True)
                 + ". Then propose_lorebook with that type"),
    ("images", "Pictures: the character's moods (and the persona's), from a picture or a description"),
    ("extras", "Story extras and trackers (letters, phone screens, milestones, meters…)"),
    ("visuals", "How the chat looks: a chat style or a custom look, backgrounds, music"),
]

ORDER = (
    "## Setting up a story: always in this order\n"
    "When they start a new character (made with you, brought from a site, or uploaded), go through these steps one at "
    "a time, each offered with offer_choices, and only move on when the step is done or they skip it:\n"
    + "\n".join(f"{i}. {text}" for i, (_, text) in enumerate(STEPS, 1)) + "\n"
    "- Corrections belong to their step: a change to the card is still step 1, a change to the persona still step 2.\n"
    "- NOTHING IS PERMANENT: a persona or a lorebook they already have is never assumed to fit a new story. At steps "
    "2 and 5, ask: keep the current one, or make one for this story? (Never skip a step because something exists.)\n"
    "- The scenario and the first message come after the persona, because they depend on who the user is here.\n"
    "- They can jump ahead or skip; come back to what was skipped at the end, in one line.")

AFTER_NEW_CARD = (
    "NEXT, after this new character: ask with offer_choices what to do with the card itself (use it as it is, or "
    "change it: propose the edits), then go on with the rest of the order, one step at a time: "
    + " ".join(f"{i}) {text}." for i, (_, text) in enumerate(STEPS[1:], 2))
    + ". A persona or lorebook they already have isn't assumed: ask whether to keep it or make one for this story. "
      "Then offer to start the chat.")

APPLY_RULES = (
    "## Apply\n"
    "- A proposal changes nothing until they press its Apply button. Never say something is changed, saved or done "
    "until the [Applied: ...] note comes back.\n"
    "- When they ask for a correction to a proposal, your new proposal replaces the old one: say so in one line "
    "(\"Here's the corrected version: press Apply on this one.\").\n"
    "- When a proposal is still waiting and they talk about something else, or before moving to the next step, "
    "remind them in one short line that it's waiting for Apply (or that they can dismiss it). Don't build the next "
    "step on a change that isn't applied.")


def proposals_section(session):
    """The proposals so far for the system prompt, with the ones still waiting for Apply called out."""
    rows = [p for p in session.proposals or [] if isinstance(p, dict)]
    if not rows:
        return APPLY_RULES
    lines = [f"- {p['id']} {p['kind']}: {p['title']} ({p['status']})" for p in rows]
    waiting = [p for p in rows if p.get("status") == "pending"]
    out = APPLY_RULES + "\n\nProposals so far:\n" + "\n".join(lines)
    if waiting:
        out += ("\n\nWAITING FOR APPLY right now: " + "; ".join(f"“{p['title']}”" for p in waiting)
                + ". Unless they just answered about it, remind them in one line before anything else.")
    return out
