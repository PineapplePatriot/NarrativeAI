"""
Editing a proposal before applying it: the text parts of Bulba's proposals (a persona, a character, card
changes, the taste section of a preset, lore entries, greetings) can be changed by the user in the card itself.
Settings-like proposals (extras, model settings, trackers, theme, voices) are changed by asking Bulba instead.
"""
CHARACTER_FIELDS = [("name", "Name", False), ("description", "Description", True), ("personality", "In short", True),
                    ("scenario", "Scenario", True), ("greeting", "First message", True),
                    ("example_dialogue", "Example dialogue", True)]
LIMIT = 40000


def fields(p):
    """[{"path", "label", "value", "long"}] the user can edit, for a pending proposal."""
    if p.get("status") != "pending":
        return []
    data, kind, out = p.get("payload") or {}, p["kind"], []

    def add(path, label, value, long=True):
        out.append({"path": path, "label": label, "value": value if isinstance(value, str) else "", "long": long})

    if kind == "persona":
        add("name", "Name", data.get("name"), False)
        add("description", "Description", data.get("description"))
    elif kind == "character":
        for key, label, long in CHARACTER_FIELDS:
            add(key, label, data.get(key), long)
    elif kind == "card_edit":
        for key, text in (data.get("fields") or {}).items():
            add(f"fields.{key}", key.replace("_", " ").capitalize(), text)
    elif kind == "preset":
        add("taste", "Your taste", data.get("taste"))
    elif kind == "lorebook":
        for i, e in enumerate(data.get("entries") or []):
            add(f"entries.{i}.content", e.get("comment") or f"Entry {i + 1}", e.get("content"))
            if not e.get("constant"):
                add(f"entries.{i}.keys", "  comes up when someone mentions (comma-separated)", ", ".join(e.get("keys") or []), False)
    elif kind in ("lore_edit", "preset_edit"):
        for i, e in enumerate(data.get("edits") or []):
            if isinstance(e.get("content"), str) and e.get("content"):
                add(f"edits.{i}.content", e.get("title") or e.get("block") or f"Change {i + 1}", e["content"])
    elif kind == "greetings":
        for i, g in enumerate(data.get("greetings") or []):
            add(f"greetings.{i}", f"Greeting {i + 1}", g)
    return out


def _set(data, path, value):
    parts = path.split(".")
    target = data
    for part in parts[:-1]:
        target = target[int(part)] if isinstance(target, list) else target[part]
    last = parts[-1]
    if isinstance(target, list):
        target[int(last)] = value
    else:
        target[last] = value


def edit(session, pid, values):
    """Writes the user's changes into a pending proposal and its card text. Returns the changed labels."""
    p = next((x for x in session.proposals if x["id"] == pid), None)
    if p is None:
        raise ValueError("No such proposal.")
    editable = {f["path"]: f for f in fields(p)}
    if not editable:
        raise ValueError("This one can't be edited here; tell Bulba what to change instead.")
    changed, replaced = [], []
    for path, value in (values or {}).items():
        f = editable.get(path)
        if f is None or not isinstance(value, str):
            continue
        value = value.strip()[:LIMIT]
        if value == (f["value"] or "").strip():
            continue
        if path.endswith(".keys"):
            keys = [k.strip() for k in value.split(",") if k.strip()][:10]
            if not keys:
                raise ValueError("A lore entry needs at least one word that brings it up.")
            _set(p["payload"], path, keys)
        else:
            if not value and path in ("name", "description", "taste"):
                raise ValueError(f"{f['label']} can't be empty.")
            _set(p["payload"], path, value)
            replaced.append(((f["value"] or "").strip(), value))
        changed.append(f["label"].strip())
    if changed:
        p["summary"] = _summary(p, replaced)
        if p["kind"] in ("persona", "character"):  # the card's title carries the name
            p["title"] = f"{'You' if p['kind'] == 'persona' else 'Character'}: {p['payload']['name']}"
        p["edited"] = True
    return p, changed


def _summary(p, replaced=()):
    """The card's text again, from the edited payload (keeping Bulba's own lines that weren't editable)."""
    data, kind, old = p["payload"], p["kind"], list(p.get("summary") or [])
    why = old[old.index("Why:"):] if "Why:" in old else []
    if kind == "persona":
        return [data["description"]]
    if kind == "character":
        out = []
        for key, label, _ in CHARACTER_FIELDS[1:]:
            if data.get(key):
                out += [f"{label if key != 'greeting' else 'First message'}:", data[key]]
        return out
    if kind == "card_edit":
        out = []
        for key, text in data["fields"].items():
            out += [f"{key.replace('_', ' ').capitalize()}:", text]
        return out + why
    if kind == "preset":
        start = old.index("Your taste:") if "Your taste:" in old else len(old)
        end = next((i for i in range(start + 1, len(old)) if not old[i].startswith("  ")), len(old))
        return old[:start] + ["Your taste:", *[f"  {line}" for line in data["taste"].splitlines() if line.strip()]] + old[end:]
    if kind == "lorebook":
        out = old[:1]
        for e in data["entries"]:
            trigger = "always in the story" if e.get("constant") else "when someone mentions " + ", ".join(e["keys"])
            out += [f"{e['comment']}:", f"  ({trigger}) {e['content']}"]
        return out + why
    if kind in ("lore_edit", "preset_edit"):  # the card quotes the new text: swap the old for the edited
        out = []
        for line in old:
            for before, after in replaced:
                if before and before in line:
                    line = line.replace(before, after)
            out.append(line)
        return out
    if kind == "greetings":
        return [f"{len(data['greetings'])} alternate greeting(s)."] + \
            [f"{i + 1}. {g[:300]}{'…' if len(g) > 300 else ''}" for i, g in enumerate(data["greetings"])] + why
    return old
