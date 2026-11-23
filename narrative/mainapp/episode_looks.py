"""
Episode looks: the third kind of character picture, used only on the visual-novel stage.

The chat page has its stage sprites (Character.photo_* and extra_sprites); the phone has its profile portrait and
reference photos (messenger_profile). Neither is shown or changed here. An episode look is one named outfit of one
character (or of the user's persona) in one setting, canon or modern, chosen by how the episode was entered.

Consistency comes from editing, not redrawing: the neutral picture is drawn once from the setting's references
on a solid key colour, and every other mood is an edit of that exact picture, so face, outfit, pose and framing
stay the same. An outfit change mid-story is also an edit of the current neutral picture (a new look whose parent
is the old one). The browser cuts each picture out of its key colour and sends the transparent copy back.
"""
import io
import re
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from mainapp import ai_client, messenger, sprites
from mainapp.models import EpisodeLook

CORE_MOODS = ["neutral", "happy", "sad", "angry", "surprised", "flustered"]
MAX_MOODS = 16
SETTINGS = ("canon", "modern")

# Key colours for the flat background the browser cuts out. A colour the character wears or has in their
# hair is skipped, so the cut doesn't eat into them.
KEYS = {
    "green": ("#00FF00", "pure chroma-key green",
              ("green", "emerald", "jade", "lime", "olive", "mint", "teal", "зелен", "смарагд")),
    "magenta": ("#FF00FF", "pure magenta",
                ("pink", "magenta", "purple", "violet", "fuchsia", "lilac", "lavender", "rose", "рожев", "фіолет", "бузк")),
    "blue": ("#0040FF", "pure saturated blue",
             ("blue", "navy", "azure", "cyan", "cobalt", "sapphire", "indigo", "teal", "блакит", "синій", "синя")),
}

# Moods the storyteller may name that a look doesn't have yet: the closest one it does have.
NEAR = {
    "happy": ("smiling", "smile", "laughing", "excited", "amused", "pleased", "cheerful", "joyful", "glad",
              "playful", "smug", "flirty", "delighted", "warm", "relieved", "content"),
    "sad": ("hurt", "crying", "upset", "tearful", "melancholy", "lonely", "disappointed", "worried", "guilty",
            "tired", "regretful", "gloomy"),
    "angry": ("annoyed", "furious", "irritated", "frustrated", "mad", "disgusted", "stern", "cold", "defiant",
              "determined", "scheming"),
    "surprised": ("shocked", "startled", "stunned", "scared", "confused", "afraid", "alarmed", "curious"),
    "flustered": ("embarrassed", "blushing", "shy", "nervous", "awkward", "bashful", "lovestruck"),
    "neutral": ("calm", "thoughtful", "serious", "bored", "focused", "listening", "pensive", "composed"),
}


def setting_for(character):
    """The setting an episode entered from the phone uses for this character."""
    return "modern" if messenger.char_profile(character).get("mode") == "modern_au" else "canon"


def pick_key(text):
    """The key colour that clashes least with the words describing the character and outfit."""
    low = str(text or "").lower()
    return min(KEYS, key=lambda k: sum(low.count(w) for w in KEYS[k][2]))


def _subject_name(user, character):
    if character is None:
        return messenger.user_profile(user).get("display_name") or user.username
    return messenger.char_profile(character)["display_name"]


def _appearance(user, character):
    if character is None:
        return str(getattr(user, "persona_description", "") or "")[:600]
    prof = messenger.char_profile(character)
    return str(prof.get("appearance_notes") or (character.description or ""))[:600]


def references(user, character, setting):
    """Identity pictures for a new look's neutral picture: canon from the stage sprite, modern from the phone.

    The phone pictures are only read here, as references; nothing is written back to them.
    """
    if character is None:
        picks = [getattr(user, "persona_photo_neutral", None)]
        if setting == "modern":
            picks.insert(0, messenger.user_profile(user).get("avatar_url"))
    elif setting == "modern":
        prof = messenger.char_profile(character)
        picks = [prof.get("neutral_url"), *(prof.get("extra_refs") or [])[:3], character.photo_neutral]
    else:
        picks = [character.photo_neutral, messenger.char_profile(character).get("neutral_url")]
    refs = []
    for pick in picks:
        image = messenger._read_storage_image(pick) if pick else None
        if image:
            refs.append(image)
        if len(refs) == 4:
            break
    return refs


def _store(look, mood, data, kind="raw"):
    name = f"episode_looks/{look.author_id}/{look.pk}-{mood.replace(' ', '-')}-{kind}-{uuid.uuid4().hex[:6]}.png"
    return default_storage.save(name, ContentFile(data))


def _drop(path):
    if path:
        try:
            default_storage.delete(path)
        except Exception:
            pass


def _key_line(look):
    hexcode, words, _ = KEYS.get(look.key_colour, KEYS["green"])
    return (f"Background: one solid, completely flat {words} ({hexcode}) filling everything behind the character: "
            "no gradient, no shadow, no floor, no props, no text. That colour must not appear on the character.")


def _base_prompt(user, character, look):
    who = _subject_name(user, character)
    era = ("present-day, modern clothes" if look.setting == "modern"
           else "their own world and era, as in the references")
    return (
        f"A visual-novel character sprite of {who} ({era}).\n"
        "Framing: from mid-thigh up, standing upright, body turned slightly toward the viewer, arms relaxed, "
        "centred, the whole head and hair inside the picture with a little space above. Tall portrait picture.\n"
        "Expression: calm and neutral, looking at the viewer.\n"
        f"Outfit, exactly and only this: {look.outfit or 'the outfit in the references'}. "
        "The outfit overrides the clothes in the references; it never changes who they are.\n"
        "Keep the face, hair, eye colour, body and art style of the reference pictures.\n"
        f"Appearance notes: {_appearance(user, character)}\n"
        + _key_line(look)
    )


def _mood_prompt(look, mood):
    return (
        "Edit this exact picture. Change only the facial expression (eyebrows, eyes, mouth) and, if the mood needs it, "
        f"the hands and shoulders, so the character looks: {mood}.\n"
        "Keep everything else identical: framing, pose, outfit, hair, colours, lighting, art style, picture size. "
        + _key_line(look)
    )


def _restyle_prompt(look, outfit):
    return (
        f"Edit this exact picture. Change only the clothes, to exactly this: {outfit}.\n"
        "Keep everything else identical: face, expression, hair, body, pose, framing, art style, picture size. "
        + _key_line(look)
    )


def _image(user, prompt, refs):
    data, cost = messenger.make_picture(user, prompt, references=refs)
    return data, float(cost or 0.0)


def _base_image(look):
    entry = (look.moods or {}).get("neutral") or {}
    image = None
    if entry.get("raw"):
        try:
            with default_storage.open(entry["raw"], "rb") as handle:
                image = (handle.read(), "image/png")
        except Exception:
            image = None
    if not image:
        raise ai_client.AIError("This look has no neutral picture to edit. Make the look again.")
    return image


def clean_mood(mood):
    return sprites.clean_name(mood) or "neutral"


def create(user, character, setting, name, outfit, moods=None):
    """A new look: the neutral picture from references, then each mood as an edit of it.

    Returns (look, cost, errors). A failed neutral picture raises AIError and leaves nothing behind; a failed
    mood is listed in errors and can be made again from the look later.
    """
    setting = setting if setting in SETTINGS else "canon"
    name = " ".join(str(name or "").split())[:60] or "Everyday"
    outfit = str(outfit or "").strip()[:1200]
    refs = references(user, character, setting)
    if not refs:
        raise ai_client.AIError("There's no picture of them to work from yet: add a "
                                + ("phone portrait" if setting == "modern" else "neutral sprite") + " first.")
    look = EpisodeLook.objects.create(author=user, character=character, setting=setting, name=name, outfit=outfit,
                                      key_colour=pick_key(_appearance(user, character) + " " + outfit))
    try:
        data, cost = _image(user, _base_prompt(user, character, look), refs)
    except Exception:
        look.delete()
        raise
    look.moods = {"neutral": {"raw": _store(look, "neutral", data), "cut": ""}}
    look.save(update_fields=["moods"])
    more, errors = add_moods(user, look, [m for m in (moods or CORE_MOODS) if clean_mood(m) != "neutral"])
    return look, cost + more, errors


def add_moods(user, look, moods):
    """Make the missing moods as edits of the neutral picture. Returns (cost, errors)."""
    cost, errors = 0.0, []
    base = _base_image(look)
    for mood in moods:
        mood = clean_mood(mood)
        if mood in look.moods:
            continue
        if len(look.moods) >= MAX_MOODS:
            errors.append(f"{MAX_MOODS} moods is the most a look keeps.")
            break
        try:
            data, spent = _image(user, _mood_prompt(look, mood), [base])
        except ai_client.AIError as exc:
            errors.append(f"{mood}: {exc}")
            continue
        cost += spent
        look.moods = {**look.moods, mood: {"raw": _store(look, mood, data), "cut": ""}}
        look.save(update_fields=["moods", "updated"])
    return cost, errors


def restyle(user, look, name, outfit, moods=None):
    """An outfit change: a new look whose neutral picture is the old one with only the clothes edited.

    The new look makes the same moods the old one had (or `moods`). Returns (new look, cost, errors).
    """
    outfit = str(outfit or "").strip()[:1200]
    if not outfit:
        raise ai_client.AIError("Describe the new outfit first.")
    base = _base_image(look)
    new = EpisodeLook.objects.create(author=look.author, character=look.character, setting=look.setting,
                                     name=" ".join(str(name or "").split())[:60] or f"{look.name} (changed)",
                                     outfit=outfit, key_colour=look.key_colour, parent=look)
    try:
        data, cost = _image(user, _restyle_prompt(look, outfit), [base])
    except Exception:
        new.delete()
        raise
    new.moods = {"neutral": {"raw": _store(new, "neutral", data), "cut": ""}}
    new.save(update_fields=["moods"])
    wanted = [m for m in (moods or list(look.moods)) if clean_mood(m) != "neutral"]
    more, errors = add_moods(user, new, wanted)
    return new, cost + more, errors


def save_cut(look, mood, data):
    """Keep the browser's transparent copy of one mood. Raises ValueError when it isn't a usable cut-out."""
    from PIL import Image
    mood = clean_mood(mood)
    entry = (look.moods or {}).get(mood)
    if not entry:
        raise ValueError("That mood isn't in this look.")
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("The cut-out is too large.")
    try:
        image = Image.open(io.BytesIO(data))
        image.verify()
        image = Image.open(io.BytesIO(data))
    except Exception:
        raise ValueError("The cut-out isn't a picture.")
    if image.format != "PNG" or "A" not in image.getbands():
        raise ValueError("The cut-out must be a PNG with transparency.")
    _drop(entry.get("cut"))
    look.moods = {**look.moods, mood: {**entry, "cut": _store(look, mood, data, "cut")}}
    look.save(update_fields=["moods", "updated"])
    return default_storage.url(look.moods[mood]["cut"])


def remove_mood(look, mood):
    mood = clean_mood(mood)
    if mood == "neutral":
        raise ValueError("The neutral picture is the base of the look; delete the whole look instead.")
    entry = (look.moods or {}).get(mood)
    if entry:
        _drop(entry.get("raw"))
        _drop(entry.get("cut"))
        look.moods = {k: v for k, v in look.moods.items() if k != mood}
        look.save(update_fields=["moods", "updated"])


def delete(look):
    for entry in (look.moods or {}).values():
        _drop(entry.get("raw"))
        _drop(entry.get("cut"))
    look.delete()


def nearest(look, mood):
    """The mood this look will show for `mood`: itself, its closest kept mood, or neutral."""
    mood = clean_mood(mood)
    have = (look.moods or {}) if look else {}
    if mood in have:
        return mood
    for core, near in NEAR.items():
        if (mood == core or any(re.search(rf"\b{re.escape(w)}", mood) for w in near)) and core in have:
            return core
    return "neutral"


def url(look, mood):
    """(picture url, mood shown) for the stage; the cut-out when the browser has made it."""
    if not look:
        return "", clean_mood(mood)
    shown = nearest(look, mood)
    entry = (look.moods or {}).get(shown) or {}
    path = entry.get("cut") or entry.get("raw")
    return (default_storage.url(path) if path else ""), shown


def pack(look):
    moods = {}
    for mood, entry in (look.moods or {}).items():
        moods[mood] = {"url": default_storage.url(entry.get("cut") or entry["raw"]) if entry.get("raw") else "",
                       "raw_url": default_storage.url(entry["raw"]) if entry.get("raw") else "",
                       "cut": bool(entry.get("cut"))}
    return {"id": look.pk, "name": look.name, "setting": look.setting, "outfit": look.outfit,
            "character_slug": look.character.slug if look.character_id else "user",
            "key_colour": look.key_colour, "key_hex": KEYS.get(look.key_colour, KEYS["green"])[0],
            "parent_id": look.parent_id, "moods": moods,
            "needs_cut": sorted(m for m, e in (look.moods or {}).items() if not e.get("cut"))}


def owned(user, look_id):
    try:
        return EpisodeLook.objects.select_related("character").get(author=user, pk=int(look_id))
    except (EpisodeLook.DoesNotExist, TypeError, ValueError):
        raise ValueError("That look isn't yours or no longer exists.")


def looks_for(user, character, setting):
    return list(EpisodeLook.objects.filter(author=user, character=character, setting=setting)
                .select_related("character"))


def default_look(user, character, setting):
    """The look an episode starts with when none is picked: the most recently used one."""
    return EpisodeLook.objects.filter(author=user, character=character, setting=setting).first()
