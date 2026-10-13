"""
Story systems (Lattice-style): rules the app keeps, the model only interprets. Bulba builds them through
conversation (bulba/tune.py: propose_story_systems); they live with the character's tracker settings
(Character.tracker_config["systems"]) and their values with each chat (the chat file's "story").

- **meter**: a slow value such as trust or warmth (min..max). The tracker call says whether the latest scene moved
  it (-1, 0, +1) and why; the app applies at most `step` per update, nothing during a `cooldown` (replies) after a
  change, and lets it drift back toward `baseline` one point per `drift_days` of story time.
- **clock**: story time (day and minutes). The tracker call says how much time passed; nothing else moves it.
- **event**: something that happens when the story clock reaches it (once on a day/time, or every N days); its
  guidance goes into the next reply once.
- **table**: an opt-in weighted list the model can draw from (a tool, like the dice) when its situation comes up.

Only kept scenes count: what an update finds is held as "pending" with the reply it read, and applied when they
reply to that reply. A reply they swipe away or regenerate never moves a meter or the clock.
"""
import random
import re
import uuid

TYPES = ("meter", "clock", "event", "table")
MAX_SYSTEMS = 12
DAY = 24 * 60


def _int(v, default, lo=None, hi=None):
    try:
        v = int(v)
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _minutes(hhmm, default=8 * 60):
    if isinstance(hhmm, int) and not isinstance(hhmm, bool):  # already minutes (a saved config)
        return hhmm % DAY
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", str(hhmm or ""))
    return (int(m.group(1)) % 24) * 60 + int(m.group(2)) % 60 if m else default


def normalize_system(raw):
    if not isinstance(raw, dict) or raw.get("type") not in TYPES:
        return None
    s = {"id": str(raw.get("id") or uuid.uuid4().hex[:8])[:40], "type": raw["type"],
         "label": str(raw.get("label") or raw["type"].capitalize()).strip()[:80]}
    if s["type"] == "meter":
        lo = _int(raw.get("min"), 0)
        hi = _int(raw.get("max"), 10, lo + 1)
        s.update(min=lo, max=hi, start=_int(raw.get("start"), lo, lo, hi),
                 baseline=None if raw.get("baseline") in (None, "") else _int(raw.get("baseline"), lo, lo, hi),
                 step=_int(raw.get("step"), 1, 1, hi - lo), cooldown=_int(raw.get("cooldown"), 2, 0, 50),
                 drift_days=_int(raw.get("drift_days"), 0, 0, 365),
                 about=str(raw.get("about") or "").strip()[:300])
    elif s["type"] == "clock":
        s.update(id="clock", start_day=_int(raw.get("start_day"), 1, 1), start_time=_minutes(raw.get("start_time")))
    elif s["type"] == "event":
        s.update(guidance=str(raw.get("guidance") or "").strip()[:500],
                 at_day=None if raw.get("at_day") in (None, "") else _int(raw.get("at_day"), 1, 1),
                 at_time=_minutes(raw.get("at_time"), None) if raw.get("at_time") not in (None, "") else None,
                 every_days=_int(raw.get("every_days"), 0, 0, 365))
        if not s["guidance"]:
            return None
    elif s["type"] == "table":
        entries = []
        for e in raw.get("entries") or []:
            if isinstance(e, dict) and str(e.get("text") or "").strip():
                entries.append({"text": str(e["text"]).strip()[:200], "weight": _int(e.get("weight"), 1, 1, 1000)})
        if not entries:
            return None
        s.update(entries=entries[:30], when=str(raw.get("when") or "").strip()[:300])
    return s


def normalize_systems(raw):
    out, seen = [], set()
    for r in (raw if isinstance(raw, list) else [])[:MAX_SYSTEMS]:
        s = normalize_system(r)
        if s and s["id"] not in seen:
            out.append(s)
            seen.add(s["id"])
    return out


def systems_of(character):
    return normalize_systems((getattr(character, "tracker_config", None) or {}).get("systems"))


def of_type(systems, kind):
    return [s for s in systems if s["type"] == kind]


def needs_ai(systems):
    """Meters and the clock are read by the tracker call; events and tables need nothing from it."""
    return bool(of_type(systems, "meter") or of_type(systems, "clock"))


# ---------------------------------------------------------------------------
# State (per chat)
# ---------------------------------------------------------------------------

def state_of(raw, systems):
    st = dict(raw) if isinstance(raw, dict) else {}
    values = dict(st.get("values") or {})
    for m in of_type(systems, "meter"):
        values.setdefault(m["id"], m["start"])
        values[m["id"]] = max(m["min"], min(m["max"], _int(values[m["id"]], m["start"])))
    st["values"] = values
    st.setdefault("last_change", {})   # meter id -> reply count when it last moved
    st.setdefault("replies", 0)        # kept replies so far
    clock = of_type(systems, "clock")
    if clock and "minutes" not in st:
        st["minutes"] = (clock[0]["start_day"] - 1) * DAY + clock[0]["start_time"]
    st.setdefault("drifted_at", st.get("minutes", 0))
    st.setdefault("fired", {})         # event id -> how many times it has happened
    st.setdefault("due", [])           # events for the next reply
    st.setdefault("pending", None)
    st.setdefault("log", [])
    return st


def clock_text(minutes):
    day, rest = divmod(int(minutes), DAY)
    return f"Day {day + 1}, {rest // 60:02d}:{rest % 60:02d}"


# ---------------------------------------------------------------------------
# What the tracker call is asked, and what it found (held until the reply is kept)
# ---------------------------------------------------------------------------

def prompt_section(systems, st):
    meters, clock = of_type(systems, "meter"), of_type(systems, "clock")
    if not (meters or clock):
        return ""
    lines = ["Story systems: also include a key \"_story\" in your JSON:",
             "{\"_story\": {\"meters\": {\"<id>\": {\"change\": -1 | 0 | 1, \"why\": \"<a few words>\"}}"
             + (", \"elapsed_minutes\": <story time that passed in these messages>" if clock else "") + "}}"]
    for m in meters:
        lines.append(f"- meter {m['id']} \"{m['label']}\" now {st['values'].get(m['id'])}/{m['max']}"
                     + (f": {m['about']}" if m["about"] else "")
                     + ". Change it only when these messages clearly move it; most scenes don't (0).")
    if clock:
        lines.append(f"- story clock now {clock_text(st['minutes'])}: estimate the time that passed in these messages "
                     "from what happened (a conversation: minutes; a night's sleep: ~480). Never guess from nothing: 0.")
        lines.append("- The World tracker's date and time follow the story clock: leave them out of your update.")
    return "\n".join(lines)


def stage(st, update, kept_at, reply_text):
    """Holds what the tracker call found until the reply it read is kept (`kept_at`: the message count then)."""
    found = update.get("_story") if isinstance(update, dict) else None
    if not isinstance(found, dict):
        return
    meters = {}
    for mid, v in (found.get("meters") or {}).items():
        if isinstance(v, dict) and _int(v.get("change"), 0) != 0:
            meters[str(mid)] = {"change": max(-1, min(1, _int(v.get("change"), 0))), "why": str(v.get("why") or "")[:120]}
    minutes = _int(found.get("elapsed_minutes"), 0, 0, 7 * DAY)
    st["pending"] = {"at": kept_at, "reply": str(reply_text or "")[:200], "meters": meters, "minutes": minutes}


def commit(st, systems, messages):
    """They replied: if the reply the pending changes came from is still the one on screen, apply them."""
    p = st.get("pending")
    st["pending"] = None
    st["replies"] = st.get("replies", 0) + 1
    st["due"] = []  # events reached last time went into the reply they just kept
    if not p:
        return []
    i = p["at"] - 1
    if not (0 <= i < len(messages)) or str(messages[i][2])[:200] != p["reply"]:
        return []  # swiped away, regenerated or deleted: it never happened
    notes = []
    by_id = {m["id"]: m for m in of_type(systems, "meter")}
    for mid, change in p["meters"].items():
        m = by_id.get(mid)
        if not m:
            continue
        since = st["replies"] - st["last_change"].get(mid, -10 ** 6)
        if since <= m["cooldown"]:
            notes.append(f"{m['label']}: held (it moved {since} replies ago)")
            continue
        old = st["values"][mid]
        new = max(m["min"], min(m["max"], old + change["change"] * m["step"]))
        if new != old:
            st["values"][mid] = new
            st["last_change"][mid] = st["replies"]
            notes.append(f"{m['label']}: {old} → {new} ({change['why']})")
    if of_type(systems, "clock") and p["minutes"]:
        before = st["minutes"]
        st["minutes"] = before + p["minutes"]
        _drift(st, systems)
        _events(st, systems, before, st["minutes"])
        notes.append(f"Story time: {clock_text(st['minutes'])}")
    st["log"] = (st["log"] + notes)[-30:]
    return notes


def _drift(st, systems):
    for m in of_type(systems, "meter"):
        if m["baseline"] is None or not m["drift_days"]:
            continue
        steps = (st["minutes"] - st["drifted_at"]) // (m["drift_days"] * DAY)
        v = st["values"][m["id"]]
        for _ in range(int(steps)):
            v += (m["baseline"] > v) - (m["baseline"] < v)
        st["values"][m["id"]] = v
    if any(m["drift_days"] for m in of_type(systems, "meter")):
        shortest = min(m["drift_days"] for m in of_type(systems, "meter") if m["drift_days"]) * DAY
        st["drifted_at"] += ((st["minutes"] - st["drifted_at"]) // shortest) * shortest


def _occurrences(e, upto):
    """How many times event `e` has come due by story minute `upto`."""
    start = ((e["at_day"] or 1) - 1) * DAY + (e["at_time"] if e["at_time"] is not None else 0)
    if upto < start:
        return 0
    return 1 + ((upto - start) // (e["every_days"] * DAY) if e["every_days"] else 0)


def _events(st, systems, before, now):
    for e in of_type(systems, "event"):
        done = st["fired"].get(e["id"], 0)
        due = _occurrences(e, now)
        if due > done and _occurrences(e, before) < due:
            st["due"].append({"label": e["label"], "guidance": e["guidance"]})
        st["fired"][e["id"]] = due


def sync_world(st, systems, tracker_state):
    """With a story clock, the World tracker's date and time show it (unless they locked them)."""
    if not of_type(systems, "clock") or not isinstance(tracker_state, dict):
        return
    world = (tracker_state.setdefault("values", {})).get("world")
    if not isinstance(world, dict):
        return
    locks = tracker_state.get("locks") or []
    day, rest = divmod(int(st["minutes"]), DAY)
    for key, text in (("date", f"Day {day + 1}"), ("time", f"{rest // 60:02d}:{rest % 60:02d}")):
        if f"world.{key}" not in locks:
            world[key] = text


def upcoming(systems, st, n=3):
    """The next events on the story clock: [{"label", "when"}], soonest first."""
    if not of_type(systems, "clock"):
        return []
    now, out = st.get("minutes", 0), []
    for e in of_type(systems, "event"):
        start = ((e["at_day"] or 1) - 1) * DAY + (e["at_time"] if e["at_time"] is not None else 0)
        nxt = start if now < start else (
            start + (((now - start) // (e["every_days"] * DAY)) + 1) * e["every_days"] * DAY if e["every_days"] else None)
        if nxt is not None:
            out.append((nxt, {"label": e["label"], "when": clock_text(nxt)}))
    return [o for _, o in sorted(out, key=lambda x: x[0])][:n]


def format_for_prompt(systems, st):
    """What the next reply is told: meters, story time, events happening now (the latter once)."""
    lines = []
    for m in of_type(systems, "meter"):
        lines.append(f"{m['label']}: {st['values'].get(m['id'])}/{m['max']} (changes slowly; let behaviour reflect "
                     "the current level, not where it could go)")
    if of_type(systems, "clock"):
        lines.append(f"Story time: {clock_text(st['minutes'])}")
    for d in st.get("due") or []:
        lines.append(f"Happening now ({d['label']}): {d['guidance']}")
    return ("Story systems:\n" + "\n".join(lines)) if lines else ""


KEPT = ("values", "last_change", "replies", "minutes", "drifted_at", "fired", "due")


def snapshot(st, count):
    """Remember the state as it is once the chat has `count` messages (deleting messages rewinds to it)."""
    snap = {k: st[k] for k in KEPT if k in st}
    history = [h for h in st.get("history") or [] if h.get("at", 0) < count]
    st["history"] = (history + [{"at": count, "state": json_copy(snap)}])[-40:]


def rewind(st, count):
    """Messages from `count` on were deleted: back to the newest state that was true before them."""
    history = [h for h in st.get("history") or [] if h.get("at", 0) <= count]
    fresh = {k: v for k, v in st.items() if k not in KEPT}
    fresh.update(json_copy(history[-1]["state"]) if history else {})
    fresh["history"], fresh["pending"] = history, None
    if not history:
        for k in KEPT:
            fresh.pop(k, None)
    return fresh


def json_copy(v):
    import json
    return json.loads(json.dumps(v))


# ---------------------------------------------------------------------------
# Tables (a tool the chat model can call, like the dice)
# ---------------------------------------------------------------------------

TABLE_RULES = ("Random tables (kept by the app): when a situation one of the story's tables is for comes up, call "
               "draw_from_table and build on what it gives you; don't draw for anything else, and never make up a draw.")


def table_tool(systems):
    tables = of_type(systems, "table")
    if not tables:
        return None
    return {"type": "function", "function": {
        "name": "draw_from_table",
        "description": "Draw from one of the story's weighted tables when its situation comes up (see each one's "
                       "'when'); the app picks the result, you narrate it. " + "; ".join(
                           f"{t['id']}: {t['label']}" + (f" (when: {t['when']})" if t["when"] else "") for t in tables),
        "parameters": {"type": "object", "properties": {"table": {"type": "string", "enum": [t["id"] for t in tables]}},
                       "required": ["table"]}}}


def draw(systems, table_id, rng=None):
    t = next((t for t in of_type(systems, "table") if t["id"] == table_id), None)
    if t is None:
        return None
    rng = rng or random
    pick = rng.choices(t["entries"], weights=[e["weight"] for e in t["entries"]], k=1)[0]
    return {"table": t["label"], "result": pick["text"]}


def describe(system):
    """One line for a proposal card or the panel."""
    s = system
    if s["type"] == "meter":
        extra = [f"starts at {s['start']}", f"moves at most {s['step']} at a time"]
        if s["cooldown"]:
            extra.append(f"then holds for {s['cooldown']} replies")
        if s["baseline"] is not None and s["drift_days"]:
            extra.append(f"drifts back toward {s['baseline']} every {s['drift_days']} story day(s)")
        return f"{s['label']} ({s['min']}–{s['max']}): " + ", ".join(extra) + (f". Moves when: {s['about']}" if s["about"] else "")
    if s["type"] == "clock":
        return f"Story clock from {clock_text((s['start_day'] - 1) * DAY + s['start_time'])}; only story time moves it"
    if s["type"] == "event":
        when = (f"day {s['at_day']}" if s["at_day"] else "from the start") + (
            f" at {s['at_time'] // 60:02d}:{s['at_time'] % 60:02d}" if s["at_time"] is not None else "")
        return f"{s['label']}: {when}" + (f", every {s['every_days']} day(s)" if s["every_days"] else ", once") + f" — {s['guidance']}"
    total = sum(e["weight"] for e in s["entries"])
    return f"{s['label']} (drawn when: {s['when'] or 'the model decides'}): " + "; ".join(
        f"{e['text']} {round(100 * e['weight'] / total)}%" for e in s["entries"])
