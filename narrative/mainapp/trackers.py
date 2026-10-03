"""
Story trackers (Marinara-style): a separate, cheap AI call keeps structured
story state up to date after replies, instead of the main model writing it
into its reply.

- The registry (TRACKERS) defines each tracker's fields.
- Per-character config (Character.tracker_config) says which trackers are on,
  which go into the main prompt, the custom tracker's fields and the layout.
- Per-chat state (chat file, "trackers" key) holds the values and locks.
  Locked fields are never changed by the AI.

Two tracker kinds:
- "object": one record with fixed fields (World, Custom)
- "list": several records, identified by their key field (Characters, Stats...)
"""
import json
import re

PANELS = [
    {"id": "scene", "label": "Scene", "icon": "🌍"},
    {"id": "characters", "label": "Characters", "icon": "🎭"},
    {"id": "you", "label": "You", "icon": "🧍"},
    {"id": "custom", "label": "Custom", "icon": "🧩"},
]


def _f(key, label, type="text", hint="", **extra):
    return {"key": key, "label": label, "type": type, "hint": hint, **extra}


TRACKERS = [
    # --- Scene ---
    {"id": "world", "panel": "scene", "kind": "object", "icon": "📍", "label": "World",
     "help": "Where and when the story is: location, date, time, weather, who is present.",
     "fields": [_f("location", "Location"), _f("date", "Date"), _f("time", "Time"),
                _f("weather", "Weather"), _f("temperature", "Temperature"),
                _f("present", "Present", "list", "names of everyone in the scene")]},
    {"id": "events", "panel": "scene", "kind": "list", "key": "title", "icon": "🧵", "label": "Plot threads",
     "help": "Set-ups, promises and dangers that have not paid off yet.",
     "fields": [_f("title", "Thread"), _f("status", "Status", hint="brewing / imminent / resolved"),
                _f("detail", "Detail")]},
    {"id": "quests", "panel": "scene", "kind": "list", "key": "title", "icon": "🗺️", "label": "Quests",
     "help": "Goals with a current objective.",
     "fields": [_f("title", "Quest"), _f("objective", "Current objective"), _f("done", "Done", "bool")]},
    {"id": "offscreen", "panel": "scene", "kind": "list", "key": "name", "icon": "👁️", "label": "Off-screen",
     "help": "What important characters who are not in the scene are doing meanwhile.",
     "fields": [_f("name", "Who"), _f("location", "Where"), _f("doing", "Doing")]},
    # --- Characters ---
    {"id": "characters", "panel": "characters", "kind": "list", "key": "name", "icon": "👥",
     "label": "Present characters",
     "help": "Everyone in the scene: mood, look, outfit and private thoughts.",
     "fields": [_f("name", "Name"), _f("mood", "Mood"), _f("appearance", "Look"),
                _f("outfit", "Outfit"), _f("thoughts", "Thinks")]},
    {"id": "clothing", "panel": "characters", "kind": "list", "key": "name", "icon": "👗",
     "label": "Detailed clothing",
     "help": "Clothing by body part, held items and injuries. More precise than Outfit.",
     "fields": [_f("name", "Name"), _f("head", "Head"), _f("upper_body", "Upper body"),
                _f("lower_body", "Lower body"), _f("feet", "Feet"), _f("accessories", "Accessories"),
                _f("held", "Holding"), _f("wounds", "Wounds")]},
    {"id": "relationships", "panel": "characters", "kind": "list", "key": "name", "icon": "❤️",
     "label": "Relationships",
     "help": "How each character feels about the user (your persona), with the reason for the last change.",
     "fields": [_f("name", "Name"), _f("affection", "Affection", "meter", min=-100, max=100),
                _f("trust", "Trust", "meter", min=0, max=100), _f("tension", "Tension", "meter", min=0, max=100),
                _f("status", "Status", hint="e.g. wary allies"), _f("last_change", "Last change")]},
    {"id": "secrets", "panel": "characters", "kind": "list", "key": "secret", "icon": "🤫", "label": "Secrets",
     "help": "Who knows what, and who it is hidden from.",
     "fields": [_f("secret", "Secret"), _f("known_by", "Known by"), _f("hidden_from", "Hidden from")]},
    # --- You (the persona) ---
    {"id": "stats", "panel": "you", "kind": "list", "key": "name", "icon": "📊", "label": "Stats",
     "help": "Status bars such as Health, Energy or Hunger.",
     "fields": [_f("name", "Stat"), _f("value", "Value", "number"), _f("max", "Max", "number")]},
    {"id": "conditions", "panel": "you", "kind": "list", "key": "name", "icon": "🩹", "label": "Conditions",
     "help": "Temporary states: injured, drunk, cursed, exhausted...",
     "fields": [_f("name", "Condition"), _f("effect", "Effect"), _f("duration", "Duration")]},
    {"id": "inventory", "panel": "you", "kind": "list", "key": "name", "icon": "🎒", "label": "Inventory",
     "help": "Money, equipped gear and carried items.",
     "fields": [_f("name", "Item"), _f("qty", "Qty", "number"),
                _f("group", "Group", hint="currency / equipped / carried")]},
    {"id": "reputation", "panel": "you", "kind": "list", "key": "group", "icon": "🏛️", "label": "Reputation",
     "help": "Standing with factions, places or groups.",
     "fields": [_f("group", "Group"), _f("standing", "Standing", "meter", min=-100, max=100), _f("note", "Why")]},
    {"id": "achievements", "panel": "you", "kind": "list", "key": "name", "icon": "🏆", "label": "Achievements",
     "help": "Milestones you have reached.",
     "fields": [_f("name", "Achievement"), _f("detail", "Detail")]},
    # --- Custom ---
    {"id": "custom", "panel": "custom", "kind": "object", "icon": "🧩", "label": "Custom tracker",
     "help": "Your own fields: counters, currencies, flags, anything the story needs.",
     "fields": []},  # filled from the character's config
]

TRACKERS_BY_ID = {t["id"]: t for t in TRACKERS}
FIELD_TYPES = ("text", "number", "meter", "bool", "list")
DEFAULT_ON = {"world": True}  # a new character starts with only World on


# ---------------------------------------------------------------------------
# Config (per character)
# ---------------------------------------------------------------------------

def normalize_custom_fields(raw):
    fields, seen = [], set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("key") or "").strip()[:60]
        if not label:
            continue
        key = re.sub(r"[^a-z0-9_]+", "_", label.lower()).strip("_") or "field"
        while key in seen:
            key += "_"
        seen.add(key)
        ftype = item.get("type") if item.get("type") in FIELD_TYPES else "text"
        field = _f(key, label, ftype, str(item.get("hint") or "")[:200])
        if ftype == "meter":
            field["min"] = _num(item.get("min"), 0)
            field["max"] = _num(item.get("max"), 100)
            if field["max"] <= field["min"]:
                field["max"] = field["min"] + 100
        fields.append(field)
    return fields


def normalize_config(raw):
    raw = raw if isinstance(raw, dict) else {}
    enabled_raw = raw.get("trackers") if isinstance(raw.get("trackers"), dict) else {}
    trackers = {}
    for t in TRACKERS:
        item = enabled_raw.get(t["id"]) if isinstance(enabled_raw.get(t["id"]), dict) else {}
        trackers[t["id"]] = {
            "on": bool(item.get("on", DEFAULT_ON.get(t["id"], False))),
            "prompt": bool(item.get("prompt", True)),  # add to the main prompt
        }
    layout = raw.get("layout") if isinstance(raw.get("layout"), dict) else {}
    return {
        "trackers": trackers,
        "custom_fields": normalize_custom_fields(raw.get("custom_fields")),
        "layout": {
            "hud": bool(layout.get("hud", True)),        # pill strip above the chat
            "panel": bool(layout.get("panel", True)),    # tabbed side panel
            "side": "left" if layout.get("side") == "left" else "right",
        },
    }


def tracker_spec(tracker_id, config):
    spec = TRACKERS_BY_ID[tracker_id]
    if tracker_id == "custom":
        spec = {**spec, "fields": config["custom_fields"]}
    return spec


def enabled_trackers(config):
    out = []
    for t in TRACKERS:
        if not config["trackers"][t["id"]]["on"]:
            continue
        spec = tracker_spec(t["id"], config)
        if spec["fields"]:  # a custom tracker without fields has nothing to track
            out.append(spec)
    return out


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def _num(value, default=0):
    try:
        n = float(value)
    except (TypeError, ValueError):
        m = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
        if not m:
            return default
        n = float(m.group())
    return int(n) if n == int(n) else round(n, 2)


def coerce_field(field, value):
    t = field["type"]
    if t == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "yes", "1", "done", "y")
        return bool(value)
    if t == "list":
        if isinstance(value, str):
            value = [v for v in re.split(r"[,;\n]", value)]
        if not isinstance(value, list):
            return []
        return [str(v).strip()[:80] for v in value if str(v).strip()][:30]
    if t in ("number", "meter"):
        n = _num(value, field.get("min", 0) if t == "meter" else 0)
        if t == "meter":
            n = max(field["min"], min(field["max"], n))
        return n
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    return str(value).strip()[:500]


def empty_value(spec):
    return {} if spec["kind"] == "object" else []


def coerce_tracker(spec, value):
    """Clean a whole tracker value. Object: only known fields. List: records with a key."""
    if spec["kind"] == "object":
        value = value if isinstance(value, dict) else {}
        return {f["key"]: coerce_field(f, value[f["key"]]) for f in spec["fields"] if f["key"] in value}

    items, seen = [], set()
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        item = {f["key"]: coerce_field(f, raw.get(f["key"])) for f in spec["fields"]}
        key = str(item.get(spec["key"]) or "").strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        items.append(item)
    return items[:40]


def lock_path(tracker_id, field_key, item_key=None):
    if item_key is None:
        return f"{tracker_id}.{field_key}"
    return f"{tracker_id}[{item_key.lower()}].{field_key}"


def merge(spec, old, new, locks):
    """Apply an AI update to a tracker, keeping locked fields (and items with locks)."""
    tid = spec["id"]
    if spec["kind"] == "object":
        result = dict(old or {})
        for key, value in coerce_tracker(spec, new).items():
            if lock_path(tid, key) not in locks:
                result[key] = value
        return result

    old_items = {str(i.get(spec["key"], "")).lower(): i for i in (old or [])}
    result, used = [], set()
    for item in coerce_tracker(spec, new):
        k = str(item[spec["key"]]).lower()
        if k in old_items:
            for f in spec["fields"]:
                if lock_path(tid, f["key"], k) in locks:
                    item[f["key"]] = old_items[k].get(f["key"], item[f["key"]])
        result.append(item)
        used.add(k)
    # Items the AI dropped survive if the user locked anything on them
    for k, item in old_items.items():
        if k not in used and any(lock_path(tid, f["key"], k) in locks for f in spec["fields"]):
            result.append(item)
    return result


def normalize_state(raw, config):
    raw = raw if isinstance(raw, dict) else {}
    values = raw.get("values") if isinstance(raw.get("values"), dict) else {}
    clean = {}
    for t in TRACKERS:
        spec = tracker_spec(t["id"], config)
        if t["id"] in values:
            clean[t["id"]] = coerce_tracker(spec, values[t["id"]])
    locks = [str(p) for p in raw.get("locks", []) if isinstance(p, str)][:500]
    return {"values": clean, "locks": locks, "upto": raw.get("upto")}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def _describe(spec):
    parts = []
    for f in spec["fields"]:
        desc = f'"{f["key"]}" ({f["type"]}'
        if f["type"] == "meter":
            desc += f' {f["min"]}..{f["max"]}'
        desc += ")"
        if f.get("hint"):
            desc += f" – {f['hint']}"
        parts.append(desc)
    shape = "object" if spec["kind"] == "object" else f'list of records, one per "{spec["key"]}"'
    return f'- "{spec["id"]}" ({spec["label"]}: {spec["help"]}) – {shape}; fields: ' + ", ".join(parts)


def update_messages(config, state, recent_messages, char_name, user_name, only=None):
    """Messages for the tracker AI call."""
    specs = [s for s in enabled_trackers(config) if not only or s["id"] in only]
    current = {s["id"]: state["values"].get(s["id"], empty_value(s)) for s in specs}
    system = (
        f"You keep the story-state trackers for a roleplay between {user_name} (the user) and {char_name}.\n"
        "Read the recent messages and update the trackers to match what is true NOW in the story.\n\n"
        "Rules:\n"
        "- Reply with ONLY a JSON object: {\"tracker_id\": value, ...}.\n"
        "- Include only trackers whose data changed. Omit unchanged ones.\n"
        "- If a tracker is still empty, fill it in from what the story shows so far.\n"
        "- For list trackers, return the COMPLETE updated list (drop entries that no longer apply).\n"
        "- For object trackers, return only the fields that changed.\n"
        "- Keep values short: a few words. Only use facts from the story; never invent events.\n"
        "- Numbers and meters must be numbers within their range.\n"
        "- Never change locked values.\n\n"
        "Trackers:\n" + "\n".join(_describe(s) for s in specs) + "\n\n"
        "Current values:\n" + json.dumps(current, ensure_ascii=False) + "\n\n"
        "Locked (do not change): " + (", ".join(state["locks"]) if state["locks"] else "none")
    )
    transcript = "\n\n".join(f"{role.upper()}: {text}" for role, text in recent_messages)
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Recent messages:\n\n{transcript}\n\nReturn the JSON update now."},
    ]


def parse_update(text):
    """Pull the JSON object out of the model's reply (tolerates code fences and chatter)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("The tracker model did not return JSON.")
    data = json.loads(text[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("The tracker model did not return a JSON object.")
    return data


def apply_update(config, state, update, only=None):
    """Merge a parsed AI update into state (in place). Returns the ids that changed."""
    changed = []
    for spec in enabled_trackers(config):
        tid = spec["id"]
        if tid not in update or (only and tid not in only):
            continue
        old = state["values"].get(tid, empty_value(spec))
        new = merge(spec, old, update[tid], set(state["locks"]))
        if new != old:
            state["values"][tid] = new
            changed.append(tid)
    return changed


def _fmt_value(field, value):
    if field["type"] == "list":
        return ", ".join(value)
    if field["type"] == "bool":
        return "yes" if value else "no"
    if field["type"] == "meter":
        return f"{value}/{field['max']}"
    return str(value)


def format_for_prompt(config, state):
    """The tracked state as text for the main chat prompt."""
    blocks = []
    for spec in enabled_trackers(config):
        if not config["trackers"][spec["id"]]["prompt"]:
            continue
        value = state["values"].get(spec["id"])
        if not value:
            continue
        if spec["kind"] == "object":
            parts = [f"{f['label']}: {_fmt_value(f, value[f['key']])}"
                     for f in spec["fields"] if value.get(f["key"]) not in ("", [], None)]
            if parts:
                blocks.append(f"{spec['label']}: " + "; ".join(parts))
        else:
            lines = []
            for item in value:
                parts = [f"{f['label'].lower()} {_fmt_value(f, item[f['key']])}"
                         for f in spec["fields"][1:] if item.get(f["key"]) not in ("", [], None)]
                if spec["id"] == "stats" and item.get("max"):
                    parts = [f"{item['value']}/{item['max']}"]
                lines.append(f"- {item[spec['key']]}" + (": " + "; ".join(parts) if parts else ""))
            blocks.append(f"{spec['label']}:\n" + "\n".join(lines))
    if not blocks:
        return ""
    return "### Current story state (tracked; keep your reply consistent with it)\n" + "\n\n".join(blocks)
