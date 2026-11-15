"""The backgrounds and music that ship with the app (static/defaults/, named in catalog.json)."""
import json
from functools import lru_cache

from django.conf import settings

FOLDER = settings.BASE_DIR / "static" / "defaults"


@lru_cache(maxsize=1)
def catalog():
    try:
        return json.loads((FOLDER / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"backgrounds": [], "music": []}


def built_in(kind):
    """[{"name", "url"}] for "backgrounds" or "music", only files that are really there."""
    return [{"name": item["name"], "url": f"{settings.STATIC_URL}defaults/{kind}/{item['file']}"}
            for item in catalog().get(kind, []) if (FOLDER / kind / item["file"]).exists()]


def radio():
    """The Pit radio's sets (catalog.json "radio"): [{"set", "tracks": [{"id", "name", "url"}]}], only files that
    are there. Played in the Pit, and offered in a chat's music picker; Bulba and "music follows the scene" keep to
    the named tracks above (these are named only with emoji)."""
    out = []
    for group in catalog().get("radio", []):
        tracks = [{"id": t["file"].rsplit("/", 1)[-1].rsplit(".", 1)[0], "name": t["name"],
                   "url": f"{settings.STATIC_URL}defaults/music/{t['file']}"}
                  for t in group.get("tracks", []) if (FOLDER / "music" / t["file"]).exists()]
        if tracks:
            out.append({"set": group.get("set", ""), "tracks": tracks})
    return out


def radio_for_picker():
    """The radio's tracks for a chat's music picker: [{"name": "🎶 Circus · 🔮🎭💫", "url"}]."""
    return [{"name": f"🎶 {g['set']} · {t['name']}", "url": t["url"]} for g in radio() for t in g["tracks"]]


def find(kind, name):
    """The built-in item with this name (any case), or None."""
    key = str(name or "").strip().lower()
    return next((i for i in built_in(kind) if i["name"].lower() == key), None)
