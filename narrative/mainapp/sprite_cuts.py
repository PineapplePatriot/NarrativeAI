"""
Cut-outs for the chat's own pictures: a character's mood sprites (the nine, the second character's, the extra
moods), the persona's sprites, and Screen stickers.

The browser does the cutting (the same engine as episode looks) and sends the transparent PNG; this keeps it in
place of the picture and remembers the original, so the cut can be undone and new moods can still be drawn from the
uncut neutral picture (its plain background is what makes them cut cleanly).

Sprite names: "photo_happy", "photo_second_happy", "persona_photo_happy", "extra:<mood>", "extra2:<mood>".
"""
import io
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from mainapp import sprites

MAX_BYTES = 12 * 1024 * 1024
MOODS = list(sprites.BUILT_IN)


def check_png(data):
    """Raises ValueError unless `data` is a PNG with transparency."""
    from PIL import Image
    if len(data) > MAX_BYTES:
        raise ValueError("The cut-out is too large.")
    try:
        Image.open(io.BytesIO(data)).verify()
        image = Image.open(io.BytesIO(data))
    except Exception:
        raise ValueError("The cut-out isn't a picture.")
    if image.format != "PNG" or "A" not in image.getbands():
        raise ValueError("The cut-out must be a PNG with transparency.")


def _originals_field(obj):
    return "persona_sprite_originals" if hasattr(obj, "persona_sprite_originals") else "sprite_originals"


def _current(obj, name):
    """The storage path of the sprite called `name` on `obj`, or ""; raises ValueError for an unknown name."""
    if name.startswith(("extra:", "extra2:")):
        if not hasattr(obj, "extra_sprites"):
            raise ValueError("Extra moods belong to characters.")
        slot = "second" if name.startswith("extra2:") else "first"
        return ((obj.extra_sprites or {}).get(slot) or {}).get(sprites.clean_name(name.split(":", 1)[1])) or ""
    prefix, _, mood = name.rpartition("_")
    if mood not in MOODS or prefix not in ("photo", "photo_second", "persona_photo"):
        raise ValueError("Which picture?")
    if (prefix == "persona_photo") != hasattr(obj, "persona_sprite_originals"):
        raise ValueError("That picture isn't this one's.")
    field = getattr(obj, name, None)
    return field.name if field else ""


def _set(obj, name, path):
    if name.startswith(("extra:", "extra2:")):
        slot = "second" if name.startswith("extra2:") else "first"
        data = dict(obj.extra_sprites or {})
        data[slot] = {**(data.get(slot) or {}), sprites.clean_name(name.split(":", 1)[1]): path}
        obj.extra_sprites = data
        obj.save(update_fields=["extra_sprites"])
    else:
        getattr(obj, name).name = path
        obj.save(update_fields=[name])


def save_cut(obj, name, data):
    """Keep the browser's transparent copy in place of the picture; the first original is remembered. Returns url."""
    check_png(data)
    current = _current(obj, name)
    if not current:
        raise ValueError("There's no picture there to cut out.")
    field = _originals_field(obj)
    originals = dict(getattr(obj, field) or {})
    if _original(obj, name):
        default_storage.delete(current)  # an earlier cut-out of the same picture
    else:
        originals[name] = current  # (a stale entry from before an upload is replaced)
    path = default_storage.save(f"cutouts/{uuid.uuid4().hex[:6]}-{name.replace(':', '-')}.png", ContentFile(data))
    setattr(obj, field, originals)
    obj.save(update_fields=[field])
    _set(obj, name, path)
    return default_storage.url(path)


def _is_cut(path):
    return str(path or "").startswith("cutouts/")


def _original(obj, name):
    """The remembered original, if the picture there now is still our cut-out of it (an upload since replaces it)."""
    original = (getattr(obj, _originals_field(obj)) or {}).get(name) or ""
    return original if original and _is_cut(_current(obj, name)) else ""


def undo(obj, name):
    """Put the original back (the cut-out is deleted). Returns its url."""
    field = _originals_field(obj)
    originals = dict(getattr(obj, field) or {})
    original = _original(obj, name)
    originals.pop(name, None)
    if not original:
        setattr(obj, field, originals)
        obj.save(update_fields=[field])
        raise ValueError("That picture hasn't been cut out.")
    current = _current(obj, name)
    if current and current != original:
        default_storage.delete(current)
    setattr(obj, field, originals)
    obj.save(update_fields=[field])
    _set(obj, name, original)
    return default_storage.url(original)


def forget(obj, name):
    """A new picture replaced this one: its old original no longer belongs to it."""
    field = _originals_field(obj)
    originals = dict(getattr(obj, field) or {})
    old = originals.pop(name, "")
    if old:
        default_storage.delete(old)
        setattr(obj, field, originals)
        obj.save(update_fields=[field])


def uncut_bytes(obj, name):
    """The picture as drawn (before any cut-out): what new moods are drawn from. (bytes, mime) or None."""
    path = _original(obj, name) or _current(obj, name)
    if not path:
        return None
    try:
        with default_storage.open(path, "rb") as handle:
            raw = handle.read()
    except Exception:
        return None
    mime = "image/png" if raw.startswith(b"\x89PNG") else "image/webp" if raw[:4] == b"RIFF" else "image/jpeg"
    return raw, mime


def originals_list(obj):
    """The sprite names whose cut-out can be undone."""
    out = []
    for name in (getattr(obj, _originals_field(obj)) or {}):
        try:
            if _original(obj, name):
                out.append(name)
        except ValueError:
            continue
    return sorted(out)


# ---------- stickers ----------

def replace_sticker(user, old_url, data):
    """A Screen sticker the user owns (one of their own, or in one of their characters' packs), its picture replaced
    by the browser's cut-out. Returns the new url."""
    from mainapp import messenger
    from mainapp.models import Character
    check_png(data)
    path = default_storage.save(f"messenger/stickers/cut-{uuid.uuid4().hex[:10]}.png", ContentFile(data))
    new_url = default_storage.url(path)
    mine = list(messenger.user_profile(user).get("custom_stickers") or [])
    if any(s.get("url") == old_url for s in mine):
        messenger.save_user_profile(user, {"custom_stickers": [{**s, "url": new_url} if s.get("url") == old_url else s for s in mine]})
        return new_url
    for character in Character.objects.filter(author=user):
        pack = list(messenger.char_profile(character).get("sticker_pack") or [])
        if any(s.get("url") == old_url for s in pack):
            messenger.save_char_profile(character, {"sticker_pack": [{**s, "url": new_url} if s.get("url") == old_url else s
                                                                     for s in pack]})
            return new_url
    default_storage.delete(path)
    raise ValueError("That sticker isn't yours.")
