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


POSE = ("Pose: standing upright, facing the viewer with the body turned very slightly, both arms hanging relaxed at "
        "the sides, hands empty and relaxed. Exactly two arms and two hands, each joined to its shoulder. No props, no "
        "crossed or raised arms, nothing held.")


def _base_prompt(user, character, look):
    who = _subject_name(user, character)
    era = ("present-day, modern clothes" if look.setting == "modern"
           else "their own world and era, as in the references")
    seen = identity_line(look.identity)
    return (
        f"A visual-novel character sprite of {who} ({era}).\n"
        "The attached pictures show this exact person. Draw the same face, hair, eyes, skin, body and art style. "
        "If anything written below disagrees with the pictures about how they look, the pictures win.\n"
        + (f"What the reference shows: {seen}\n" if seen else "")
        + "Framing: from the knees up, centred, the whole head and hair inside the picture with a little space above. "
        "Tall portrait picture.\n"
        + POSE + "\n"
        "Expression: calm and neutral, looking at the viewer.\n"
        f"Outfit, exactly and only this (it replaces the clothes in the pictures, never who they are): "
        f"{look.outfit or 'the outfit in the references'}.\n"
        + _key_line(look)
    )


def _mood_prompt(look, mood):
    return (
        f"Edit this exact picture. Change only the face (eyebrows, eyes, mouth) so the character looks: {mood}.\n"
        "Do not move, add, remove or redraw arms, hands, shoulders or the body: everything below the chin stays "
        "pixel for pixel as it is. Keep the framing, outfit, hair, colours, lighting, art style and picture size. "
        + _key_line(look)
    )


def _restyle_prompt(look, outfit):
    return (
        f"Edit this exact picture. Change only the clothes, to exactly this: {outfit}.\n"
        "Keep everything else identical: face, expression, hair, body, the same pose with the arms and hands exactly "
        "where they are (two arms, two hands), framing, art style, picture size. "
        + _key_line(look)
    )


# ---------- what Bulba sees, and Bulba's check of a drawing ----------

IDENTITY_FIELDS = ("hair", "eyes", "skin", "face", "build", "marks", "art_style")
IDENTITY_PROMPT = (
    "Look at this picture of a character and write down only what you can see, for an artist who has to draw the "
    "same person again. Short, concrete phrases; no guessing, no personality, no story. Return ONLY JSON: "
    '{"hair": "colour, length, style, fringe or parting", "eyes": "colour", "skin": "tone", '
    '"face": "shape and anything distinctive", "build": "body type", "marks": "glasses, scars, freckles, piercings, '
    'tattoos, or \'\'", "art_style": "medium, line work, shading, palette (e.g. anime cel shading)"}. '
    "Write '' for anything you can't see."
)


def identity(user, refs):
    """{field: words} from the first reference picture; {} if it can't be looked at. A text call, no picture made."""
    from mainapp.bulba import vision
    if not refs:
        return {}
    try:
        data_url, _ = vision.prepare(refs[0][0])
        text, _ = vision.describe(user, data_url, prompt=IDENTITY_PROMPT)
    except (ValueError, ai_client.AIError):
        return {}
    raw = messenger._read_json(text)
    return {k: " ".join(str(raw.get(k) or "").split())[:200] for k in IDENTITY_FIELDS if str(raw.get(k) or "").strip()}


def identity_line(seen):
    seen = seen if isinstance(seen, dict) else {}
    names = {"hair": "hair", "eyes": "eyes", "skin": "skin", "face": "face", "build": "build", "marks": "marks",
             "art_style": "art style"}
    return "; ".join(f"{names[k]}: {seen[k]}" for k in IDENTITY_FIELDS if seen.get(k))


REVIEW_PROMPT = (
    "The first picture{plural} the reference of a character. The LAST picture is a new drawing that must show the "
    "same character from the knees up, standing with both arms at the sides, in this outfit: {outfit}.\n"
    "Check only the LAST picture. Count carefully. Return ONLY JSON: "
    '{{"arms": <number of arms you see>, "hands": <number of hands you see>, "extra_or_merged_limbs": true|false, '
    '"fingers_ok": true|false, "same_person": true|false, "outfit_missing": ["listed items you cannot see"], '
    '"background_plain": true|false, "notes": "one short sentence on anything else wrong, or \'\'"}}\n'
    "same_person: face, hair, eye colour and art style match the reference. Leave out of outfit_missing anything "
    "that would be below the knees. background_plain: one flat colour behind the character."
)


def review(user, look, refs, drawn):
    """Bulba's check of a drawn neutral picture against the reference: arms, hands, same person, outfit, background.

    Returns {"ok": True/False/None, "issues": [plain sentences]}; None when the picture couldn't be checked.
    A text call with pictures attached; nothing is redrawn.
    """
    from mainapp.bulba import vision
    import base64
    try:
        model, _ = vision.looker(user)
        content = [{"type": "text", "text": REVIEW_PROMPT.format(
            plural=" is" if len(refs[:2]) <= 1 else "s are", outfit=look.outfit or "as in the reference")}]
        for raw, mime in [*refs[:2], drawn]:
            data_url, _ = vision.prepare(raw)
            content.append({"type": "image_url", "image_url": {"url": data_url}})
        text = ai_client.complete(user, "bulba", [{"role": "user", "content": content}], model=model,
                                  max_tokens=2500, temperature=0.1)
    except (ValueError, ai_client.AIError):
        return {"ok": None, "issues": ["Bulba couldn't look at this picture to check it."]}
    raw = messenger._read_json(text or "")
    if not raw:
        return {"ok": None, "issues": ["Bulba couldn't read this picture to check it."]}
    issues = []
    num = lambda v: int(v) if str(v).strip().isdigit() else None
    arms, hands = num(raw.get("arms")), num(raw.get("hands"))
    if arms is not None and arms > 2:
        issues.append(f"{arms} arms.")
    if hands is not None and hands > 2:
        issues.append(f"{hands} hands.")
    if raw.get("extra_or_merged_limbs") is True:
        issues.append("Extra or merged limbs.")
    if raw.get("fingers_ok") is False:
        issues.append("The fingers look wrong.")
    if raw.get("same_person") is False:
        issues.append("Doesn't look like the same person as the reference.")
    missing = [str(m)[:80] for m in (raw.get("outfit_missing") or []) if str(m).strip()][:6] if isinstance(raw.get("outfit_missing"), list) else []
    if missing:
        issues.append("Missing from the outfit: " + ", ".join(missing) + ".")
    if raw.get("background_plain") is False:
        issues.append("The background isn't plain, so the cut-out may be rough.")
    note = " ".join(str(raw.get("notes") or "").split())[:200]
    if note and issues:
        issues.append(note)
    return {"ok": not issues, "issues": issues}


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
    seen = identity(user, refs)
    look = EpisodeLook.objects.create(author=user, character=character, setting=setting, name=name, outfit=outfit,
                                      identity=seen, key_colour=pick_key(identity_line(seen) + " " + outfit))
    try:
        data, cost = _image(user, _base_prompt(user, character, look), refs)
    except Exception:
        look.delete()
        raise
    look.moods = {"neutral": {"raw": _store(look, "neutral", data), "cut": ""}}
    look.review = review(user, look, refs, (data, "image/png"))
    look.save(update_fields=["moods", "review"])
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
                                     outfit=outfit, key_colour=look.key_colour, parent=look, identity=look.identity)
    try:
        data, cost = _image(user, _restyle_prompt(look, outfit), [base])
    except Exception:
        new.delete()
        raise
    new.moods = {"neutral": {"raw": _store(new, "neutral", data), "cut": ""}}
    new.review = review(user, new, [base], (data, "image/png"))
    new.save(update_fields=["moods", "review"])
    wanted = [m for m in (moods or list(look.moods)) if clean_mood(m) != "neutral"]
    more, errors = add_moods(user, new, wanted)
    return new, cost + more, errors


def save_cut(look, mood, data, body_changed=None):
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
    kept = {**entry, "cut": _store(look, mood, data, "cut")}
    kept.pop("flag", None)
    if mood != "neutral" and body_changed is not None and body_changed > BODY_CHANGE_LIMIT:
        # A mood is an edit of the face only; a different outline means an arm, hand or pose changed too.
        kept["flag"] = f"The body changed from the neutral picture ({round(body_changed * 100)}% of the outline): " \
                       "an extra or moved arm or hand, or a different pose."
    look.moods = {**look.moods, mood: kept}
    look.save(update_fields=["moods", "updated"])
    return default_storage.url(look.moods[mood]["cut"])


BODY_CHANGE_LIMIT = 0.03  # share of the outline a face-only edit may change (face edits measure ~0.1%; a third arm ~5%)


def redraw_mood(user, look, mood):
    """Draw one mood again from the neutral picture. Returns cost."""
    mood = clean_mood(mood)
    if mood == "neutral":
        raise ValueError("The neutral picture is the base of every mood: redraw the whole look instead.")
    entry = (look.moods or {}).get(mood)
    if not entry:
        raise ValueError("That mood isn't in this look.")
    data, cost = _image(user, _mood_prompt(look, mood), [_base_image(look)])
    _drop(entry.get("raw"))
    _drop(entry.get("cut"))
    look.moods = {**look.moods, mood: {"raw": _store(look, mood, data), "cut": ""}}
    look.save(update_fields=["moods", "updated"])
    return cost


def redraw_look(user, look):
    """Draw the neutral picture again (from the references, or from the parent look for an outfit change), check it,
    then every mood again from it. Returns (cost, errors)."""
    if look.parent_id and look.parent and (look.parent.moods or {}).get("neutral"):
        refs = [_base_image(look.parent)]
        data, cost = _image(user, _restyle_prompt(look.parent, look.outfit), refs)
    else:
        refs = references(user, look.character, look.setting)
        if not refs:
            raise ai_client.AIError("There's no picture of them to work from any more.")
        if not look.identity:
            look.identity = identity(user, refs)
        data, cost = _image(user, _base_prompt(user, look.character, look), refs)
    moods = [m for m in (look.moods or {}) if m != "neutral"]
    for entry in (look.moods or {}).values():
        _drop(entry.get("raw"))
        _drop(entry.get("cut"))
    look.moods = {"neutral": {"raw": _store(look, "neutral", data), "cut": ""}}
    look.review = review(user, look, refs, (data, "image/png"))
    look.save(update_fields=["moods", "review", "identity", "updated"])
    more, errors = add_moods(user, look, moods)
    return cost + more, errors


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
    # A mood the body check flagged (an extra arm, a new pose) stays off the stage until it's redrawn.
    have = {m: e for m, e in ((look.moods or {}) if look else {}).items() if m == "neutral" or not e.get("flag")}
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
                       "cut": bool(entry.get("cut")), "flag": entry.get("flag", "")}
    return {"id": look.pk, "name": look.name, "setting": look.setting, "outfit": look.outfit,
            "character_slug": look.character.slug if look.character_id else "user",
            "key_colour": look.key_colour, "key_hex": KEYS.get(look.key_colour, KEYS["green"])[0],
            "parent_id": look.parent_id, "moods": moods, "identity": identity_line(look.identity),
            "review": look.review or {},
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
