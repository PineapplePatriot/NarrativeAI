"""Bulba's conversation loop and tools. See mainapp/data/bulba/instructions.md for its instructions."""
import json
import random
import re
import uuid
from pathlib import Path

from mainapp import ai_client, cards, model_profiles, presets, starters
from mainapp.bulba import library

INSTRUCTIONS = Path(__file__).resolve().parent.parent / "data" / "bulba" / "instructions.md"
GUIDES_DIR = Path(__file__).resolve().parent.parent / "data" / "bulba" / "guides"
# Which guides Bulba reads at each stage (keeps the prompt, and the bill, small)
STAGE_GUIDES = {"extras": ["extras"], "taste": ["asking", "presets", "writing"], "preset": ["presets", "writing"],
                "persona": ["characters", "writing"], "character": ["characters", "writing"], "done": []}
REWRITABLE = ("Roleplay", "Style")
TEST_CHARACTER = Path(__file__).resolve().parent.parent / "data" / "bulba" / "test-character.json"

STAGES = ["extras", "taste", "preset", "persona", "character", "done"]
MAX_TOOL_ROUNDS = 8
HISTORY_LIMIT = 60      # messages of conversation sent to Bulba's model
SAMPLE_WORDS = 250


class BudgetReached(Exception):
    pass


# ---------------------------------------------------------------------------
# What Bulba knows
# ---------------------------------------------------------------------------

def target_profile(session):
    return next((p for p in model_profiles.all_profiles() if p["id"] == session.target_model), None)


def model_knowledge(profile):
    """The knowledge section for the one model the user picked."""
    card = profile.get("card", {})
    style = profile.get("style", {})
    lines = [f"## Model knowledge: {profile['name']}", ""]
    if card:
        lines += [f"Where it shines: {card.get('best_for', '')}", f"Watch out: {card.get('watch_out', '')}",
                  f"Price: {card.get('price', '?')} (from $ cheap to $$$$ expensive)", ""]
    if style.get("notes"):
        lines.append("What is known about how it writes (source, status):")
        lines += [f"- {n['text']} ({n.get('source', '?')}, {n.get('status', '?')})" for n in style["notes"]]
        lines.append("")
    if style.get("watch_for"):
        lines.append("Habits to check for in samples: " + "; ".join(style["watch_for"]))
    if style.get("probes"):
        lines.append("Onboarding probes for this model:")
        lines += [f"- {q}" for q in style["probes"]]
    reasoning = profile.get("reasoning", {})
    if reasoning.get("note"):
        lines += ["", f"Thinking: {reasoning['note']}"]
    fixed = [k for k, r in profile.get("samplers", {}).items() if r.get("status") == "fixed"]
    if fixed:
        lines.append("Settings this model fixes itself (don't promise to change them): " + ", ".join(fixed))
    lines += ["", "Starters for this model (the base for propose_preset):"]
    for sid in profile.get("starters", {}).values():
        s = starters.get(sid)
        if s:
            lines.append(f"- {s['id']}: {s['title']}. {s['tagline']} {s['description']}")
    return "\n".join(lines)


def system_prompt(session):
    profile = target_profile(session)
    text = INSTRUCTIONS.read_text(encoding="utf-8").replace("{target_model}", profile["name"] if profile else "?")
    progress = f"Current stage: {session.stage}. Budget: ${session.spent:.2f} of ${session.budget:.2f} spent."
    prefs = [f"- {p['id']} [{p['status']}, {p['scope']}] {p['interpretation']} (they said: \"{p['wording']}\")"
             for p in session.preferences if p.get("status") not in ("rejected", "superseded")]
    pending = [f"- {p['id']} {p['kind']}: {p['title']} ({p['status']})" for p in session.proposals]
    guides = [(GUIDES_DIR / f"{g}.md").read_text(encoding="utf-8") for g in STAGE_GUIDES.get(session.stage, [])
              if (GUIDES_DIR / f"{g}.md").exists()]
    return "\n\n".join(filter(None, [
        text,
        *guides,
        model_knowledge(profile) if profile else "",
        "## Session\n" + progress,
        "Preferences so far:\n" + "\n".join(prefs) if prefs else "",
        "Proposals so far:\n" + "\n".join(pending) if pending else "",
    ]))


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

def _fn(name, description, properties, required=()):
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": properties, "required": list(required)}}}


STR = {"type": "string"}
TOOLS = [
    _fn("get_current_setup", "What is already set up: chat model, extras, presets, persona, characters.", {}),
    _fn("get_starter", "The full text of one of this model's starters (its Roleplay and Style sections).",
        {"starter": STR}, ["starter"]),
    _fn("show_basics_form", "Show the basics form: the plain settings (language, point of view, tense, reply "
        "length, how speech and actions look, coloured speech, in-story panels, genres, pacing, narration voice, "
        "an author to write like, things to keep out) answered in "
        "one go. Use it once, at the start of the taste stage. Their answers come back as a message and are "
        "already recorded as preferences.", {}),
    _fn("look_up", "Search the web for facts about a known character, setting or work (canon details, timeline, "
        "personality, how they speak). Costs a little; use it before writing a character from an existing work.",
        {"query": {"type": "string", "description": "What to find, e.g. 'Il Dottore Genshin Impact personality, "
                   "appearance and history (Sumeru era)'"}}, ["query"]),
    _fn("set_stage", "Move to another stage of the setup.", {"stage": {"type": "string", "enum": STAGES}}, ["stage"]),
    _fn("offer_choices", "Show quick-reply buttons under your message. A choice with a url opens that page instead.",
        {"choices": {"type": "array", "maxItems": 5, "items": {"type": "object", "properties": {
            "label": STR, "url": {"type": "string", "description": "Optional: opens a page instead of answering. "
                "Only /users/extras/ (voices, extras), a link you were given in an [Applied: ...] note, "
                "or https://gemini.google.com/ (Nano Banana, for character pictures)"}},
            "required": ["label"]}}}, ["choices"]),
    _fn("write_samples", "Write one or two short sample replies with the user's chat model, shown as A and B. "
        "Same scene for both; each variant adds its own instructions.",
        {"starter": {"type": "string", "description": "Starter id to build on (from the model knowledge)"},
         "from_proposal": {"type": "string", "description": "Instead of a starter: build on one of your preset proposals (id), to test exactly what they'd get"},
         "scenario": {"type": "string", "description": "The situation, two or three sentences"},
         "user_turn": {"type": "string", "description": "What the user's character just said or did"},
         "character": {"type": "object", "description": "Optional; a neutral test character is used otherwise",
                       "properties": {"name": STR, "description": STR}},
         "variants": {"type": "array", "minItems": 1, "maxItems": 2, "items": {"type": "object", "properties": {
             "label": {"type": "string", "description": "Your private name for the variant"},
             "instructions": {"type": "string", "description": "Extra instructions for this variant ('' for none)"}},
             "required": ["label", "instructions"]}}},
        ["scenario", "user_turn", "variants"]),
    _fn("record_preference", "Remember something about the user's taste.",
        {"wording": {"type": "string", "description": "Their words"},
         "interpretation": {"type": "string", "description": "Your plain reading of it"},
         "scope": {"type": "string", "enum": ["general", "character", "scene", "boundary"]},
         "strength": {"type": "string", "enum": ["firm", "flexible"]},
         "status": {"type": "string", "enum": ["tentative", "confirmed", "rejected"]},
         "replaces": {"type": "string", "description": "Optional id of a preference this one updates"}},
        ["wording", "interpretation", "scope", "status"]),
    _fn("propose_extras", "Propose the extras settings (they press Apply).",
        {"summary": {"type": "string", "enum": ["auto", "manual"]}, "summary_every": {"type": "integer"},
         "trackers": {"type": "string", "enum": ["auto", "manual"]}, "trackers_every": {"type": "integer"},
         "sprites": {"type": "boolean"},
         "background": {"type": "string", "description": "'chat', or a cheap model id: mimo-v2-6-pro, gemini-3-8-flash, glm-5-3, deepseek-v4-pro, deepseek-v4-flash"},
         "why": STR}, ["why"]),
    _fn("propose_preset", "Propose the finished preset: a starter plus a short 'your taste' section.",
        {"starter": STR, "name": STR, "taste": {"type": "string", "description": "Plain instructions to the model"},
         "reply_length": {"type": "string", "enum": ["short", "medium", "long"]},
         "rewrite": {"type": "object", "description": "Only if the starter contradicts them: full replacement text for its Roleplay and/or Style section",
                     "properties": {"Roleplay": STR, "Style": STR}},
         "borrow": {"type": "array", "maxItems": 6, "items": STR,
                    "description": "Library blocks (exact names from find_practice) to add word for word"},
         "why": STR},
        ["starter", "taste", "why"]),
    _fn("propose_persona", "Propose who the user is in the story.",
        {"name": STR, "description": STR, "why": STR}, ["name", "description"]),
    _fn("propose_character", "Propose a character to chat with.",
        {"name": STR, "description": STR, "scenario": STR, "greeting": STR,
         "personality": STR, "example_dialogue": STR, "why": STR},
        ["name", "description", "greeting"]),
    *library.tool_defs(_fn, STR),
]


def _proposal(session, kind, title, summary, payload):
    for older in session.proposals:
        if older["kind"] == kind and older["status"] == "pending":
            older["status"] = "replaced"
    p = {"id": uuid.uuid4().hex[:12], "kind": kind, "title": title, "summary": summary,
         "payload": payload, "status": "pending"}
    session.proposals.append(p)
    return p


def tool_get_current_setup(session, args):
    from users.views import _extras_state
    from mainapp.models import Character, Preset
    user = session.user
    extras = _extras_state(user)
    active = presets.get_active(user)
    return {
        "chat_model": extras["chat_model"],
        "extras": {k: extras[k] for k in ("has_eleven_key", "summary", "trackers", "sprites", "background")},
        "active_preset": active.name,
        "presets": [p.name for p in Preset.objects.filter(user=user)][:20],
        "persona": {"name": getattr(user, "persona_name", "") or "", "description": getattr(user, "persona_description", "") or ""},
        "characters": [{"name": c.name, "description": (c.description or "")[:200]}
                       for c in Character.objects.filter(author=user)[:20]],
    }, []


def tool_set_stage(session, args):
    if args.get("stage") in STAGES:
        session.stage = args["stage"]
    return {"stage": session.stage}, [{"type": "stage", "stage": session.stage}]


def tool_offer_choices(session, args):
    choices = []
    for c in (args.get("choices") or [])[:5]:
        if isinstance(c, dict) and str(c.get("label", "")).strip():
            url = c.get("url") if str(c.get("url", "")).startswith("/") else None
            choices.append({"label": str(c["label"])[:80], **({"url": url} if url else {})})
    return {"shown": len(choices)}, [{"type": "choices", "choices": choices}]


def _test_character():
    try:
        data = json.loads(TEST_CHARACTER.read_text(encoding="utf-8"))["data"]
        return {"name": data["name"], "description": data["description"] + "\n\n" + data.get("personality", "")}
    except (OSError, ValueError, KeyError):
        return {"name": "Mara", "description": "A practical museum restorer with a dry sense of humour."}


def _starter_for(session, starter_id):
    profile = target_profile(session) or {}
    allowed = set(profile.get("starters", {}).values())
    if starter_id in allowed:
        return starters.get(starter_id)
    default = profile.get("starters", {}).get("rich_scene")
    return starters.get(default) if default else None


def _add_block(preset, name, text):
    """Insert a prompt block right after the Style block (or first) of a normalized preset."""
    block = presets.normalize_block({"name": name, "kind": "prompt", "content": text})
    idx = next((i + 1 for i, b in enumerate(preset["blocks"]) if b["name"] == "Style"), 1)
    preset["blocks"].insert(idx, block)
    return preset


def build_preset(payload):
    """A normalized preset from a preset proposal's payload: starter, rewritten sections, taste."""
    starter = starters.get(payload["starter"])
    preset = presets.normalize(starter["preset"])
    for block in preset["blocks"]:
        if block["kind"] == "prompt" and block["name"] in (payload.get("rewrite") or {}):
            block["content"] = payload["rewrite"][block["name"]]
    length = LENGTHS.get(payload.get("reply_length"))
    if length and not _replace_length_line(preset, length):
        payload = {**payload, "taste": (payload.get("taste", "") + "\n" + length).strip()}
    for name in reversed(payload.get("borrow") or []):
        block = library.get(name)
        if block and not any(b["name"] == name for b in preset["blocks"]):
            _add_block(preset, name, block["content"])
        elif block:  # already in this preset (a community one): just switch it on
            next(b for b in preset["blocks"] if b["name"] == name)["enabled"] = True
    if payload.get("taste"):
        _add_block(preset, "Your taste", payload["taste"])
    return preset


LENGTH_LINE = re.compile(r"^- (?:Usually|Length:|Short replies:)[^\n]*?(?:paragraph|words)[^\n]*$", re.M | re.I)


def _replace_length_line(preset, length):
    """Swap the starter's own length rule for theirs, so the model never gets two. False if none found."""
    for block in preset["blocks"]:
        if block["kind"] == "prompt" and block["name"] == "Style":
            m = LENGTH_LINE.search(block["content"])
            if m:
                tail = re.search(r"\. (End where .*)$", m.group(0))  # keep "End where {{user}} ..." clauses
                line = "- " + length + (" " + tail.group(1) if tail else "")
                block["content"] = block["content"][:m.start()] + line + block["content"][m.end():]
                return True
    return False


def generate_sample(session, preset, scenario, user_turn, character, instructions):
    """One reply from the user's chat model, using a preset (+ instructions). Returns (text, cost)."""
    user = session.user
    preset = presets.normalize(preset)
    extra = (instructions or "").strip()
    unknown = "" if (getattr(user, "persona_description", "") or "").strip() else (
        "\n\nNothing is known about {{user}} yet: don't give them a gender (no he or she), a look or a past.")
    _add_block(preset, "Sample instructions",
               (extra + "\n\n" if extra else "") + f"Keep this reply under {SAMPLE_WORDS} words." + unknown)
    _, chat_model = ai_client.resolve(user, "chat")
    slots = {"char_description": character["description"], "scenario": scenario,
             "persona": getattr(user, "persona_description", "") or ""}
    names = {"char": character["name"], "user": cards.user_name(user)}
    built = presets.assemble(preset, slots, [{"role": "user", "content": user_turn}], names, chat_model)
    message, cost = ai_client.complete_message(user, "chat", built["messages"], **built["params"])
    return (message.get("content") or "").strip(), cost


def tool_get_starter(session, args):
    starter = _starter_for(session, args.get("starter"))
    if starter is None:
        return {"error": "No starter for this model."}, []
    sections = {b["name"]: b["content"] for b in starter["preset"]["blocks"]
                if b.get("kind") == "prompt" and b.get("name") in REWRITABLE}
    return {"id": starter["id"], "title": starter["title"], "sections": sections}, []


def tool_write_samples(session, args):
    proposal = next((p for p in session.proposals if p["id"] == args.get("from_proposal") and p["kind"] == "preset"), None)
    if args.get("from_proposal") and proposal is None:
        return {"error": "No preset proposal with that id."}, []
    if proposal:
        preset = build_preset(proposal["payload"])
    else:
        starter = _starter_for(session, args.get("starter"))
        if starter is None:
            return {"error": "No starter for this model."}, []
        preset = starter["preset"]
    character = args.get("character") if isinstance(args.get("character"), dict) and args["character"].get("name") else _test_character()
    character = {"name": str(character["name"])[:80], "description": str(character.get("description", ""))[:3000]}
    variants = [v for v in (args.get("variants") or []) if isinstance(v, dict)][:2]
    if not variants:
        return {"error": "Give at least one variant."}, []
    random.shuffle(variants)  # the user sees A and B in random order
    samples, private = [], {}
    model_name = (target_profile(session) or {}).get("name", "your model")
    for letter, v in zip("AB", variants):
        set_activity(session, f"Writing sample {letter} with {model_name}…" if len(variants) > 1
                     else f"Writing a test reply with {model_name}…")
        _check_budget(session)
        text, cost = generate_sample(session, preset, str(args.get("scenario", "")), str(args.get("user_turn", "")),
                                     character, str(v.get("instructions", "")))
        session.spent += cost or 0
        samples.append({"label": letter, "text": text})
        private[letter] = {"variant": v.get("label"), "text": text}
    profile = target_profile(session) or {}
    shown = lambda text: cards.fill_names(str(text or ""), character["name"], cards.user_name(session.user))
    return ({"shown_to_user_as": private, "note": "They see only the letters, not your variant names."},
            [{"type": "samples", "model": profile.get("name", ""), "character": character["name"],
              "scenario": shown(args.get("scenario")), "user_turn": shown(args.get("user_turn")),
              "samples": samples}])


LOOKUP_PROMPT = ("You research fiction for someone writing a roleplay character card. Using the web results, "
                 "answer factually and concisely: who they are, appearance, personality and how it shows, how they "
                 "speak, key relationships and history, and which version or timeline the facts belong to. Say "
                 "plainly when sources disagree or something isn't known. No speculation, no fan theories as fact.")


def tool_look_up(session, args):
    from users.models import ConnectionProfile
    query = str(args.get("query") or "").strip()[:300]
    if not query:
        return {"error": "Say what to look up."}, []
    profile, _ = ai_client.resolve(session.user, "bulba")
    if profile.provider != ConnectionProfile.PROVIDER_OPENROUTER:
        return {"error": "Web search only works through OpenRouter. Rely on what you know, and say so."}, []
    _check_budget(session)
    set_activity(session, f"Looking up {query[:60]} on the web…")
    message, cost = ai_client.complete_message(
        session.user, "bulba", [{"role": "system", "content": LOOKUP_PROMPT}, {"role": "user", "content": query}],
        plugins=[{"id": "web", "max_results": 5}], max_tokens=1500)
    session.spent += cost or 0
    notes = [a.get("url_citation", {}) for a in message.get("annotations") or [] if isinstance(a, dict)]
    sources = [{"title": n.get("title", ""), "url": n.get("url", "")} for n in notes if n.get("url")][:5]
    return {"findings": (message.get("content") or "").strip()[:6000], "sources": sources}, [
        {"type": "lookup", "query": query, "sources": sources}]


# The basics form: plain settings, no interpretation needed. key -> (question, {answer: preference text})
BASICS = {
    "language": ("Story language", None),  # free text, default English
    "pov": ("Point of view", {
        "second": "Narrate in second person for {{user}} (\"you step inside\").",
        "third": "Narrate in third person (\"she steps inside\").",
        "first": "Narrate in first person from {{char}}'s point of view (\"I step inside\")."}),
    "tense": ("Tense", {"present": "Write in present tense.", "past": "Write in past tense."}),
    "length": ("Reply length", {"short": "short", "medium": "medium", "long": "long"}),
    "format": ("Speech and actions", {
        "quotes": "Put speech in double quotes; write actions as plain prose.",
        "asterisks": "Put speech in double quotes and actions in *asterisks*.",
        "any": ""}),
    "colors": ("Coloured speech", {
        "on": "Give each character's spoken lines their own colour: wrap each quoted line in "
              "<font color=\"#RRGGBB\">\"...\"</font>, keep one colour per character for the whole story, "
              "and pick colours that read well on a dark background.",
        "off": ""}),
    "panels": ("In-story panels", {
        "on": "When a text message, note, letter, sign or screen appears in the story, show it as a small "
              "self-contained HTML panel with inline styles (for example a phone chat as message bubbles), "
              "then carry on with the prose.",
        "off": ""}),
    "genres": ("Genres", {  # several may be picked (wording after Celia's genre toggles)
        "fluff": "light-hearted warmth, affectionate exchanges and cozy moments",
        "slice_of_life": "the quiet charm of everyday life, routine and small connections",
        "comedy": "humour, banter and absurd or exaggerated situations",
        "romance": "real emotional connection, chances to bond and slowly growing intimacy",
        "heartwarming": "kindness, hope and joy in simple gestures, even through hard times",
        "melancholy": "bittersweet moments where wonder and gentle sorrow sit together",
        "healing": "hurt and comfort: emotional wounds, tender support and trust slowly rebuilt",
        "angst": "emotional tension, hard decisions, heartbreak and painful realisations",
        "tragedy": "devastating turns and heart-rending scenes, delivered rawly",
        "smut": "explicit sexual content when the story leads there",
        "dead_dove": "dark, cruel and taboo material, morally complex and unsettling, without softening",
    }),
    "pacing": ("Pacing", {
        "quick": "Keep the story moving: skip or summarise the dull stretches with time skips and head for the "
                 "important scenes and events.",
        "slow": "Slow burn: let things develop in small, earned steps, with quiet everyday moments between the "
                "ones that move the story.",
        "any": ""}),
    "voice": ("Narration voice", {  # after Pura's narration voices and Celia's narrative styles
        "hemingway": "Narrate in the manner of Ernest Hemingway: short, plain, loaded sentences; feelings left under the surface.",
        "mccarthy": "Narrate in the manner of Cormac McCarthy: heavy, rhythmic, solemn prose; a harsh, beautiful world.",
        "camus": "Narrate in the manner of Albert Camus: an intimate, mischievous voice with dry amusement and controlled irony.",
        "kafka": "Narrate in the manner of Franz Kafka: dry, bureaucratic irony; the absurd treated as routine.",
        "ligotti": "Narrate in the manner of Thomas Ligotti: chilling metaphysical dread, delivered with quiet relish.",
        "maupassant": "Narrate in the manner of Guy de Maupassant: cruel, clear-eyed realism about pride and fragile dignity.",
        "dickens": "Narrate in the manner of Charles Dickens: a bustling, theatrical world of eccentrics and gentle satire.",
        "ellis": "Narrate in the manner of Bret Easton Ellis: gossipy, cold, hyper-detailed attention to status and things.",
        "anime": "Tell it like an anime: larger-than-life characters, rivalries, familiar character archetypes and big moments.",
        "realism": "Tell it with grounded realism: unexaggerated people and feelings; good and bad happen within reason.",
        "fanfic": "Tell it like a well-loved fanfic: true to the characters' voices, building smartly on canon.",
        "webnovel": "Format it like a web novel: a chapter heading at the top of every reply, web-novel conventions.",
        "any": ""}),
    "author": ("Write like", None),  # free text: an author they love
    "keep_out": ("Keep out", None),  # free text
}
LENGTH_WORDS = {"short": "a few lines", "medium": "a few paragraphs", "long": "a proper chunk"}


def tool_show_basics_form(session, args):
    return {"shown": True, "note": "They'll answer with the form; wait."}, [{"type": "form", "form": "basics"}]


def apply_basics(session, answers):
    """Records the form's answers as confirmed preferences; returns the message Bulba reads."""
    answers = answers if isinstance(answers, dict) else {}
    lines = []
    for key, (label, options) in BASICS.items():
        if key == "genres":
            picked = [g for g in (answers.get(key) or []) if isinstance(g, str) and g in options][:6]
            if picked:
                text = "Lean the story toward " + "; ".join(options[g] for g in picked) + "."
                lines.append(f"{label}: {text}")
                tool_record_preference(session, {"wording": "Basics form: genres", "interpretation": text,
                                                 "scope": "general", "strength": "firm", "status": "confirmed"})
            continue
        raw = str(answers.get(key) or "").strip()[:300]
        if not raw:
            continue
        if key == "author":
            text = f"Write in the style of {raw}: their diction, rhythm and conventions, not their plots."
            lines.append(f"{label}: {text}")
            tool_record_preference(session, {"wording": f"Basics form: write like {raw}", "interpretation": text,
                                             "scope": "general", "strength": "flexible", "status": "confirmed"})
            continue
        if options is None:
            if key == "language" and raw.lower() in ("english", "en"):
                lines.append(f"{label}: English")
                continue
            text = (f"Write the whole story in {raw}." if key == "language" else f"Keep out: {raw}.")
            scope = "boundary" if key == "keep_out" else "general"
        else:
            if raw not in options:
                continue
            text, scope = options[raw], "general"
            if key == "length":
                text = f"Reply length: {LENGTH_WORDS[raw]} (reply_length {raw})."
            if not text:
                lines.append(f"{label}: no preference")
                continue
        lines.append(f"{label}: {text}")
        tool_record_preference(session, {"wording": f"Basics form: {label.lower()}", "interpretation": text,
                                         "scope": scope, "strength": "firm", "status": "confirmed"})
    return "Basics form answers (already recorded as preferences):\n" + ("\n".join(lines) if lines else "(left empty)")


def tool_record_preference(session, args):
    pref = {"id": uuid.uuid4().hex[:8], "wording": str(args.get("wording", ""))[:300],
            "interpretation": str(args.get("interpretation", ""))[:300],
            "scope": args.get("scope") if args.get("scope") in ("general", "character", "scene", "boundary") else "general",
            "strength": args.get("strength") if args.get("strength") in ("firm", "flexible") else "flexible",
            "status": args.get("status") if args.get("status") in ("tentative", "confirmed", "rejected") else "tentative"}
    replaced = next((p for p in session.preferences if p["id"] == args.get("replaces")), None)
    if replaced:
        replaced["status"] = "superseded"
    session.preferences.append(pref)
    return {"id": pref["id"]}, [{"type": "preference", "id": pref["id"]}]


def tool_propose_extras(session, args):
    from users.views import _cheap_models
    payload, summary = {}, []
    if args.get("summary") in ("auto", "manual"):
        every = max(1, min(200, int(args.get("summary_every") or 10)))
        payload["summary"] = {"mode": args["summary"], "interval": every}
        summary.append(f"Story summary: {'every ' + str(every) + ' messages' if args['summary'] == 'auto' else 'only when you ask'}")
    if args.get("trackers") in ("auto", "manual"):
        every = max(1, min(200, int(args.get("trackers_every") or 2)))
        payload["trackers"] = {"mode": args["trackers"], "interval": every}
        summary.append(f"Story trackers: {'every ' + str(every) + ' messages' if args['trackers'] == 'auto' else 'only when you ask'}")
    if isinstance(args.get("sprites"), bool):
        payload["sprites"] = args["sprites"]
        summary.append("Character pictures that match the mood: " + ("on" if args["sprites"] else "off"))
    bg = args.get("background")
    cheap = {m["id"]: m["name"] for m in _cheap_models()}
    if bg == "chat" or bg in cheap:
        payload["background"] = bg
        summary.append("Background jobs: " + ("your chat model" if bg == "chat" else cheap[bg]))
    if not payload:
        return {"error": "Nothing to propose."}, []
    p = _proposal(session, "extras", "Extras", summary, payload)
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


LENGTHS = {"short": "Keep replies short: one to three paragraphs.",
           "medium": "Keep replies to about three to five paragraphs.",
           "long": "Longer replies are welcome: five or more paragraphs when the moment allows."}


def tool_propose_preset(session, args):
    starter = _starter_for(session, args.get("starter"))
    if starter is None:
        return {"error": "No starter for this model."}, []
    taste = str(args.get("taste", "")).strip()
    reply_length = args.get("reply_length") if args.get("reply_length") in LENGTHS else ""
    rewrite = {}
    originals = {b["name"]: b["content"] for b in starter["preset"]["blocks"] if b.get("kind") == "prompt"}
    for section, text in (args.get("rewrite") or {}).items():
        text = str(text or "").strip()
        if section not in REWRITABLE or not text or text == originals.get(section):
            continue
        # A rewrite must keep the placeholders the starter relies on
        missing = [m for m in ("{{char}}", "{{user}}") if m in originals.get(section, "") and m not in text]
        if missing:
            return {"error": f"Your {section} rewrite dropped {', '.join(missing)}; keep them."}, []
        rewrite[section] = text[:6000]
    borrow = [str(n).strip() for n in (args.get("borrow") or [])][:6]
    unknown = [n for n in borrow if library.get(n) is None]
    if unknown:
        return {"error": f"Not in the library: {', '.join(unknown)}. Use the exact names from find_practice."}, []
    profile = target_profile(session) or {}
    name = str(args.get("name") or f"My setup · {profile.get('name', '')}").strip()[:120]
    summary = [f"Built on the {starter['title']} starter for {profile.get('name', '')}"]
    if rewrite:
        summary.append("Adjusted from the starter: " + " and ".join(rewrite) + " section")
    if borrow:
        summary += ["Tested blocks added from Realistic Frankenstein:", *[f"  {n}" for n in borrow]]
    summary += ["Your taste:", *[f"  {line}" for line in taste.splitlines() if line.strip()]]
    if reply_length:
        summary += ["Reply length:", f"  {LENGTHS[reply_length]}"]
    p = _proposal(session, "preset", f"Preset: {name}", summary,
                  {"starter": starter["id"], "name": name, "taste": taste, "rewrite": rewrite,
                   "reply_length": reply_length, "borrow": borrow})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_propose_persona(session, args):
    name = str(args.get("name", "")).strip()[:100]
    desc = str(args.get("description", "")).strip()[:3000]
    if not name or not desc:
        return {"error": "Need a name and a description."}, []
    p = _proposal(session, "persona", f"You: {name}", [desc], {"name": name, "description": desc})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def tool_propose_character(session, args):
    name = str(args.get("name", "")).strip()[:100]
    if not name or not str(args.get("description", "")).strip():
        return {"error": "Need a name and a description."}, []
    payload = {k: str(args.get(k, "")).strip()[:6000]
               for k in ("description", "scenario", "greeting", "personality", "example_dialogue")}
    payload["name"] = name
    summary = ["Description:", payload["description"]]
    if payload["personality"]:
        summary += ["In short:", payload["personality"]]
    if payload["scenario"]:
        summary += ["Scenario:", payload["scenario"]]
    summary += ["First message:", payload["greeting"]]
    if payload["example_dialogue"]:
        summary += ["Example dialogue:", payload["example_dialogue"]]
    p = _proposal(session, "character", f"Character: {name}", summary, payload)
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


HANDLERS = {
    "get_current_setup": tool_get_current_setup, "get_starter": tool_get_starter, "look_up": tool_look_up,
    "show_basics_form": tool_show_basics_form, "set_stage": tool_set_stage, "offer_choices": tool_offer_choices,
    "write_samples": tool_write_samples, "record_preference": tool_record_preference,
    "propose_extras": tool_propose_extras, "propose_preset": tool_propose_preset,
    "propose_persona": tool_propose_persona, "propose_character": tool_propose_character,
    **library.HANDLERS,
}


# ---------------------------------------------------------------------------
# The loop
# ---------------------------------------------------------------------------

def set_activity(session, text):
    """What the page shows while a turn runs ("Writing sample A with MiMo..."). Saved at once, on its own."""
    from mainapp.models import BulbaSession
    if session.pk:
        BulbaSession.objects.filter(pk=session.pk).update(activity=str(text or "")[:200])


def _check_budget(session):
    if session.spent >= session.budget:
        raise BudgetReached(f"This session reached its ${session.budget:.2f} limit.")


def _trimmed(messages):
    """The recent conversation, starting at a user message so tool calls and results stay paired."""
    if len(messages) <= HISTORY_LIMIT:
        return messages
    tail = messages[-HISTORY_LIMIT:]
    first_user = next((i for i, m in enumerate(tail) if m.get("role") == "user"), 0)
    return tail[first_user:]


def opening(session):
    """Bulba's first message (canned, so starting costs nothing)."""
    profile = target_profile(session) or {"name": "your model"}
    text = (f"Hi. I'm Bulba. Yes, a potato. You picked {profile['name']}, which is a choice.\n\n"
            "I'll set up the rest: the extras, how replies read, who you are in the story, and who you're "
            "talking to. Ten minutes, maybe. Stop whenever.\n\n"
            "Boring bits first: should characters be able to speak out loud? That needs an ElevenLabs account.")
    choices = [{"label": "No voices"}, {"label": "Yes, I have an ElevenLabs key", "url": "/users/extras/"},
               {"label": "What's ElevenLabs?"}]
    session.messages = [{"role": "assistant", "content": text}]
    session.events = [{"type": "bulba", "text": text, "choices": choices}]


# Tools after which Bulba waits for the user (see instructions.md, "Tools, briefly")
TURN_ENDING = {"offer_choices", "write_samples", "show_basics_form", "retry_reply",
               "propose_preset_edit", "propose_card_edit", "propose_extras", "propose_preset", "propose_persona", "propose_character"}


def run_turn(session, user_text, action_note=None, model_note=None):
    """
    Adds the user's message (or a note about something they did, like pressing Apply), lets Bulba
    think and use tools, and returns the new page events.
    """
    user_text = str(user_text or "").strip()[:12000]  # room for a pasted piece of writing they like
    new_events = []
    if action_note:
        session.messages.append({"role": "user", "content": f"[{model_note or action_note}]"})
        new_events.append({"type": "action", "text": action_note})
    elif user_text:
        session.messages.append({"role": "user", "content": user_text})
        new_events.append({"type": "user", "text": user_text})

    pending_choices = None
    try:
        for _ in range(MAX_TOOL_ROUNDS):
            _check_budget(session)
            set_activity(session, "Bulba is thinking…")
            in_chat = session.mode == "chat"
            if in_chat:
                from mainapp.bulba import doctor
            request = ([{"role": "system", "content": doctor.system_prompt(session) if in_chat else system_prompt(session)}]
                       + _trimmed(session.messages))
            message, cost = ai_client.complete_message(session.user, "bulba", request,
                                                       tools=doctor.tools() if in_chat else TOOLS,
                                                       tool_choice="auto", max_tokens=4000)
            session.spent += cost or 0
            calls = message.get("tool_calls") or []
            content = (message.get("content") or "").strip()
            if not content and not calls:
                break  # nothing more to say; an empty assistant turn would only confuse some providers
            entry = {"role": "assistant", "content": content}
            if calls:
                entry["tool_calls"] = calls
            session.messages.append(entry)
            if content:
                new_events.append({"type": "bulba", "text": content})
            if not calls:
                break
            waiting_for_user = False
            for call in calls:
                fn = (call.get("function") or {})
                name = fn.get("name")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = None
                handlers = {**HANDLERS, **doctor.HANDLERS} if in_chat else HANDLERS
                if name not in handlers or not isinstance(args, dict):
                    result, events = {"error": f"Unknown tool or bad arguments: {name}"}, []
                else:
                    try:
                        result, events = handlers[name](session, args)
                    except BudgetReached:
                        raise
                    except ai_client.AIError as e:
                        result, events = {"error": str(e)}, [{"type": "error", "text": str(e)}]
                for ev in events:
                    if ev["type"] == "choices":
                        pending_choices = ev["choices"]
                    else:
                        new_events.append(ev)
                session.messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                         "content": json.dumps(result, ensure_ascii=False)})
                if name in TURN_ENDING and "error" not in result:
                    waiting_for_user = True
            # Buttons, samples or a proposal mean "your move": no extra (paid) round just to hear nothing
            # new. A tool that failed doesn't count, so Bulba still sees the error and can fix it.
            if waiting_for_user:
                break
    except BudgetReached as e:
        new_events.append({"type": "error", "text": f"{e} Raise it in the panel if you want to continue."})
    except ai_client.AIError as e:
        new_events.append({"type": "error", "text": str(e)})

    if pending_choices:
        last = next((ev for ev in reversed(new_events) if ev["type"] == "bulba"), None)
        if last is None:
            last = {"type": "bulba", "text": ""}
            new_events.append(last)
        last["choices"] = pending_choices
    session.events.extend(new_events)
    return new_events
