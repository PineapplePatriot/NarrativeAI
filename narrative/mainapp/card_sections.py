"""
Structured cards: a card kept as sections (who they are, how they look, how they act...), composed into the one
description text every prompt path, SillyTavern export and Bulba already read.

- Three kinds of card. *Character*: one person. *Ensemble*: several people, each with their own sections, plus
  what they share. *Simulation*: a world rather than a person, which makes new people as the story goes (story
  memory keeps them, mainapp/memory.py).
- Every section can be switched off (it then costs nothing); the page shows what each one costs in tokens.
- Temperament is ours: how fast they warm to someone, what wounds them, where their attitude to {{user}} starts,
  and which route a relationship with them leans to. Story memory's relationship progression starts from it.
- An old card (or a SillyTavern import) is sorted into sections by its own headings when it has them, by Bulba
  when it doesn't; anything that fits nowhere stays word for word in "More", so nothing is lost.

Stored on Character.sections:
    {"kind": "character" | "ensemble" | "simulation", "version": 1,
     "shared": {key: {"text": str, "on": bool}},
     "people": [{"name": str, "sections": {key: {"text", "on"}}, "temperament": {"pace", "route", "start"}}],
     "extra": [{"title": str, "text": str, "on": bool}]}     # their own sections, after everything else
"""
import json
import re

VERSION = 1
KINDS = ("character", "ensemble", "simulation")

# A person's sections, in the order they're composed (the order models weigh them: who, looks, how they act)
PERSON = [
    ("identity", "Who they are", "Name, age, what they are and do, where they stand in this world. Two or three lines."),
    ("appearance", "Appearance", "Build, face, hair, eyes, what they usually wear, how they move. Never cut it: the story and the pictures rely on it."),
    ("personality", "Personality in action", "How they behave, shown as what they do: when, to whom, at what cost. Not a list of adjectives."),
    ("temperament", "Temperament", "How fast they warm up to someone, what hurts them, what wins them over, where their attitude to {{user}} starts."),
    ("goals", "Wants and conflicts", "What they want now, what stands in the way, what they'd never do."),
    ("voice", "Voice", "How they talk: rhythm, words they use or avoid, one sample line in their voice."),
    ("background", "Background", "Only the past that drives the present."),
    ("relationships", "Relationships", "With {{user}} first, then the people who matter to them."),
    ("knowledge", "Knowledge and secrets", "What they know that others don't, and what they hide."),
]
# What several people share (ensemble), or what a world is made of (simulation)
SHARED = {
    "ensemble": [
        ("setting", "Setting", "Where and when these people are, and what brings them together."),
        ("between", "Between them", "How they relate to each other: alliances, rivalries, history, who defers to whom."),
    ],
    "simulation": [
        ("world", "World and rules", "What this world is, how it works, what's possible and what isn't."),
        ("places", "Places", "The places the story moves between, one line each."),
        ("factions", "Factions and powers", "Who holds power, who wants it, how they treat outsiders."),
        ("tone", "Tone", "The feel of the story: genre, how dark or light, how fast."),
        ("start", "Starting situation", "Where {{user}} is when the story opens and what's happening."),
        ("new_people", "New people", "What kinds of people {{user}} meets, how they're introduced (name, look, what they want), which ones come back. The narrator voices them all and never {{user}}."),
    ],
    "character": [],
}

PACES = {"slow": "slow to warm up", "steady": "warms up at an ordinary pace", "fast": "quick to warm up"}
ROUTES = {
    "basic": ("Basic", ["stranger", "acquaintance", "friend", "close friend", "trusted"]),
    "romance": ("Romance", ["stranger", "interested", "attracted", "courting", "together", "devoted"]),
    "enemies": ("Enemies", ["stranger", "wary", "rival", "enemy", "nemesis"]),
    "enemies_to_lovers": ("Enemies to lovers", ["enemy", "grudging respect", "uneasy allies", "drawn in", "together"]),
    "mentor": ("Mentor and student", ["stranger", "teacher", "mentor", "trusted mentor", "equals"]),
    "rivals": ("Rivals", ["stranger", "competitor", "rival", "respected rival", "friendly rival"]),
    "family": ("Found family", ["stranger", "acquaintance", "ally", "family"]),
}


def labels(kind="character"):
    """{key: (title, hint)} for a card of this kind, the person's and the shared ones."""
    out = {k: (t, h) for k, t, h in PERSON}
    out.update({k: (t, h) for k, t, h in SHARED.get(kind, [])})
    return out


def empty(kind="character", names=("",)):
    kind = kind if kind in KINDS else "character"
    people = [] if kind == "simulation" and not any(names) else [
        {"name": n, "sections": {k: {"text": "", "on": True} for k, _, _ in PERSON},
         "temperament": {"pace": "steady", "route": "basic", "start": ""}} for n in names]
    return {"kind": kind, "version": VERSION, "shared": {k: {"text": "", "on": True} for k, _, _ in SHARED[kind]},
            "people": people, "extra": []}


def clean(data):
    """Whatever arrived (the page, Bulba) as a well-formed sections record, or None."""
    if not isinstance(data, dict):
        return None
    kind = data.get("kind") if data.get("kind") in KINDS else "character"

    def sec(value):
        if isinstance(value, str):
            return {"text": value.strip()[:8000], "on": True}
        if isinstance(value, dict):
            return {"text": str(value.get("text") or "").strip()[:8000], "on": value.get("on", True) is not False}
        return {"text": "", "on": True}

    shared = {k: sec((data.get("shared") or {}).get(k)) for k, _, _ in SHARED[kind]}
    people = []
    for p in (data.get("people") or [])[:12]:
        if not isinstance(p, dict):
            continue
        given = p.get("sections") or {}
        temper = p.get("temperament") if isinstance(p.get("temperament"), dict) else {}
        people.append({
            "name": str(p.get("name") or "").strip()[:120],
            "sections": {k: sec(given.get(k)) for k, _, _ in PERSON},
            "temperament": {"pace": temper.get("pace") if temper.get("pace") in PACES else "steady",
                            "route": temper.get("route") if temper.get("route") in ROUTES else "basic",
                            "start": str(temper.get("start") or "").strip()[:60]},
        })
    extra = [{"title": str(e.get("title") or "More").strip()[:80] or "More", "text": str(e.get("text") or "").strip()[:12000],
              "on": e.get("on", True) is not False}
             for e in (data.get("extra") or [])[:20] if isinstance(e, dict) and str(e.get("text") or "").strip()]
    if kind != "simulation" and not people:
        people = empty(kind)["people"]
    return {"kind": kind, "version": VERSION, "shared": shared, "people": people, "extra": extra}


def _temper_line(p):
    t = p.get("temperament") or {}
    bits = [PACES.get(t.get("pace"), "") if t.get("pace") != "steady" else ""]
    route = ROUTES.get(t.get("route"))
    if route and t.get("route") != "basic":
        bits.append(f"a relationship with them leans toward {route[0].lower()}")
    if t.get("start"):
        bits.append(f"their attitude to {{{{user}}}} starts as: {t['start']}")
    bits = [b for b in bits if b]
    return ("(" + "; ".join(bits) + ")") if bits else ""


def compose(data):
    """The description text the model reads: plain labelled parts (the guide: plain text beats W++/JSON)."""
    data = clean(data)
    if not data:
        return ""
    kind = data["kind"]
    names = labels(kind)
    out = []
    for key, (title, _) in [(k, (t, h)) for k, t, h in SHARED[kind]]:
        s = data["shared"].get(key) or {}
        if s.get("on") and s.get("text"):
            out.append(f"[{title}]\n{s['text']}")
    several = len(data["people"]) > 1 or kind == "simulation"
    for p in data["people"]:
        parts = []
        for key, _, _ in PERSON:
            s = p["sections"].get(key) or {}
            text = s.get("text") or ""
            if key == "temperament" and s.get("on"):
                line = _temper_line(p)
                text = (text + ("\n" + line if text and line else line)) if line else text
            if s.get("on") and text:
                parts.append(f"[{names[key][0]}]\n{text}")
        if not parts:
            continue
        if several:
            head = p["name"] or "Someone"
            out.append(f"## {head}\n" + "\n\n".join(parts))
        else:
            out.extend(parts)
    for e in data["extra"]:
        if e.get("on") and e.get("text"):
            out.append(f"[{e['title']}]\n{e['text']}")
    return "\n\n".join(out).strip()


def tokens(text):
    """About how many tokens (4 characters each, the usual estimate for English)."""
    return (len(text or "") + 3) // 4


def costs(data):
    """{"total": n, "shared": {key: n}, "people": [{key: n}], "extra": [n]}: what each switched-on part costs."""
    data = clean(data)
    if not data:
        return {"total": 0}
    return {"total": tokens(compose(data)),
            "shared": {k: tokens(v["text"]) if v["on"] else 0 for k, v in data["shared"].items()},
            "people": [{k: tokens(v["text"]) if v["on"] else 0 for k, v in p["sections"].items()} for p in data["people"]],
            "extra": [tokens(e["text"]) if e["on"] else 0 for e in data["extra"]]}


# --- Sorting an old card into sections ---------------------------------------------------------------------------

# Headings people use in cards, mapped to our sections (English and Ukrainian; W++ style too)
SYNONYMS = {
    "identity": r"identity|basics?|basic info(rmation)?|overview|summary|about|info|name|character|хто|основне",
    "appearance": r"appearance|looks?|physical( description| traits| features)?|body|clothing|outfit|attire|зовнішність|вигляд|одяг",
    "personality": r"personality|traits?|behaviou?r|mannerisms?|habits?|likes|dislikes|quirks|характер|поведінка",
    "temperament": r"temperament|emotional( profile| triggers)?|triggers|soul|attachment|темперамент",
    "goals": r"goals?|motivations?|desires?|wants|fears|conflicts?|цілі|мотивація|страхи",
    "voice": r"voice|speech( pattern| style)?|dialogue style|how (they|he|she) (talks?|speaks?)|мова|мовлення",
    "background": r"background|backstory|history|past|lore|biography|bio|передісторія|історія|минуле",
    "relationships": r"relationships?|relations|connections|family|with \{\{user\}\}|стосунки",
    "knowledge": r"knowledge|secrets?|skills?|abilities|powers|знання|секрети|навички|вміння",
    "setting": r"setting|world|scenario setting|сеттинг|світ",
}
# A heading: [Title], ## Title, **Title**, "Title:" alone on a line, or "Label: text" (the label short)
HEADINGS = [
    re.compile(r"^\s*\[([^\]\n]{2,60})\]\s*:?\s*$"),
    re.compile(r"^\s*#{1,4}\s*(.{2,60}?)\s*#*\s*:?\s*$"),
    re.compile(r"^\s*\*\*([^*\n]{2,60})\*\*\s*:?\s*$"),
    re.compile(r"^\s*([^\s:\[\]#*][^:\n]{1,38}):\s*$"),
]
LABEL_LINE = re.compile(r"^\s*(?:\*\*)?([A-Za-zА-Яа-яІіЇїЄєҐґ' /&()-]{2,30})(?:\*\*)?\s*:\s*(\S.*)$")
SYNONYMS["personality"] += r"|behaves|behaviou?r|acts|manner|demeanou?r|disposition"
SYNONYMS["voice"] += r"|talks|speaks|speech|dialogue|how (he|she|they) sound"


# Words that name a section even inside a longer heading ("How he behaves under pressure", "Her backstory")
STRONG = {
    "appearance": r"appearance|physical|outfit|clothing|attire|зовнішність|вигляд",
    "personality": r"personality|behaves|behaviou?r|mannerisms?|demeanou?r|характер|поведінка",
    "temperament": r"temperament|triggers|темперамент",
    "goals": r"goals?|motivations?|desires?|ambitions?|цілі|мотивація",
    "voice": r"voice|speech|speaks|talks|мовлення",
    "background": r"backstory|background|biography|передісторія",
    "relationships": r"relationships?|стосунки",
    "knowledge": r"secrets?|knowledge|skills|abilities|секрети|знання",
}


def _which(title):
    t = title.strip().lower().strip("*#[]<>: ")
    for key, pattern in SYNONYMS.items():  # the whole heading is a section's name
        if re.fullmatch(rf"(?:the |his |her |their )?(?:{pattern})", t):
            return key
    for key, pattern in STRONG.items():  # or says it plainly somewhere
        if re.search(rf"(?<!\w)(?:{pattern})(?!\w)", t):
            return key
    return None


def _heading(line):
    """(title, rest of the line) when the line is a heading, else None."""
    for h in HEADINGS:
        m = h.match(line)
        if m:
            return m.group(1), ""
    m = LABEL_LINE.match(line)
    if m and _which(m.group(1)):  # "Appearance: tall, grey eyes" (only a label we know: "Note: ..." is just text)
        return m.group(1), m.group(2)
    return None


def split_by_headings(text):
    """(sections {key: text}, leftover text) from a card with recognisable headings. Every line goes somewhere:
    under the heading it follows, or in the leftover (text before the first heading, unknown headings)."""
    found, leftover, current = {}, [], None
    started = False  # the opening lines, before any heading, introduce the person: identity
    for line in (text or "").splitlines():
        head = _heading(line)
        if head:
            key = _which(head[0])
            started = True
            if key:
                current = key
                if head[1].strip():
                    found.setdefault(key, []).append(head[1].strip())
            else:  # a heading we don't know: its part goes to "More", the heading kept
                current = None
                leftover.append(line)
            continue
        if not started:
            found.setdefault("identity", []).append(line)
        else:
            (found.setdefault(current, []) if current else leftover).append(line)
    sections = {k: "\n".join(v).strip() for k, v in found.items() if "\n".join(v).strip()}
    return sections, "\n".join(leftover).strip()


def from_text(text, name="", kind="character"):
    """A sections record from an old card's description by its headings (no AI). Good enough when at least two
    sections are recognised; the caller asks Bulba otherwise."""
    data = empty(kind, (name,))
    sections, leftover = split_by_headings(text)
    setting = sections.pop("setting", "")
    if kind == "ensemble":
        data["shared"]["setting"]["text"] = setting
    elif setting:
        leftover = (f"[Setting]\n{setting}\n\n" + leftover).strip()
    person = data["people"][0]
    for key, value in sections.items():
        if key in person["sections"]:
            person["sections"][key]["text"] = value
    if leftover:
        data["extra"].append({"title": "More", "text": leftover, "on": True})
    return data, len(sections)


STRUCTURE_PROMPT = """You sort a roleplay character card into sections. You never rewrite, shorten or add: every \
sentence of the card goes, word for word, into exactly one section. Sections for each person: {person_keys}. \
{shared_line}Anything that fits nowhere goes in "more", word for word. Also judge the temperament for each person, \
only from what the card says: "pace" (slow, steady or fast to warm up), "route" (the relationship route the card \
leans to with {{{{user}}}}: {routes}) and "start" (a few words: where their attitude to {{{{user}}}} starts, e.g. \
"cold and suspicious"). Several people described in one card are separate people, each with their own sections.
Answer with JSON only:
{{"kind": "character" | "ensemble" | "simulation", "shared": {{key: text}}, "people": [{{"name": "...", \
"sections": {{key: text}}, "temperament": {{"pace": "...", "route": "...", "start": "..."}}}}], "more": "..."}}"""


def structure_prompt():
    return STRUCTURE_PROMPT.format(
        person_keys=", ".join(f'"{k}" ({t})' for k, t, _ in PERSON),
        shared_line=("For a card about several people, shared parts: " + ", ".join(f'"{k}" ({t})' for k, t, _ in SHARED["ensemble"])
                     + ". For a world or scenario card (a setting that makes its own people, no single main character): "
                     + ", ".join(f'"{k}" ({t})' for k, t, _ in SHARED["simulation"]) + ". "),
        routes=", ".join(ROUTES))


def _words(text):
    return re.findall(r"\w+", (text or "").lower())


def coverage(original, data):
    """How much of the original card's wording made it into the sections (0..1): a check that sorting lost
    nothing important."""
    have = set(_words(compose(data) + " " + " ".join(p["name"] for p in clean(data)["people"])))
    body = []  # the card's own words, not its headings (those become our section names)
    for line in (original or "").splitlines():
        head = _heading(line)
        body.append(head[1] if head else line)
    words = _words("\n".join(body))
    if not words:
        return 1.0
    return sum(1 for w in words if w in have) / len(words)


def from_ai_answer(answer, original, name="", is_mult=False):
    """The model's sorted card as a sections record (anything it dropped goes back into "More")."""
    m = re.search(r"\{.*\}", answer or "", re.S)
    raw = json.loads(m.group(0)) if m else {}
    if not isinstance(raw, dict):
        raw = {}
    kind = raw.get("kind") if raw.get("kind") in KINDS else ("ensemble" if is_mult else "character")
    people = raw.get("people") if isinstance(raw.get("people"), list) else []
    if kind != "simulation" and not people:
        people = [{"name": name}]
    if people and not people[0].get("name"):
        people[0]["name"] = name
    data = clean({"kind": kind, "shared": raw.get("shared") or {}, "people": people,
                  "extra": [{"title": "More", "text": str(raw.get("more") or "")}]})
    if coverage(original, data) < 0.9:  # it lost something: the whole original stays in "More", switched off
        data["extra"].append({"title": "The card as it was", "text": original.strip(), "on": False})
    return data


def structure(user, character):
    """Sort this character's description into sections: by its headings when it has them, else Bulba's model.
    Returns the sections record (not saved)."""
    from mainapp import ai_client
    text = character.description or ""
    second = (character.second_name or "").strip() if getattr(character, "is_mult", False) else ""
    data, recognised = from_text(text, character.name)
    more = sum(len(e["text"]) for e in data["extra"])
    if recognised >= 3 and not second and more <= 0.25 * len(text):  # its own headings did the job
        return data
    if not text.strip():
        return empty("ensemble" if second else "character", (character.name, second) if second else (character.name,))
    answer = ai_client.complete(user, "bulba", [
        {"role": "system", "content": structure_prompt()},
        {"role": "user", "content": f"The card's name: {character.name}" + (f" (and {second})" if second else "")
                                    + f"\n\nThe card:\n{text}"}],
        max_tokens=12000, temperature=0.1, response_format={"type": "json_object"})
    return from_ai_answer(answer, text, character.name, bool(second))


FILL_PROMPT = """You help write a roleplay character card. Fill in only the EMPTY sections listed, from what the \
rest of the card says (and what is well known about the character if they're from a known story). Plain labelled \
prose, concrete behaviour over adjectives, no stock labels ("predator's smile", "cold genius", "heart of gold"), \
no purple prose. About {words} words per section. Answer with JSON only: {{"people": [{{"name": "...", \
"sections": {{key: text}}}}], "shared": {{key: text}}}}"""


def fill_empty(user, data, words=80):
    """Bulba drafts the empty switched-on sections; filled ones stay as they are. Returns the new record."""
    from mainapp import ai_client
    data = clean(data)
    names = labels(data["kind"])
    wanted = {"shared": [k for k, v in data["shared"].items() if v["on"] and not v["text"]],
              "people": [{"name": p["name"], "empty": [k for k, v in p["sections"].items() if v["on"] and not v["text"]]}
                         for p in data["people"]]}
    if not wanted["shared"] and not any(p["empty"] for p in wanted["people"]):
        return data
    asked = []
    if wanted["shared"]:
        asked.append("Shared: " + ", ".join(f'"{k}" ({names[k][0]}: {names[k][1]})' for k in wanted["shared"]))
    for p in wanted["people"]:
        if p["empty"]:
            asked.append(f"{p['name'] or 'The character'}: " + ", ".join(f'"{k}" ({names[k][0]}: {names[k][1]})' for k in p["empty"]))
    answer = ai_client.complete(user, "bulba", [
        {"role": "system", "content": FILL_PROMPT.format(words=words)},
        {"role": "user", "content": f"The card so far:\n{compose(data) or '(nothing yet)'}\n\nFill these:\n" + "\n".join(asked)}],
        max_tokens=8000, temperature=0.6, response_format={"type": "json_object"})
    m = re.search(r"\{.*\}", answer or "", re.S)
    try:
        got = json.loads(m.group(0)) if m else {}
    except ValueError:
        got = {}
    for k in wanted["shared"]:
        text = str((got.get("shared") or {}).get(k) or "").strip()
        if text:
            data["shared"][k]["text"] = text
    by_name = {str(p.get("name") or "").strip().lower(): p for p in (got.get("people") or []) if isinstance(p, dict)}
    for i, p in enumerate(data["people"]):
        g = by_name.get(p["name"].strip().lower()) or ((got.get("people") or [None])[i] if i < len(got.get("people") or []) else None)
        if not isinstance(g, dict):
            continue
        for k in wanted["people"][i]["empty"]:
            text = str((g.get("sections") or {}).get(k) or "").strip()
            if text:
                p["sections"][k]["text"] = text
    return clean(data)


APPEARANCE_PROMPT = """Write the Appearance section of a roleplay character card for {name} from this description \
of their picture. Plain prose, 60 to 120 words: build, face, hair, eyes, skin, what they wear, how they carry \
themselves. Only what the picture shows; no art-style words ("anime", "digital art"), no guessing a name. \
Answer with the section's text only.

The picture: {seen}"""


def appearance_from_picture(user, name, data_url):
    """(appearance text, who looked) from a picture of the character (Bulba's eyes, mainapp/bulba/vision.py)."""
    from mainapp import ai_client
    from mainapp.bulba import vision
    seen, who = vision.describe(user, data_url, f"This is {name}: write how they look, for their card.")
    text = ai_client.complete(user, "bulba", [{"role": "user", "content": APPEARANCE_PROMPT.format(name=name or "the character", seen=seen)}],
                              max_tokens=3000, temperature=0.3)
    return (text or "").strip().strip('"'), who


def apply(character, data):
    """Save the sections on the character, with the description composed from them (and the second name for a
    card with two or more people, so the chat page's two pictures keep working). Returns the description."""
    data = clean(data)
    character.sections = data or {}
    if data:
        character.description = compose(data)
        names = [p["name"] for p in data["people"] if p["name"]]
        if data["kind"] == "ensemble" and len(names) >= 2:
            character.is_mult = True
            character.second_name = names[1]
    return character.description


def temperament_of(character, name=None):
    """{"pace", "route", "start"} for a person on this card (the first one by default), or the defaults."""
    data = clean(getattr(character, "sections", None) or {})
    if data:
        for p in data["people"]:
            if name is None or p["name"].strip().lower() == str(name).strip().lower():
                return dict(p["temperament"])
    return {"pace": "steady", "route": "basic", "start": ""}


def edit(data, edits):
    """Bulba's changes to some sections (propose_card_edit section_edits): a new record. Raises ValueError for a
    section that doesn't exist."""
    import copy
    data = copy.deepcopy(clean(data) or empty())
    names = labels(data["kind"])
    for e in edits if isinstance(edits, list) else []:
        if not isinstance(e, dict):
            continue
        key = str(e.get("section") or "").strip()
        text = str(e.get("text") or "").strip()[:8000]
        person = str(e.get("person") or "").strip()
        on = e.get("on", True) is not False
        if key in data["shared"] and not person:
            data["shared"][key] = {"text": text or data["shared"][key]["text"], "on": on}
            continue
        if key in dict((k, 1) for k, _, _ in PERSON):
            target = None
            if person:
                target = next((p for p in data["people"] if p["name"].strip().lower() == person.lower()), None)
                if target is None and data["kind"] != "character":  # someone new in an ensemble or a world
                    target = clean({"kind": data["kind"], "people": [{"name": person}]})["people"][0]
                    data["people"].append(target)
            elif data["people"]:
                target = data["people"][0]
            if target is None:
                raise ValueError(f"There's no {person or 'person'} on this card.")
            target["sections"][key] = {"text": text or target["sections"][key]["text"], "on": on}
            continue
        mine = next((x for x in data["extra"] if x["title"].strip().lower() == key.lower()), None)
        if mine is not None:
            mine.update({"text": text or mine["text"], "on": on})
        elif text:
            data["extra"].append({"title": key[:80] or "More", "text": text, "on": on})
        else:
            raise ValueError(f"No section “{key}”; use one of: {', '.join(names)}, or a title of their own.")
    return clean(data)


def outline(character):
    """For Bulba: the card's sections at a glance (who, which sections are on, how long), or None for a one-box card."""
    data = clean(getattr(character, "sections", None) or {}) if getattr(character, "sections", None) else None
    if not data:
        return None
    names = labels(data["kind"])
    lines = [f"Kept as sections ({data['kind']}); change them with propose_card_edit section_edits."]
    for k, v in data["shared"].items():
        lines.append(f"- {names[k][0]} ({k}): " + (f"{len(v['text'].split())} words" if v["text"] else "empty") + ("" if v["on"] else ", off"))
    for p in data["people"]:
        t = p["temperament"]
        lines.append(f"{p['name'] or 'The character'} (temperament: {t['pace']}, route {t['route']}"
                     + (f", starts {t['start']}" if t["start"] else "") + "):")
        for k, v in p["sections"].items():
            lines.append(f"  - {names[k][0]} ({k}): " + (f"{len(v['text'].split())} words" if v["text"] else "empty")
                         + ("" if v["on"] else ", off"))
    for x in data["extra"]:
        lines.append(f"- {x['title']} (their own): {len(x['text'].split())} words" + ("" if x["on"] else ", off"))
    return "\n".join(lines)


# A persona (who they are in the story): seven core elements, a fully fledged character
PERSONA = [("pronouns", "Name & pronouns"), ("appearance", "Appearance"), ("background", "Background & lore"),
           ("connection", "Connection to the story"), ("traits", "Core traits"), ("likes", "Likes & dislikes"),
           ("temperament", "Temperament")]
PERSONA_HINTS = {
    "pronouns": "Their name, and how others refer to them (she/he/they...).",
    "appearance": "Build, face, hair, eyes, what they usually wear, how they move.",
    "background": "Where they come from and what shaped them, in this story's world.",
    "connection": "How they're tied to the card's characters (or to its world): history, debts, roles.",
    "traits": "How they behave: what they do, not adjectives.",
    "likes": "What draws them in and what they can't stand.",
    "temperament": "How they act in different situations (danger, flirting, being lied to) and how they change.",
}
PERSONA_QUESTIONS = ["What's your name, and your pronouns?", "How do you look?",
                     "Where do you come from, and what shaped you?",
                     "How are you connected to the character(s), or to this world?",
                     "How do you act around people?", "What do you like, and what can't you stand?",
                     "How do you react when things get tense, flirty or dangerous, and do you change over time?"]
OLD_PERSONA = {"identity": "pronouns", "personality": "traits", "wants": "connection"}  # the five-question keys


def split_persona(text):
    """({key: text}, leftover) from a persona written in our parts ("[Appearance]" headings); anything else is
    the leftover, word for word."""
    titles = {t.lower(): k for k, t in PERSONA} | {"who they are": "pronouns", "personality in action": "traits",
                                                   "voice": "traits", "what they want here": "connection"}
    found, leftover, current = {}, [], None
    for line in (text or "").splitlines():
        m = re.match(r"^\s*\[([^\]\n]{2,40})\]\s*$", line)
        if m and m.group(1).strip().lower() in titles:
            current = titles[m.group(1).strip().lower()]
            continue
        (found.setdefault(current, []) if current else leftover).append(line)
    return {k: "\n".join(v).strip() for k, v in found.items() if "\n".join(v).strip()}, "\n".join(leftover).strip()


def compose_persona(sections):
    """The persona's description from its sections ({key: text}), the same plain labelled way as a card."""
    if not isinstance(sections, dict):
        return ""
    sections = {OLD_PERSONA.get(k, k): v for k, v in sections.items()}
    parts = [f"[{title}]\n{str(sections.get(key) or '').strip()[:3000]}" for key, title in PERSONA
             if str(sections.get(key) or "").strip()]
    return "\n\n".join(parts)
