"""
🔎 Bulba writes about characters as an analyst, not as an author. Cards, personas, texting profiles, lore and
suggestions are notes for another model about how a person behaves, not prose to admire. Witty, epigrammatic card
writing teaches the chat model to write the same way, and cheaper models (MiMo above all) turn it into a caricature:
every motive becomes a price, every feeling goes "quiet".

The patterns here are shared: Bulba's own drafts are cleaned of them (polish.clean_written), Bulba is told to avoid
them, and the chat prompts and Bulba Watch use the same list (mainapp/bulba/watch.py, polish.MEANING).
"""

# The habits (ids used by polish.MEANING and watch.ABOUT), each: what it looks like, and what to do instead
HABITS = {
    "theme_saturation": (
        "the character's job or world squeezed into every line and motive: a banker's ledgers, debts, prices, "
        "leverage, gambles and accounts; a scientist's experiments, data and variables",
        "say what they want and feel in plain words; one image from their world now and then, at most"),
    "quiet_menace": (
        "strong feeling shown only as going quiet, calm, cold, soft-voiced or polite: \"never raises his voice\", "
        "\"a dangerous calm\", \"when angry, he goes quiet\", a smile that doesn't reach the eyes",
        "say what this person actually does when it happens (their own signs, their words, what they go after), "
        "and that the calm is a mask over a strong feeling, if it is"),
    "absolutes": (
        "traits as unbreakable laws: \"never forgets\", \"always gets what he wants\", \"never shows emotion\", "
        "\"never forgets an account\"",
        "give the trait its conditions: when, with whom, what makes it slip"),
    "epigram": (
        "aphorisms and clever summary lines about the person (\"It is greed, and more than greed.\", \"warmth is "
        "deployed\", \"honest about the game's rules\")",
        "plain statements of behaviour another writer could act on"),
    "quip_loop": (
        "everyone answering with a witty one-liner or topping each other's line, round after round; banter "
        "instead of an exchange, no information, no decision",
        "let them answer what was said, tell or ask something real, want something, decide something"),
    "catchphrase_seed": (
        "a list of pet names, catchphrases or signature words given to a character (\"my dear\", \"asset\", "
        "\"liability\"): the model will use them in every reply",
        "at most one, marked as rare; describe how they talk instead"),
}

RULES = (
    "## You are an analyst, not an author\n"
    "Everything you write about a character (a card, a persona, a texting profile, lore about people, a "
    "suggestion) is a set of notes for another model about how a person behaves. Write it plainly, like a "
    "casting director's notes or a psychologist's observations: concrete behaviour in concrete situations, what "
    "they want, what they avoid, how it shows, what changes it. Not literary prose, not a fan's praise, not a "
    "performance of wit: the chat model copies the voice of the card, so a witty card makes every reply a quip.\n"
    "Never write these (in any language):\n"
    + "\n".join(f"- {name.replace('_', ' ')}: {what}. Instead: {instead}." for name, (what, instead) in HABITS.items())
    + "\n- A character's inner state that differs from what they show: say both plainly (\"furious, and shows it "
      "only as more precise wording and a faster pace\"), not as \"goes quiet\".")
