"""
Moving people onto the experience presets (experiences.py), shown once on the chat page:

- An old preset nobody changed (the old default, or an old starter used as it came) is switched automatically to
  the matching experience for their model, with a note and Undo; nothing is deleted.
- An old preset they edited or imported gets a one-time offer instead.
- An experience preset made for another model (they changed it in Connections) gets an offer to rebuild it for the
  model they use now.

What carries over: who writes their character, adult scenes, their taste and Basics blocks, chat memory, and for a
rebuild also the experience, reply length and every module's on/off state.
"""
import copy
import json
from pathlib import Path

from mainapp import experiences, model_profiles, presets

KEY = "preset_upgrade_v1"   # ChatSettings.appearance: the one-time move off old presets
REBUILD = "preset_rebuild"  # ChatSettings.appearance: rebuild offers dismissed, per "from>to" model pair
LEGACY_FEEL = {"back_and_forth": "conversation", "rich_scene": "drama", "director": "drama"}
CARRY = ("Your taste", "Basics")  # their own blocks, kept in a new preset
APP_ADDED = {"Mature content", "Mature content (optional)", "Reply reminder", "Basics", "Your character", "Your taste"}
STARTERS_DIR = Path(__file__).resolve().parent / "data" / "starters"


def _settings(user):
    from mainapp.models import ChatSettings
    obj, _ = ChatSettings.objects.get_or_create(author=user)
    return obj


def _remember(user, key, value):
    obj = _settings(user)
    obj.appearance = {**(obj.appearance or {}), key: value}
    obj.save(update_fields=["appearance"])


def _prompts(blocks):
    return {(b.get("name"), (b.get("content") or "").strip()) for b in blocks
            if b.get("kind") == "prompt" and b.get("name") not in APP_ADDED}


def _raw_starter(starter_id):
    path = STARTERS_DIR / f"{starter_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def is_new(data):
    return bool((data.get("extras") or {}).get("original_experience"))


def untouched(user, data):
    """True when an old preset is exactly what the app gave them (apart from the app's own switches)."""
    extras = data.get("extras") or {}
    starter = extras.get("starter") or {}
    if starter.get("id"):
        raw = _raw_starter(starter["id"])
        if raw is None or raw.get("experience") not in LEGACY_FEEL:
            return False
        from mainapp.bulba import control
        original = presets.normalize(raw["preset"])
        mode = control.mode_of(data)
        if mode != "dont":  # the app's own authorship switch rewrites a line or two of the starter
            original = control.apply_to_preset(original, mode)
        return _prompts(original["blocks"]) == _prompts(data["blocks"])
    if extras.get("bulba"):
        return False
    return _prompts(presets.build_default(user)["blocks"]) == _prompts(data["blocks"])


def _feel_of(data):
    if is_new(data):
        return data["extras"]["original_experience"]["id"]
    starter = _raw_starter(((data.get("extras") or {}).get("starter") or {}).get("id", "")) or {}
    return LEGACY_FEEL.get(starter.get("experience"), experiences.catalog()["default_experience"])


def convert(data, profile):
    """The experience preset for `profile` that matches `data`, with their choices carried over."""
    from mainapp import mature, starters
    from mainapp.bulba import control
    feel = _feel_of(data)
    starter = starters.get(profile["starters"][feel])
    mode = control.mode_of(data)
    new = presets.normalize(copy.deepcopy(starter["preset"]))
    ext_titles = {e["title"]: k for k, e in experiences.catalog()["extensions"].items()}
    extensions = [ext_titles[b["name"]] for b in data["blocks"] if b.get("name") in ext_titles and b.get("enabled")]
    new = experiences.configure(new, mode, extensions)
    if is_new(data):  # a rebuild: every module and the reply length as they had them
        states = {b["name"]: b.get("enabled") for b in data["blocks"] if b.get("kind") == "prompt"}
        for b in new["blocks"]:
            if b["name"] in states and b["name"] not in ("Your character",) and b["kind"] == "prompt" \
                    and b["name"] not in {e["title"] for e in experiences.catalog()["extensions"].values()}:
                b["enabled"] = states[b["name"]]
        old_len = next((b for b in data["blocks"] if b.get("name") == experiences.LENGTH_BLOCK), None)
        mine = next((b for b in new["blocks"] if b.get("name") == experiences.LENGTH_BLOCK), None)
        if old_len and mine:
            mine["content"] = old_len["content"]
    at = next((i for i, b in enumerate(new["blocks"]) if b.get("kind") == "marker"), len(new["blocks"]))
    for name in reversed(CARRY):
        old = next((b for b in data["blocks"] if b.get("name") == name and b.get("kind") == "prompt"), None)
        if old and old.get("content", "").strip():
            new["blocks"] = [b for b in new["blocks"] if b.get("name") != name]
            new["blocks"].insert(at, presets.normalize_block({**copy.deepcopy(old)}))
    if (data.get("samplers") or {}).get("context_size", {}).get("on"):
        new["samplers"]["context_size"] = copy.deepcopy(data["samplers"]["context_size"])
    new["extras"] = {**new["extras"], "starter": {"id": starter["id"], "model": starter["model"], "based_on": []}}
    if mature.is_on(data):
        new = mature.set_on(new, True)
    return new, starter


def _profile(user):
    from mainapp import ai_client
    try:
        _, model = ai_client.resolve(user, "chat")
    except Exception:
        return None
    return model_profiles.for_style(model)


def _name(starter):
    return f"{starter['title']} · {(model_profiles.by_id(starter['model']) or {}).get('name', starter['model'])}"


def switch(user, mark="switched"):
    """Their active old preset → a new experience preset (a new entry; the old one stays). Returns the new one."""
    from mainapp.models import Preset
    profile = _profile(user)
    if profile is None:
        return None
    old = presets.get_active(user)
    data, starter = convert(presets.normalize(old.data), profile)
    new = Preset.objects.create(user=user, data=data, name=presets.unique_name(user, _name(starter)))
    presets.activate(new)
    _remember(user, KEY, {"state": mark, "from": old.id, "to": new.id, "from_name": old.name})
    return new


def undo(user):
    from mainapp.models import Preset
    state = (_settings(user).appearance or {}).get(KEY) or {}
    old = Preset.objects.filter(user=user, id=state.get("from")).first()
    if old is None:
        return False
    presets.activate(old)
    _remember(user, KEY, {**state, "state": "undone"})
    return True


def rebuild(user):
    """The active experience preset rebuilt in place for the model they use now (Undo keeps the previous version)."""
    profile = _profile(user)
    if profile is None:
        return None
    obj = presets.get_active(user)
    data = presets.normalize(obj.data)
    extras = data.get("extras") or {}
    before_model = (extras.get("starter") or {}).get("model") or (extras.get("original_experience") or {}).get("model", "")
    new, starter = convert(data, profile)
    _remember(user, "preset_rebuild_undo", {"id": obj.id, "data": data, "name": obj.name})
    old_auto = before_model and obj.name.endswith(" · " + (model_profiles.by_id(before_model) or {}).get("name", "\0"))
    obj.data = new
    if old_auto:  # a name the app gave it ("Heartstrings · MiMo v2.6 Pro") follows the model
        obj.name = presets.unique_name(user, _name(starter), exclude_id=obj.id)
    obj.save()
    return obj


def undo_rebuild(user):
    from mainapp.models import Preset
    saved = (_settings(user).appearance or {}).get("preset_rebuild_undo") or {}
    obj = Preset.objects.filter(user=user, id=saved.get("id")).first()
    if obj is None:
        return False
    obj.data, obj.name = saved["data"], presets.unique_name(user, saved["name"], exclude_id=obj.id)
    obj.save()
    return True


def pending(user):
    """What to show on the chat page now, or None. May switch an untouched old preset right away."""
    from django.conf import settings
    if getattr(settings, "LEGACY_FIRST_PRESET", False):  # the older tests run on the old default, unmoved
        return None
    profile = _profile(user)
    if profile is None:
        return None
    appearance = _settings(user).appearance or {}
    active = presets.get_active(user)
    data = presets.normalize(active.data)
    state = appearance.get(KEY) or {}
    if not is_new(data):
        if state:  # already moved, offered or declined once: never again on its own
            return None
        if untouched(user, data):
            new = switch(user, mark="switched")
            if new is None:
                return None
            _remember(user, KEY, {**(_settings(user).appearance or {}).get(KEY, {}), "seen": True})  # shown now
            return {"kind": "switched", "from": active.name, "to": new.name}
        return {"kind": "offer_upgrade", "from": active.name,
                "to": _name({"title": experiences.catalog()["experiences"][_feel_of(data)]["name"],
                             "model": profile["id"]})}
    if state.get("state") == "switched" and not state.get("seen"):
        _remember(user, KEY, {**state, "seen": True})
        return {"kind": "switched", "from": state.get("from_name", ""), "to": active.name}
    extras = data.get("extras") or {}
    made_for = (extras.get("starter") or {}).get("model") or (extras.get("original_experience") or {}).get("model", "")
    if made_for and made_for != profile["id"] and f"{made_for}>{profile['id']}" not in (appearance.get(REBUILD) or []):
        return {"kind": "offer_rebuild", "preset": active.name,
                "from": (model_profiles.by_id(made_for) or {}).get("name", made_for), "to": profile["name"],
                "pair": f"{made_for}>{profile['id']}"}
    return None


def decline(user, kind, pair=""):
    appearance = _settings(user).appearance or {}
    if kind == "offer_upgrade":
        _remember(user, KEY, {"state": "declined"})
    elif kind == "offer_rebuild" and pair:
        _remember(user, REBUILD, list(dict.fromkeys([*(appearance.get(REBUILD) or []), pair]))[-20:])
