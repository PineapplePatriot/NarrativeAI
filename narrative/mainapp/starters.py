"""
Starters: ready-made presets per model, one for each experience (mainapp/data/starters/*.json).

A starter is a normal preset plus a title, a description and the community presets it was
based on (credited and linked, not copied wholesale). Using one creates a preset the user
owns and activates it, so it can be edited and exported like any other.
"""
import copy
import json
from functools import lru_cache
from pathlib import Path

from mainapp import model_profiles, presets

DATA_DIR = Path(__file__).resolve().parent / "data" / "starters"

EXPERIENCES = {
    "back_and_forth": {"label": "Back-and-forth", "order": 0},
    "rich_scene": {"label": "Rich scene", "order": 1},
    "director": {"label": "Director seat", "order": 2},
    "full_preset": {"label": "Community preset", "order": 3},  # a well-known preset, whole (e.g. Realistic Frankenstein)
}


@lru_cache(maxsize=1)
def all_starters():
    out = []
    for path in sorted(DATA_DIR.glob("*.json")):
        with open(path, encoding="utf-8") as f:
            out.append(json.load(f))
    return out


def get(starter_id):
    return next((s for s in all_starters() if s["id"] == starter_id), None)


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


def apply(user, starter_id):
    """Create the user's own preset from a starter and make it active."""
    from mainapp.models import Preset
    s = get(starter_id)
    if s is None:
        raise ValueError("No such starter.")
    data = presets.normalize(copy.deepcopy(s["preset"]))
    data["extras"] = {**data["extras"], "starter": {"id": s["id"], "model": s["model"], "based_on": s.get("based_on", [])}}
    card = _card(s)
    obj = Preset.objects.create(user=user, data=data,
                                name=presets.unique_name(user, f"{s['title']} · {card['model_name']}"))
    presets.activate(obj)
    return obj
