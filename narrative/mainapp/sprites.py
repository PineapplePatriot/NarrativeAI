"""
More mood pictures for a character than the nine built in (neutral, happy, sad, angry, surprised, scared, confused,
calm, scheming): up to MAX_EXTRA more, from SUGGESTED or named by them ("pouting", "battle-ready"). Uploaded on the
character's page or with Bulba's 📎, or drawn from the neutral picture by the image model like the others.

Kept on Character.extra_sprites: {"first": {emotion: file path}, "second": {...}} (the second character of a card
with two). The emotion check after each reply picks from the built-in moods plus the ones this character has.
"""
import re
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

BUILT_IN = ["neutral", "happy", "sad", "angry", "surprised", "scared", "confused", "calm", "scheming"]
SUGGESTED = ["flustered", "smug", "tired", "disgusted", "embarrassed", "determined", "worried", "excited", "bored",
             "thoughtful", "flirty", "hurt", "laughing", "crying", "annoyed"]
MAX_EXTRA = 24


def clean_name(name):
    """A mood name as kept: lower case, letters, spaces and hyphens, up to 24 characters ("" if unusable)."""
    name = re.sub(r"[^a-zа-яіїєґ' -]", "", str(name or "").strip().lower())
    return " ".join(name.split())[:24]


def _slot(second):
    return "second" if second else "first"


def extras(character, second=False):
    """{emotion: url} of this character's extra mood pictures."""
    data = (getattr(character, "extra_sprites", None) or {}).get(_slot(second)) or {}
    out = {}
    for emotion, path in data.items():
        try:
            out[emotion] = default_storage.url(path)
        except Exception:
            continue
    return out


def emotions(character):
    """Every mood the emotion check may pick for this character: the built-in ones and its own."""
    own = set((getattr(character, "extra_sprites", None) or {}).get("first", {})) | \
        set((getattr(character, "extra_sprites", None) or {}).get("second", {}))
    return BUILT_IN + sorted(own - set(BUILT_IN))


def url_of(character, prefix, emotion):
    """An extra mood picture's url for "photo" / "photo_second", or None."""
    return extras(character, prefix == "photo_second").get(emotion)


def save(character, emotion, content, ext="png", second=False):
    """Keep a picture as this mood (replacing an older one). Raises ValueError."""
    emotion = clean_name(emotion)
    if not emotion:
        raise ValueError("Give the mood a name (letters only).")
    if emotion in BUILT_IN:
        raise ValueError(f"“{emotion}” is one of the built-in moods: use its own slot.")
    data = dict(getattr(character, "extra_sprites", None) or {})
    slot = dict(data.get(_slot(second)) or {})
    if emotion not in slot and len(slot) >= MAX_EXTRA:
        raise ValueError(f"That's {MAX_EXTRA} extra moods already; remove one first.")
    if slot.get(emotion):
        default_storage.delete(slot[emotion])
    path = default_storage.save(f"photos/extra/{character.slug}-{emotion.replace(' ', '-')}-{uuid.uuid4().hex[:6]}.{ext}",
                                ContentFile(content))
    slot[emotion] = path
    data[_slot(second)] = slot
    character.extra_sprites = data
    character.save(update_fields=["extra_sprites"])
    return default_storage.url(path)


def remove(character, emotion, second=False):
    data = dict(getattr(character, "extra_sprites", None) or {})
    slot = dict(data.get(_slot(second)) or {})
    path = slot.pop(clean_name(emotion), None)
    if path:
        default_storage.delete(path)
    data[_slot(second)] = slot
    character.extra_sprites = data
    character.save(update_fields=["extra_sprites"])
