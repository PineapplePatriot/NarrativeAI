"""
Bulba and the text rules (find-and-replace rules, mainapp/regex_rules.py) of the active preset and the user's own
list: it reads them all, and proposes changes (switch on/off, add, edit, remove) that they Apply or Undo. The
card's own rules stay on/off only (tune.propose_card_rules), since they belong to the card's author.
"""
import copy

from mainapp import presets, regex_rules

MODE_HELP = {"saved": "changes the saved message", "display": "only what's shown on screen",
             "prompt": "only what's sent to the AI"}


def _view(rule):
    return {"id": rule["id"], "name": rule["name"], "find": rule["find"][:400], "replace": rule["replace"][:400],
            "on": [regex_rules.PLACEMENT_NAMES[p] for p in rule["placement"]], "mode": rule["mode"],
            "enabled": rule["enabled"]}


def current(user, scope):
    if scope == "preset":
        return presets.normalize(presets.get_active(user).data)["regex"]
    return regex_rules.user_rules(user)


def tool_read_text_rules(session, args):
    from mainapp.bulba.tune import target_character
    character = target_character(session)
    return {"preset": [_view(r) for r in current(session.user, "preset")],
            "mine": [_view(r) for r in current(session.user, "mine")],
            "card": [_view(r) for r in regex_rules.card_rules(character)] if character else [],
            "modes": MODE_HELP,
            "placements": {v: k for k, v in regex_rules.PLACEMENT_NAMES.items()}}, []


def _apply_changes(rules, changes):
    """The rules after the changes; ValueError with a plain reason when one can't be made."""
    rules = copy.deepcopy(rules)
    by_id = {r["id"]: r for r in rules}
    for c in changes:
        action = c.get("action")
        if action in ("switch", "edit", "remove") and c.get("id") not in by_id:
            raise ValueError(f"No rule with id {c.get('id')!r} (read_text_rules lists them).")
        if action == "switch":
            by_id[c["id"]]["enabled"] = bool(c.get("enabled"))
        elif action == "remove":
            rules = [r for r in rules if r["id"] != c["id"]]
            by_id.pop(c["id"])
        elif action in ("add", "edit"):
            base = by_id[c["id"]] if action == "edit" else {}
            fields = {k: c[k] for k in ("name", "find", "replace", "mode", "enabled", "min_depth", "max_depth")
                      if k in c}
            if "placement" in c:
                fields["placement"] = [p for p in c["placement"] if isinstance(p, int)]
            rule = regex_rules.normalize_rule({**base, **fields})
            problem = regex_rules.check(rule)
            if problem:
                raise ValueError(f"“{rule['name']}”: {problem}")
            if action == "edit":
                rules = [rule if r["id"] == rule["id"] else r for r in rules]
            else:
                rules.append(rule)
            by_id[rule["id"]] = rule
        else:
            raise ValueError("Each change is switch, add, edit or remove.")
    return rules


def _line(c, rules_before):
    name = c.get("name") or next((r["name"] for r in rules_before if r["id"] == c.get("id")), c.get("id"))
    if c["action"] == "switch":
        return f"{name}: {'on' if c.get('enabled') else 'off'}"
    if c["action"] == "remove":
        return f"Remove: {name}"
    detail = f"find {c['find']!r}" if c.get("find") else ""
    if "replace" in c:
        detail += f", replace with {c['replace']!r}" if c["replace"] else ", remove it"
    return f"{'Add' if c['action'] == 'add' else 'Change'}: {name} ({detail.strip(', ')})"


def tool_propose_text_rules(session, args):
    from mainapp.bulba.agent import _proposal
    scope = "preset" if args.get("scope") == "preset" else "mine"
    changes = [c for c in (args.get("changes") or []) if isinstance(c, dict)][:8]
    if not changes:
        return {"error": "No changes."}, []
    before = current(session.user, scope)
    try:
        _apply_changes(before, changes)
    except ValueError as e:
        return {"error": str(e)}, []
    where = f"the preset “{presets.get_active(session.user).name}”" if scope == "preset" else "your own list (every preset)"
    summary = [f"Text rules in {where}:", *[f"  {_line(c, before)}" for c in changes],
               "Why:", str(args.get("why") or "")[:400]]
    p = _proposal(session, "text_rules", "Text rules", summary,
                  {"scope": scope, "preset_id": presets.get_active(session.user).id, "changes": changes})
    return {"proposal": p["id"], "status": "waiting for Apply"}, [{"type": "proposal", "id": p["id"]}]


def _save(user, scope, preset_id, rules):
    from mainapp.models import Preset
    if scope == "preset":
        obj = Preset.objects.filter(user=user, id=preset_id).first()
        if obj is None:
            raise ValueError("That preset is gone.")
        data = presets.normalize(obj.data)
        data["regex"] = rules
        obj.data = data
        obj.save(update_fields=["data", "time_update"])
    else:
        regex_rules.save_user_rules(user, rules)


def apply(session, p):
    from mainapp.models import Preset
    d = p["payload"]
    if d["scope"] == "preset":
        obj = Preset.objects.filter(user=session.user, id=d["preset_id"]).first()
        if obj is None:
            raise ValueError("That preset is gone.")
        before = presets.normalize(obj.data)["regex"]
    else:
        before = regex_rules.user_rules(session.user)
    _save(session.user, d["scope"], d.get("preset_id"), _apply_changes(before, d["changes"]))
    p["undo"] = {"rules": before}
    return "Text rules saved. The next reply uses them."


def undo(session, p):
    d = p["payload"]
    _save(session.user, d["scope"], d.get("preset_id"), (p.get("undo") or {}).get("rules") or [])


KINDS = ("text_rules",)
HANDLERS = {"read_text_rules": tool_read_text_rules, "propose_text_rules": tool_propose_text_rules}
TURN_ENDING = {"propose_text_rules"}


def tool_defs(fn, STR):
    change = {"type": "object", "properties": {
        "action": {"type": "string", "enum": ["switch", "add", "edit", "remove"]},
        "id": {"type": "string", "description": "The rule's id (switch, edit, remove)"},
        "enabled": {"type": "boolean"}, "name": STR,
        "find": {"type": "string", "description": "A regular expression, e.g. /\\*\\*(.+?)\\*\\*/g"},
        "replace": {"type": "string", "description": "$1 for the first group; '' removes the match"},
        "placement": {"type": "array", "items": {"type": "integer"},
                      "description": "1 their messages, 2 AI replies, 5 lore entries, 6 the model's thinking"},
        "mode": {"type": "string", "enum": list(MODE_HELP), "description": "; ".join(f"{k}: {v}" for k, v in MODE_HELP.items())}},
        "required": ["action"]}
    return [
        fn("read_text_rules", "The text rules (find-and-replace) of the active preset, their own list (runs with "
           "every preset) and the character's card, with ids.", {}),
        fn("propose_text_rules", "Change text rules in the active preset (scope preset) or their own list (scope "
           "mine): switch, add, edit or remove. For formatting and clean-up only (asterisks, stray tags, a word "
           "they never want shown); never to fix how characters behave. They see the change and Apply.",
           {"scope": {"type": "string", "enum": ["preset", "mine"]},
            "changes": {"type": "array", "maxItems": 8, "items": change}, "why": STR}, ["scope", "changes", "why"]),
    ]
