"""Original experience catalog plus compatibility lookup for legacy starters.

New presets use independently authored components; legacy artifacts remain readable for saved
proposals and user imports. Creating a preset never rewrites an existing saved preset.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

from mainapp import model_profiles, presets, writing_quality, experiences

DATA_DIR = Path(__file__).resolve().parent / "data" / "starters"

EXPERIENCES = {
    "conversation": {"label": "Conversation & Chemistry", "order": 0},
    "drama": {"label": "Character Drama", "order": 1},
    "storytelling": {"label": "Immersive Storytelling", "order": 2},
    "back_and_forth": {"label": "Back-and-forth", "order": 0},
    "rich_scene": {"label": "Rich scene", "order": 1},
    "director": {"label": "Director seat", "order": 2},
    "full_preset": {"label": "Community preset", "order": 3},  # a well-known preset, whole (e.g. Realistic Frankenstein)
    "full_preset_fast": {"label": "Community preset, faster setup", "order": 4},
}


@lru_cache(maxsize=1)
def legacy_starters():
    out = []
    for path in sorted(DATA_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            out.append(writing_quality.add_baseline(json.load(f)))
    return out


@lru_cache(maxsize=1)
def all_starters():
    templates = {s['id']: s for s in legacy_starters()}
    return [experiences.generate(templates[p['starters']['rich_scene']], p, feel)
            for p in model_profiles.all_profiles() for feel in experiences.EXPERIENCES]


def get(starter_id):
    return next((s for s in [*all_starters(), *legacy_starters()] if s["id"] == starter_id), None)


def _card(s):
    profile = next((p for p in model_profiles.all_profiles() if p["id"] == s["model"]), {})
    return {"id": s["id"], "title": s["title"], "tagline": s["tagline"], "description": s["description"],
            "experience": s["experience"], "model": s["model"], "model_name": profile.get("name", s["model"]),
            "based_on": s.get("based_on", []), "status": s.get("status", "draft")}


def for_page(model):
    """Starters grouped by model, the user's chat model first."""
    mine = model_profiles.for_model(model)
    groups = {}
    for s in all_starters():
        groups.setdefault(s["model"], []).append(_card(s))
    ordered = sorted(groups.items(), key=lambda kv: (not (mine and kv[0] == mine["id"]), kv[0]))
    return [{"model": mid, "model_name": cards[0]["model_name"], "yours": bool(mine and mid == mine["id"]),
             "starters": sorted(cards, key=lambda c: EXPERIENCES.get(c["experience"], {}).get("order", 9))}
            for mid, cards in ordered]


def apply(user, starter_id, mode=None, extensions=()):
    """Create the user's own preset from a starter and make it active."""
    from mainapp.models import Preset
    s = get(starter_id)
    if s is None:
        raise ValueError("No such starter.")
    data = presets.normalize(copy.deepcopy(s["preset"]))
    if data["extras"].get("original_experience"):
        from mainapp.bulba import control
        chosen_mode = mode if mode is not None else control.mode_of(presets.normalize(presets.get_active(user).data))
        data = experiences.configure(data, chosen_mode, extensions)
    data["extras"] = {**data["extras"], "starter": {"id": s["id"], "model": s["model"], "based_on": s.get("based_on", [])}}
    from mainapp import ai_client
    chosen = ai_client.get_task_setting(user, "chat").context  # the memory they picked with Bulba wins
    if chosen:
        data["samplers"]["context_size"] = {"on": True, "value": chosen}
    card = _card(s)
    from mainapp import mature
    data = mature.keep(user, data)  # they switched adult scenes on earlier (the setup's form, the chat's menu)
    obj = Preset.objects.create(user=user, data=data,
                                name=presets.unique_name(user, f"{s['title']} · {card['model_name']}"))
    presets.activate(obj)
    return obj


READY_FEELS = experiences.EXPERIENCES


def ready_for(model_id):
    """The same three reading experiences for every supported model."""
    profile = next((p for p in model_profiles.all_profiles() if p["id"] == model_id), {})
    out = []
    for feel in READY_FEELS:
        s = get((profile.get("starters") or {}).get(feel, ""))
        if s:
            out.append({"id": s["id"], "feel": feel, "label": EXPERIENCES[feel]["label"], "tagline": s.get("tagline", "")})
    return out


def apply_ready(user, starter_id, mode=None, extensions=()):
    """Apply a ready experience with independent authorship and optional extensions."""
    s = get(starter_id)
    if s is None or s.get("experience") not in (*READY_FEELS, "back_and_forth", "rich_scene", "director"):
        raise ValueError("No such ready setup.")
    obj = apply(user, starter_id, mode=mode, extensions=extensions)
    if (mode == "director") or (s["experience"] == "director" and mode is None):
        from mainapp.bulba import control
        from mainapp.views import set_layout
        obj.data = control.apply_to_preset(presets.normalize(obj.data), "director")
        obj.save(update_fields=["data"])
        set_layout(user, "book")
    return obj
