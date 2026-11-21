"""
Story memory: what happened, who knows what, who everyone is, and where each relationship stands. One of the two
summary modes of a chat (the other is the manual summary, mainapp/views.py _summarize_pieces); new chats start
with it.

- **Milestones**, one per scene. Every few messages (4 by default: the "memory" task's interval, Connections or
  Bulba) one call on the background model reads the new messages and either extends the open scene's milestone
  or closes it and opens the next. A milestone is written for a reader who never saw the chat: everyone and
  everything is introduced with who or what they are ("Ivan, Dottore's new guard on the third sublevel"), small
  details the story may come back to stay, and it says who did, said, learned or misunderstood what.
- **Arcs**: once there are many closed milestones, the oldest roll up into an arc of a few sentences.
- **Facts** with who knows them, who believes something else, and who they're hidden from.
- **People and places**: every named person, place and important thing, with one line on who or what it is.
- **Relationships**, one per ordered pair (how A sees B): a route (basic, romance, enemies...), a stage on it,
  trust / warmth / tension, and a short history of what changed it. A character's card temperament sets where it
  starts and how fast it moves (mainapp/card_sections.py); a stage moves at most one step per milestone.

All of it is kept in the chat file under "memory" and given to the model in the summary slot of the preset, as
one block that changes only when memory updates (so the start of the prompt stays cacheable).
"""
import json
import re
import uuid

from mainapp import ai_client, card_sections, html_objects, samplers

DEFAULT_EVERY = 4
MAX_SCENE = 24          # messages: an open milestone longer than this is closed whatever the model says
ARC_AFTER = 14          # closed milestones before the oldest ones roll into an arc
ARC_SIZE = 8            # milestones per arc
CATCH_UP_CHUNK = 16     # messages per call when building memory for an older chat
BUDGET = 3000           # tokens for the memory block in the prompt
DIMS = ("trust", "warmth", "tension")
PACE_STEP = {"fast": 1, "steady": 2, "slow": 3}  # points of change it takes to move a stage


def empty():
    return {"version": 1, "upto": 0, "milestones": [], "arcs": [], "facts": [], "people": [], "relationships": []}


def clean(data):
    """A well-formed memory record from whatever was saved."""
    out = empty()
    if not isinstance(data, dict):
        return out
    out["upto"] = int(data.get("upto") or 0) if str(data.get("upto") or "0").isdigit() else 0
    for key in ("milestones", "arcs", "facts", "people", "relationships"):
        if isinstance(data.get(key), list):
            out[key] = [x for x in data[key] if isinstance(x, dict)]
    return out


# --- Settings: the mode is per chat; how often, per user (the "memory" task) ---

def mode_of(chat_data, message_count=None):
    """'memory' or 'manual' for this chat. Chats from before memory (a summary, or a long history) stay manual
    until they switch; new chats start with memory."""
    mode = chat_data.get("summary_mode") if isinstance(chat_data, dict) else None
    if mode in ("memory", "manual"):
        return mode
    count = message_count if message_count is not None else len(chat_data.get("messages") or [])
    if chat_data.get("summary_parts") or chat_data.get("summary") or count > 3:
        return "manual"
    return "memory"


def chat_mode(user, chat_data, message_count=None):
    """The mode a chat uses: its own choice, else memory for a new chat (unless they turned story memory off for
    new chats), manual for one from before."""
    data = chat_data if isinstance(chat_data, dict) else {}
    if data.get("summary_mode") in ("memory", "manual"):
        return data["summary_mode"]
    if not ai_client.get_task_setting(user, "memory").enabled:
        return "manual"
    return mode_of(data, message_count)


def story_text(user, chat_data, summary_text, message_count=None):
    """What the model reads in the preset's summary slot: story memory, or the manual summary."""
    if chat_mode(user, chat_data, message_count) == "memory":
        return prompt_text((chat_data or {}).get("memory")) or summary_text
    return summary_text


def every(user):
    setting = ai_client.get_task_setting(user, "memory")
    return max(1, min(100, setting.interval or DEFAULT_EVERY))


def automatic(user):
    setting = ai_client.get_task_setting(user, "memory")
    return setting.enabled and setting.mode == setting.MODE_AUTO


def due(user, memory, message_count):
    """Should memory update now (enough new messages since it last did)?"""
    return automatic(user) and message_count - clean(memory)["upto"] >= every(user)


def trim_to(memory, message_count):
    """Messages were deleted: memory keeps only what still exists (milestones past the end go; facts and changes
    from them go too)."""
    memory = clean(memory)
    if memory["upto"] <= message_count:
        return memory
    gone = {m["id"] for m in memory["milestones"] if m.get("from", 0) >= message_count}
    memory["milestones"] = [m for m in memory["milestones"] if m["id"] not in gone]
    for m in memory["milestones"]:
        if m.get("to", 0) > message_count:
            m["to"], m["stale"] = message_count, True
    memory["facts"] = [f for f in memory["facts"] if f.get("source") not in gone]
    # an arc that told any of the gone scenes would still tell them: it goes, its other scenes show on their own
    broken = {a["id"] for a in memory["arcs"] if gone & set(a.get("milestones") or [])}
    memory["arcs"] = [a for a in memory["arcs"] if a["id"] not in broken]
    for m in memory["milestones"]:
        if m.get("arc") in broken:
            m.pop("arc", None)
    for r in memory["relationships"]:
        r["history"] = [h for h in r.get("history", []) if h.get("m") not in gone]
    memory["upto"] = message_count
    return memory


def milestone_count(memory, message_count=None):
    """How many milestones there are (that start before message_count, when given)."""
    ms = clean(memory)["milestones"]
    return len([m for m in ms if message_count is None or m.get("from", 0) < message_count])


def linked_text(memory):
    """Another chat's memory, for a chat that remembers it (🔗): the same block its own replies read."""
    text = prompt_text(memory)
    return text.split("\n", 1)[1] if text.startswith("[Story memory]") else text


def mark_stale(memory, index):
    """A message they edited or swiped: the milestone that covers it is marked to be looked at again."""
    memory = clean(memory)
    for m in memory["milestones"]:
        if m.get("from", 0) <= index < m.get("to", 0):
            m["stale"] = True
    return memory


# --- The call ---

PROMPT = """You keep the memory of a long roleplay story so that a reader who has never seen the chat can follow \
it. Read what memory already holds, then the new messages, and answer with JSON only.

How to write a milestone (the most important part):
1. Introduce every person, place and thing on first mention with who or what they are. Not "they meet Ivan" \
but "they meet Ivan, Dottore's new guard on the third sublevel". Use the people list below for people already \
known, and still say in a few words who they are.
2. Keep the small details the story may come back to: names, numbers, dates, promises, deals, objects handed \
over, wounds, deadlines, lies, things said that someone will remember. Quote the words that matter.
3. Say who did each thing, who said it, who learned or revealed something, who decided, who believed or \
misunderstood what.
4. Plain past tense. No interpretation, no mood words ("tension rises", "a moment of connection"), nothing \
invented, nothing about the writing. Short where little happened.
5. {user} is the person the user plays. {char_line}

Scenes: if the new messages carry on the scene of the open milestone (same place and time, same situation), \
set "continues": true and rewrite that milestone to cover all of it. If the scene changed (a new place, time \
skip, a new situation), "continues": false: the open milestone is closed as it is and you write the new one. \
New messages may also hold both: then "continues": false and write the new scene only; put anything that \
finished the old scene in "close_with" (one or two sentences added to the old milestone).

Also:
- "facts": new facts that matter later (secrets, revelations, decisions, lies, what was promised). For each: \
who knows it (was there, was told), who believes something else (and what), who it's kept from. Only people \
in the people list or new ones you add.
- "people": every person, place or important thing that appeared and isn't in the list yet, or whose role \
changed: name, kind (person, place, thing, group) and one line on who or what it is now.
- "relationships": changes in how one person sees another, from what actually happened in these messages (not \
from mood): from, to, "step" (+1 closer along their route, -1 further, 0 no stage change), changes to trust, \
warmth and tension (-2 to +2 each), "why" (one line, what happened), and "route" only if the relationship \
clearly turned into another kind ({routes}). Leave it empty when nothing changed.

Answer:
{{"continues": true|false, "close_with": "", "title": "a few words", "where": "", "when": "", \
"who": ["names present"], "summary": "the milestone", "turning_points": [{{"who": "", "said_or_did": "close to \
word for word", "reactions": "how each person present took it"}}], "keywords": [""], "facts": [{{"fact": "", \
"known_by": [""], "believed_by": [{{"who": "", "belief": ""}}], "hidden_from": [""]}}], "people": [{{"name": "", \
"kind": "person", "identity": ""}}], "relationships": [{{"from": "", "to": "", "step": 0, "trust": 0, \
"warmth": 0, "tension": 0, "why": "", "route": ""}}]}}"""


def _line(message, names):
    who = names["user"] if message[0] == "user" else (names["char"] if message[0] == "assistant" else "Note")
    return f"{who}: {html_objects.shrink(message[2])}"


def known_text(memory, open_only=False):
    """What memory already holds, for the update call."""
    memory = clean(memory)
    parts = []
    if memory["people"]:
        parts.append("People, places and things:\n" + "\n".join(f"- {p['name']} ({p.get('kind', 'person')}): {p.get('identity', '')}"
                                                                for p in memory["people"][-60:]))
    if memory["relationships"]:
        parts.append("Relationships:\n" + "\n".join(_rel_line(r) for r in memory["relationships"][-30:]))
    closed = [m for m in memory["milestones"] if not m.get("open")][-2:]
    if closed:
        parts.append("The milestones just before:\n" + "\n\n".join(f"{m.get('title', '')}: {m.get('summary', '')}" for m in closed))
    open_m = next((m for m in memory["milestones"] if m.get("open")), None)
    parts.append("The open milestone (the current scene):\n" + (f"{open_m.get('title', '')}: {open_m.get('summary', '')}"
                                                                 if open_m else "(none yet: this is the first)"))
    return "\n\n".join(parts)


def _parse(answer):
    m = re.search(r"\{.*\}", answer or "", re.S)
    if not m:
        raise ai_client.AIError("Story memory: the answer had no JSON. It'll try again next time.")
    try:
        data = json.loads(m.group(0))
    except ValueError:
        raise ai_client.AIError("Story memory: the answer wasn't readable. It'll try again next time.")
    return data if isinstance(data, dict) else {}


def _people_names(memory):
    return {p["name"].strip().lower(): p for p in memory["people"] if p.get("name")}


def _rel_line(r):
    route = card_sections.ROUTES.get(r.get("route"), ("Basic", []))[0]
    dims = ", ".join(f"{d} {r.get(d, 5)}/10" for d in DIMS)
    last = (r.get("history") or [{}])[-1].get("why", "")
    return f"- {r['from']} → {r['to']}: {r.get('stage', 'stranger')} ({route} route; {dims})" + (f". Last change: {last}" if last else "")


def _relationship(memory, a, b, character=None):
    """The record for how a sees b (made the first time, from a's card temperament when a is on the card)."""
    for r in memory["relationships"]:
        if r["from"].lower() == a.lower() and r["to"].lower() == b.lower():
            return r
    temper = card_sections.temperament_of(character, a) if character is not None and _on_card(character, a) else \
        {"pace": "steady", "route": "basic", "start": ""}
    route = temper["route"] if temper["route"] in card_sections.ROUTES else "basic"
    r = {"from": a, "to": b, "route": route, "stage": card_sections.ROUTES[route][1][0], "points": 0,
         "pace": temper["pace"], "start": temper["start"], "trust": 5, "warmth": 5, "tension": 3, "history": []}
    if route in ("enemies", "rivals"):
        r.update({"trust": 3, "warmth": 3, "tension": 6})
    memory["relationships"].append(r)
    return r


def _on_card(character, name):
    if not name:
        return False
    names = {character.name.strip().lower()}
    data = card_sections.clean(character.sections) if getattr(character, "sections", None) else None
    if data:
        names |= {p["name"].strip().lower() for p in data["people"] if p["name"]}
    return name.strip().lower() in names


def _apply_relationship(memory, change, milestone_id, character=None):
    a, b = str(change.get("from") or "").strip()[:80], str(change.get("to") or "").strip()[:80]
    if not a or not b or a.lower() == b.lower():
        return
    r = _relationship(memory, a, b, character)
    route = str(change.get("route") or "").strip()
    if route in card_sections.ROUTES and route != r["route"]:  # it turned into another kind of relationship
        r["route"] = route
        ladder = card_sections.ROUTES[route][1]
        r["stage"] = ladder[min(1, len(ladder) - 1)]
        r["points"] = 0
    for d in DIMS:
        try:
            delta = max(-2, min(2, int(change.get(d) or 0)))
        except (TypeError, ValueError):
            delta = 0
        r[d] = max(0, min(10, int(r.get(d, 5)) + delta))
    try:
        step = max(-1, min(1, int(change.get("step") or 0)))
    except (TypeError, ValueError):
        step = 0
    moved = ""
    if step:
        # The card's pace: how many points of change move a stage; and never more than a step per milestone
        r["points"] = int(r.get("points", 0)) + step
        need = PACE_STEP.get(r.get("pace"), 2)
        if abs(r["points"]) >= need and r.get("stepped_at") != milestone_id:
            ladder = card_sections.ROUTES.get(r["route"], card_sections.ROUTES["basic"])[1]
            i = ladder.index(r["stage"]) if r["stage"] in ladder else 0
            j = max(0, min(len(ladder) - 1, i + (1 if r["points"] > 0 else -1)))
            if j != i:
                moved = f"{r['stage']} → {ladder[j]}"
                r["stage"], r["stepped_at"] = ladder[j], milestone_id
            r["points"] = 0
    why = str(change.get("why") or "").strip()[:300]
    if why or moved:
        r["history"] = (r.get("history") or [])[-11:] + [{"m": milestone_id, "why": why, "moved": moved}]


def update(user, character, memory, messages, names, upto=None, chunk=None):
    """Read the messages memory hasn't covered yet (up to `upto`, at most `chunk` of them) and fold them in.
    Returns the new memory. Raises ai_client.AIError."""
    memory = trim_to(memory, len(messages))
    start = memory["upto"]
    stop = min(len(messages), upto if upto is not None else len(messages))
    if chunk:
        stop = min(stop, start + chunk)
    if stop <= start:
        return memory
    window = samplers.job_window(user, "memory")
    known = known_text(memory)
    room = max(1500, window - samplers.approx_tokens(known) - 1500)
    lines = [_line(m, names) for m in messages[start:stop] if m[0] in ("user", "assistant", "system")]
    text = samplers.cut_to("\n\n".join(lines), room, keep="end")
    routes = ", ".join(card_sections.ROUTES)
    char_line = (f"The main character is {names['char']}." if names.get("char") else "")
    prompt = PROMPT.format(user=names["user"], char_line=char_line, routes=routes)
    answer = ai_client.complete(user, "memory", [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"What memory holds now:\n\n{known}\n\nThe new messages (numbers {start + 1} to {stop}):\n\n{text}"}],
        temperature=0.2, max_tokens=6000, response_format={"type": "json_object"})
    data = _parse(answer)
    return fold(memory, data, start, stop, character)


def fold(memory, data, start, stop, character=None):
    """Put one answer into memory (separate from the call, for tests and catch-up)."""
    memory = clean(memory)
    open_m = next((m for m in memory["milestones"] if m.get("open")), None)
    summary = str(data.get("summary") or "").strip()[:6000]
    continues = bool(data.get("continues")) and open_m is not None and (stop - open_m.get("from", start)) <= MAX_SCENE
    if open_m is not None and not continues:
        close = str(data.get("close_with") or "").strip()
        if close:
            open_m["summary"] = (open_m.get("summary", "") + " " + close).strip()
        open_m["open"] = False
        open_m["to"] = start
    fields = {
        "title": str(data.get("title") or "").strip()[:120] or "A scene",
        "where": str(data.get("where") or "").strip()[:160],
        "when": str(data.get("when") or "").strip()[:120],
        "who": [str(w).strip()[:80] for w in (data.get("who") or []) if str(w).strip()][:12],
        "turning_points": [{k: str(t.get(k) or "").strip()[:600] for k in ("who", "said_or_did", "reactions")}
                           for t in (data.get("turning_points") or []) if isinstance(t, dict)][:6],
        "keywords": [str(k).strip()[:40] for k in (data.get("keywords") or []) if str(k).strip()][:12],
    }
    if continues:
        open_m.update(fields)
        if summary:
            open_m["summary"] = summary
        open_m["to"], open_m["stale"] = stop, False
        mid = open_m["id"]
    else:
        mid = uuid.uuid4().hex[:10]
        memory["milestones"].append({"id": mid, "from": start, "to": stop, "open": True, "summary": summary, **fields})

    people = _people_names(memory)
    for p in data.get("people") or []:
        if not isinstance(p, dict) or not str(p.get("name") or "").strip():
            continue
        name = str(p["name"]).strip()[:80]
        identity = str(p.get("identity") or "").strip()[:300]
        kind = p.get("kind") if p.get("kind") in ("person", "place", "thing", "group") else "person"
        if name.lower() in people:
            if identity:
                people[name.lower()].update({"identity": identity, "updated": mid})
        else:
            entry = {"name": name, "kind": kind, "identity": identity, "first": mid, "updated": mid}
            memory["people"].append(entry)
            people[name.lower()] = entry

    for f in data.get("facts") or []:
        if not isinstance(f, dict) or not str(f.get("fact") or "").strip():
            continue
        names_of = lambda key: [str(x).strip()[:80] for x in (f.get(key) or []) if str(x).strip()][:12]
        memory["facts"].append({
            "id": uuid.uuid4().hex[:10], "text": str(f["fact"]).strip()[:500], "known_by": names_of("known_by"),
            "believed_by": [{"who": str(b.get("who") or "").strip()[:80], "belief": str(b.get("belief") or "").strip()[:300]}
                            for b in (f.get("believed_by") or []) if isinstance(b, dict) and b.get("who")][:8],
            "hidden_from": names_of("hidden_from"), "source": mid})
    memory["facts"] = memory["facts"][-120:]

    for change in data.get("relationships") or []:
        if isinstance(change, dict):
            _apply_relationship(memory, change, mid, character)

    memory["upto"] = max(memory["upto"], stop)
    return memory


ARC_PROMPT = """Write one paragraph (4 to 8 sentences) that tells what happened in these milestones of a story, \
for a reader who never saw them: introduce everyone with who they are, keep the details that still matter \
(promises, secrets, objects, wounds, who knows what), say who did what. Plain past tense, nothing invented. \
Answer with the paragraph only."""


def roll_arcs(user, memory):
    """Old closed milestones into an arc (one call), when there are many. Returns the memory."""
    memory = clean(memory)
    loose = [m for m in memory["milestones"] if not m.get("open") and not m.get("arc")]
    if len(loose) < ARC_AFTER:
        return memory
    batch = loose[:ARC_SIZE]
    text = "\n\n".join(f"{m.get('title', '')} ({m.get('where', '')}, {m.get('when', '')}): {m.get('summary', '')}" for m in batch)
    answer = ai_client.complete(user, "memory", [{"role": "system", "content": ARC_PROMPT}, {"role": "user", "content": text}],
                                temperature=0.2, max_tokens=2000)
    answer = (answer or "").strip()
    if not answer:
        return memory
    arc_id = uuid.uuid4().hex[:10]
    memory["arcs"].append({"id": arc_id, "text": answer, "from": batch[0].get("from", 0), "to": batch[-1].get("to", 0),
                           "milestones": [m["id"] for m in batch]})
    for m in batch:
        m["arc"] = arc_id
    return memory


# --- What the model reads ---

def present(memory):
    """Who is in the current scene (the open milestone's people), else everyone in the last one."""
    memory = clean(memory)
    last = next((m for m in reversed(memory["milestones"]) if m.get("who")), None)
    return [w for w in (last or {}).get("who", [])]


def prompt_text(memory, budget=BUDGET):
    """The memory block for the prompt (the preset's summary slot)."""
    memory = clean(memory)
    if not memory["milestones"] and not memory["arcs"]:
        return ""
    here = {w.lower() for w in present(memory)}
    loose = [m for m in memory["milestones"] if not m.get("arc")]
    sections = []
    story = []
    for a in memory["arcs"]:
        story.append(f"Earlier: {a['text']}")
    for m in loose:
        place = ", ".join(x for x in (m.get("where"), m.get("when")) if x)
        story.append(f"{m.get('title', 'A scene')}" + (f" ({place})" if place else "") + f": {m.get('summary', '')}"
                     + (" [still going]" if m.get("open") else ""))
    sections.append(["Story so far (what already happened, oldest first; the chat's older messages may be gone):", story])
    who = [f"{p['name']}: {p.get('identity', '')}" for p in memory["people"] if p.get("identity")]
    if who:
        sections.append(["Who and what is who (as of now):", who])
    rels = [r for r in memory["relationships"] if not here or r["from"].lower() in here or r["to"].lower() in here]
    if rels:
        lines = []
        for r in rels:
            ladder = card_sections.ROUTES.get(r.get("route"), card_sections.ROUTES["basic"])
            lines.append(f"{r['from']} toward {r['to']}: {r.get('stage')} (route: {ladder[0].lower()}; "
                         f"trust {r.get('trust')}/10, warmth {r.get('warmth')}/10, tension {r.get('tension')}/10)"
                         + (f"; last: {r['history'][-1]['why']}" if r.get("history") and r["history"][-1].get("why") else ""))
        sections.append(["Where things stand (play it from here: change comes from what happens in scenes, a step at a time):", lines])
    facts = []
    for f in memory["facts"]:
        bits = [f["text"]]
        if f.get("known_by"):
            bits.append("known to " + ", ".join(f["known_by"]))
        if f.get("hidden_from"):
            bits.append("NOT known to " + ", ".join(f["hidden_from"]))
        for b in f.get("believed_by") or []:
            bits.append(f"{b['who']} believes instead: {b['belief']}")
        facts.append("; ".join(bits))
    if facts:
        sections.append(["Who knows what (characters act only on what they know; the narrator knows it all):", facts])

    def render(secs):
        return "\n\n".join(head + "\n" + "\n".join(f"- {x}" for x in items) for head, items in secs if items)

    text = render(sections)
    # Over budget: the oldest milestones go down to their titles, then the oldest facts go
    while samplers.approx_tokens(text) > budget:
        story_items = sections[0][1]
        long_i = next((i for i, s in enumerate(story_items) if not s.startswith("Earlier:") and ": " in s
                       and len(s) > 140 and i < len(story_items) - 3), None)
        if long_i is not None:
            story_items[long_i] = story_items[long_i].split(": ", 1)[0] + " (details dropped for room)"
        elif facts and len(facts) > 5:
            facts.pop(0)
        else:
            break
        text = render(sections)
    return "[Story memory]\n" + text


def page_payload(memory, user=None, mode="memory"):
    """What the Summary panel's Story memory tab shows."""
    memory = clean(memory)
    out = {"mode": mode, "memory": memory, "tokens": samplers.approx_tokens(prompt_text(memory)),
           "routes": {k: {"title": v[0], "stages": v[1]} for k, v in card_sections.ROUTES.items()}}
    if user is not None:
        out.update({"every": every(user), "automatic": automatic(user)})
    return out


def edit(memory, data):
    """Their changes from the panel: one item edited or removed. Returns the memory."""
    memory = clean(memory)
    kind, item_id = data.get("kind"), data.get("id")
    if kind == "milestone":
        m = next((x for x in memory["milestones"] if x["id"] == item_id), None)
        if m is None:
            raise ValueError("That milestone is gone.")
        if data.get("delete"):
            memory["milestones"].remove(m)
        else:
            m.update({"summary": str(data.get("summary", m.get("summary", ""))).strip()[:6000],
                      "title": str(data.get("title", m.get("title", ""))).strip()[:120] or m.get("title", ""), "stale": False})
    elif kind == "person":
        i = int(item_id)
        if not 0 <= i < len(memory["people"]):
            raise ValueError("No such entry.")
        if data.get("delete"):
            memory["people"].pop(i)
        else:
            memory["people"][i].update({"name": str(data.get("name", memory["people"][i]["name"])).strip()[:80],
                                        "identity": str(data.get("identity", memory["people"][i].get("identity", ""))).strip()[:300]})
    elif kind == "fact":
        f = next((x for x in memory["facts"] if x["id"] == item_id), None)
        if f is None:
            raise ValueError("That fact is gone.")
        if data.get("delete"):
            memory["facts"].remove(f)
        else:
            f["text"] = str(data.get("text", f["text"])).strip()[:500]
            for key in ("known_by", "hidden_from"):
                if isinstance(data.get(key), str):
                    f[key] = [x.strip()[:80] for x in data[key].split(",") if x.strip()][:12]
    elif kind == "relationship":
        i = int(item_id)
        if not 0 <= i < len(memory["relationships"]):
            raise ValueError("No such relationship.")
        r = memory["relationships"][i]
        if data.get("delete"):
            memory["relationships"].pop(i)
        else:
            if data.get("route") in card_sections.ROUTES:
                r["route"] = data["route"]
            ladder = card_sections.ROUTES[r["route"]][1]
            if data.get("stage") in ladder:
                r["stage"] = data["stage"]
            elif r["stage"] not in ladder:
                r["stage"] = ladder[0]
            for d in DIMS:
                if d in data:
                    r[d] = max(0, min(10, int(data[d])))
    elif kind == "arc":
        a = next((x for x in memory["arcs"] if x["id"] == item_id), None)
        if a is None:
            raise ValueError("That arc is gone.")
        if data.get("delete"):  # its milestones come back as they were
            memory["arcs"].remove(a)
            for m in memory["milestones"]:
                if m.get("arc") == a["id"]:
                    m.pop("arc", None)
        else:
            a["text"] = str(data.get("text", a["text"])).strip()[:4000]
    else:
        raise ValueError("Unknown kind.")
    return memory


def redo_milestone(user, memory, messages, names, milestone_id):
    """Write one milestone again from its messages (a stale one, or one they want redone): its text only; the
    facts and relationship changes it made stay."""
    memory = clean(memory)
    m = next((x for x in memory["milestones"] if x["id"] == milestone_id), None)
    if m is None:
        raise ValueError("That milestone is gone.")
    part = messages[m.get("from", 0):m.get("to", 0)]
    if not part:
        raise ValueError("Its messages are gone.")
    scratch = clean({"people": memory["people"], "relationships": memory["relationships"],
                     "milestones": [x for x in memory["milestones"] if x.get("to", 0) <= m.get("from", 0)][-2:]})
    for x in scratch["milestones"]:
        x["open"] = False
    known = known_text(scratch)
    prompt = PROMPT.format(user=names["user"], char_line=f"The main character is {names['char']}.", routes=", ".join(card_sections.ROUTES))
    text = samplers.cut_to("\n\n".join(_line(x, names) for x in part), max(1500, samplers.job_window(user, "memory") - 3000), keep="end")
    data = _parse(ai_client.complete(user, "memory", [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"What memory holds now:\n\n{known}\n\nThe messages of this scene:\n\n{text}\n\n"
                                    "(Write this scene's milestone; continues is false. Facts, people and relationships may be left empty.)"}],
        temperature=0.2, max_tokens=4000, response_format={"type": "json_object"}))
    if str(data.get("summary") or "").strip():
        m["summary"] = str(data["summary"]).strip()[:6000]
        m["title"] = str(data.get("title") or m.get("title", "")).strip()[:120]
        m["stale"] = False
    return memory


def knowledge_for_watch(memory):
    """For Bulba Watch: the secrets and who mustn't know them, so a reply where someone acts on what they can't
    know is caught ("" when there are none)."""
    lines = [f"- {f['text']} (NOT known to {', '.join(f['hidden_from'])})" for f in clean(memory)["facts"] if f.get("hidden_from")]
    return "\n".join(lines[-20:])
