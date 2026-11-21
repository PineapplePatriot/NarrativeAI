"""The backgrounds and music that ship with the app (static/defaults/, named in catalog.json), plus the ones the
project's owners upload from the stats page (kept on the volume, in media storage: library/, listed in
library/catalog.json), so they survive deploys and need no code change."""
import json
import uuid
from functools import lru_cache

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

FOLDER = settings.BASE_DIR / "static" / "defaults"
UPLOADS = "library/catalog.json"
KINDS = {"backgrounds": ((".png", ".jpg", ".jpeg", ".webp", ".gif"), 15), "music": ((".mp3", ".ogg", ".m4a", ".wav", ".opus"), 30)}


def uploads():
    """{"backgrounds": [{"name", "file"}], "music": [...], "radio": [{"set", "name", "file"}]}: the uploaded ones."""
    try:
        with default_storage.open(UPLOADS, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError, FileNotFoundError):
        data = {}
    return {k: [i for i in data.get(k) or [] if isinstance(i, dict) and i.get("file")] for k in ("backgrounds", "music", "radio")}


def _save_uploads(data):
    if default_storage.exists(UPLOADS):
        default_storage.delete(UPLOADS)
    default_storage.save(UPLOADS, ContentFile(json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")))


def add(kind, name, upload, radio_set=""):
    """An uploaded background ("backgrounds"), named track ("music") or radio track ("music" with radio_set).
    Raises ValueError for the person."""
    if kind not in KINDS:
        raise ValueError("Backgrounds or music only.")
    exts, max_mb = KINDS[kind]
    ext = ("." + upload.name.rsplit(".", 1)[-1].lower()) if "." in upload.name else ""
    if ext not in exts:
        raise ValueError(f"That kind of file doesn't work here: {', '.join(exts)}.")
    if upload.size > max_mb * 1024 * 1024:
        raise ValueError(f"Over {max_mb} MB.")
    name = " ".join(str(name or "").split())[:80] or upload.name.rsplit(".", 1)[0][:80]
    path = default_storage.save(f"library/{kind}/{uuid.uuid4().hex[:10]}{ext}", upload)
    data = uploads()
    if kind == "music" and radio_set:
        data["radio"].append({"set": " ".join(str(radio_set).split())[:60], "name": name, "file": path})
    else:
        data[kind].append({"name": name, "file": path})
    _save_uploads(data)
    return path


def remove(path):
    """An uploaded file out of the library (and off the disk)."""
    data = uploads()
    for k in data:
        data[k] = [i for i in data[k] if i["file"] != path]
    _save_uploads(data)
    if str(path).startswith("library/") and default_storage.exists(path):
        default_storage.delete(path)


@lru_cache(maxsize=1)
def catalog():
    try:
        return json.loads((FOLDER / "catalog.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"backgrounds": [], "music": []}


def built_in(kind):
    """[{"name", "url"}] for "backgrounds" or "music", only files that are really there (then the uploaded ones)."""
    return [{"name": item["name"], "url": f"{settings.STATIC_URL}defaults/{kind}/{item['file']}"}
            for item in catalog().get(kind, []) if (FOLDER / kind / item["file"]).exists()] + \
        [{"name": item["name"], "url": default_storage.url(item["file"])} for item in uploads().get(kind, [])]


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
    for item in uploads()["radio"]:  # uploaded tracks join their set (or start a new one)
        group = next((g for g in out if g["set"].lower() == item["set"].lower()), None)
        if group is None:
            group = {"set": item["set"], "tracks": []}
            out.append(group)
        group["tracks"].append({"id": item["file"].rsplit("/", 1)[-1].rsplit(".", 1)[0], "name": item["name"],
                                "url": default_storage.url(item["file"])})
    return out


def radio_for_picker():
    """The radio's tracks for a chat's music picker: [{"name": "🎶 Circus · 🔮🎭💫", "url"}]."""
    return [{"name": f"🎶 {g['set']} · {t['name']}", "url": t["url"]} for g in radio() for t in g["tracks"]]


def find(kind, name):
    """The built-in item with this name (any case), or None."""
    key = str(name or "").strip().lower()
    return next((i for i in built_in(kind) if i["name"].lower() == key), None)
