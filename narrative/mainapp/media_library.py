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


def find(kind, name):
    """The built-in item with this name (any case), or None."""
    key = str(name or "").strip().lower()
    return next((i for i in built_in(kind) if i["name"].lower() == key), None)
