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
      "only as more precise wording and a faster pace\"), not as \"goes quiet\".\n"
      "- Details: real and specific, not stock. When a card, persona, greeting or lore touches luxury, clothes, "
      "food, science, politics or a genre trope, check look_up_texture first for what it's really like.")


# ✍️ Bad-and-good pairs for models that slide into these habits (MiMo): shown once, before the chat. A model copies
# an example better than it obeys a ban. Each pair: the habit, the tired version, the version that does the work.
EXAMPLE_PAIRS = [
    ("everything turned into the character's job",
     "The banker weighs your words like coins. \"An interesting investment, my dear. But every debt is collected.\"",
     "The banker reads your letter twice, then turns it face down. \"You came alone. Good. Sit, and tell me who "
     "else knows.\""),
    ("a strong feeling shown only as going quiet",
     "He doesn't raise his voice. He never has to.",
     "He stops writing mid-word, caps the pen, and asks you to say that again, slower, while his assistant finds a "
     "reason to leave the room."),
    ("the same detail brought back reply after reply",
     "[the same lamp, rain or smell as in the last few replies], again, framing the moment.",
     "[something this moment brings that wasn't there before, and that changes what happens: a noise that "
     "interrupts, someone arriving, a thing going wrong]"),
    ("lines that only top the last line",
     "\"Bold of you to assume I'd care.\" \"Bold of you to assume I asked.\"",
     "\"I don't care,\" she says, and then, because that isn't true: \"Why didn't you call?\""),
]

EXAMPLES_BLOCK = (
    "[How to write it: examples. Each pair shows a tired habit and the version that does the work. Write like the "
    "second of each pair; never copy their words, characters or details.]\n\n"
    + "\n\n".join(f"{what}:\n✗ {bad}\n✓ {good}" for what, bad, good in EXAMPLE_PAIRS))



def tool_look_up_texture(session, args):
    """🧵 The built-in world texture library (mainapp/texture.py), for concrete specifics in cards, personas, lore."""
    from mainapp import mature, texture
    found = texture.look_up(str(args.get("query") or "")[:200], mature=mature.wanted(session.user))
    if not found:
        return {"result": "Nothing in the library for that; use look_up for the web, or your own knowledge."}, []
    return {"entries": found, "note": "Draw on these for concrete, varied detail (pick, don't list them all); the "
                                      "card's and the story's own facts come first."}, []


def tool_defs(fn, STR):
    return [fn("look_up_texture", "The app's own library of concrete, varied specifics (luxury, clothing styles by "
               "era, food by cuisine, lab and hospital life, courts, parliaments, bureaucracy, organised crime, "
               "genre tropes such as vampires, fae, dragons, omegaverse...): what it's really like, the tired version "
               "to avoid, and specifics. Use it when writing a card, persona, greeting or lore that touches these, "
               "so details are real and not stock. Free.", {"query": STR}, ["query"])]


HANDLERS = {"look_up_texture": tool_look_up_texture}



REWRITE = (
    "You rewrite drafts of a roleplay character card (or a persona, a greeting, lore) that another assistant wrote. "
    "Keep every fact, name, relationship, {{char}} and {{user}} exactly; keep each field's purpose and roughly its "
    "length. Change only the writing, following these rules:\n\n" + RULES + "\n\n"
    "A greeting stays a scene in the story's voice (not notes), but plain and specific, without these habits. "
    "Answer with JSON only: the same keys, each with its rewritten text.")


def rewrite(user, fields, what="character card"):
    """{field: text} rewritten by their card-writing model (ai_client task "card_writing"), or None (not set up,
    or the answer didn't hold: then the usual cleanup runs)."""
    import json
    from mainapp import ai_client
    texts = {k: v for k, v in fields.items() if isinstance(v, str) and v.strip()}
    if not texts or not ai_client.card_writer_set(user):
        return None
    try:
        answer = ai_client.complete(user, "card_writing", [
            {"role": "system", "content": REWRITE},
            {"role": "user", "content": f"## The {what} draft (JSON)\n" + json.dumps(texts, ensure_ascii=False)}],
            max_tokens=6000, temperature=0.4, response_format={"type": "json_object"})
        data = json.loads(answer[answer.find("{"):answer.rfind("}") + 1])
    except (ai_client.AIError, ValueError):
        return None
    if not isinstance(data, dict) or set(data) != set(texts) or not all(isinstance(v, str) and v.strip() for v in data.values()):
        return None
    return {**fields, **{k: v.strip() for k, v in data.items()}}
