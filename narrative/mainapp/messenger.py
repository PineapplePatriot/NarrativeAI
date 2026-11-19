"""
Telegram-style Messenger & Digital Screen Hub (Phase F).

Lives inside the Screen Hub (`/main/screen/`), where the Messenger is the first app alongside
Moments (profile status/stories feed) and Notes & Files.

Key capabilities:
- 1-on-1 and multi-character Group Chats (`MessengerThread`), separate from narrative roleplay chats.
- Separate `Character.messenger_profile` so modernizing a character (Modern AU) or setting a texting
  scenario never overwrites their main roleplay card. Bulba can draft the Modern AU profile automatically,
  and every field is editable by hand.
- Frankenstein-inspired Texting Preset & safeguards: zero stage directions (`*sighs*`), natural multi-bubble
  bursts, distinct texting fingerprints from each character's Voice & Temperament sections, anti-therapy-speak,
  anti-occupation-metaphor spam, and strict phone-medium knowledge limits.
- Real-time clock & events: passes actual time of day, day of the week, real time elapsed since the last text,
  and scheduled real-time events.
- Rich Telegram media & formatting: reactions, stickers (character mood sprites + built-in + custom),
  in-world files, ElevenLabs voice notes with `[ >A ]` transcript toggle, Nano Banana casual/tease photos
  using the character's neutral sprite as reference, and profile/bio/status updates by both characters and user.
"""
import base64
import json
import logging
import re
import time
import uuid
from datetime import datetime
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from mainapp import ai_client, card_sections, chats, sprites, story_memory, voice, writing_quality
from mainapp.models import Character, ChatSettings, MessengerThread

log = logging.getLogger(__name__)

WALLPAPERS = {
    "tg-night": {"name": "Telegram Night", "bg": "linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)"},
    "tg-emerald": {"name": "Emerald Dusk", "bg": "linear-gradient(135deg, #06281e 0%, #0f3d2e 50%, #071f18 100%)"},
    "tg-twilight": {"name": "Cyber Twilight", "bg": "linear-gradient(135deg, #16113a 0%, #2a1b4e 50%, #120d2b 100%)"},
    "tg-sakura": {"name": "Midnight Sakura", "bg": "linear-gradient(135deg, #2b1222 0%, #3d1a30 50%, #1c0b16 100%)"},
    "tg-amber": {"name": "Warm Espresso", "bg": "linear-gradient(135deg, #241710 0%, #362218 50%, #1a100b 100%)"},
    "tg-slate": {"name": "Minimal Slate", "bg": "linear-gradient(135deg, #18181b 0%, #27272a 100%)"},
    "tg-light": {"name": "Daylight Sky", "bg": "linear-gradient(135deg, #dbeafe 0%, #eff6ff 50%, #e0e7ff 100%)", "light": True},
}

# 🖼️ The picture model for the messenger's photos and references ("" = the app's default, Nano Banana); all take
# reference pictures. A model OpenRouter stops listing falls back to the default.
PICTURE_MODELS = {
    "microsoft/mai-image-2.7": "MAI-Image-2.7 (Microsoft): precise, consistent",
    "microsoft/mai-image-2.7-flash": "MAI-Image-2.7 Flash (Microsoft): faster, cheaper",
}


def make_picture(user, prompt, references=None):
    """One picture for the messenger, on the user's chosen picture model (their profile tab)."""
    model = user_profile(user).get("image_model") or None
    profile = ai_client.main_profile(user)
    if model and profile is not None and profile.provider == ai_client.ConnectionProfile.PROVIDER_OPENROUTER:
        listed = [m["id"] for m in ai_client.image_models()]
        if listed and model not in listed:
            log.warning("messenger: picture model %s isn't on OpenRouter's list; using the default", model)
            model = None
    return ai_client.generate_image(user, prompt, references=references, model=model)


# 🎨 Ready chat themes (bubbles, accent, a matching background), per chat; "" = the app's purple
THEMES = {"classic": "Telegram classic", "forest": "Forest", "rose": "Rose", "sepia": "Sepia evening"}


REACTIONS = ["❤️", "🔥", "👍", "😂", "😮", "😢", "👀", "🎉", "😡", "🤔"]

BUILT_IN_STICKERS = [
    {"id": "bulba_wave", "pack": "Bulba & Friends", "name": "Bulba Wave", "emoji": "🥔👋", "label": "Hey there!"},
    {"id": "bulba_judge", "pack": "Bulba & Friends", "name": "Bulba Judging", "emoji": "🥔😒", "label": "Seriously?"},
    {"id": "bulba_hype", "pack": "Bulba & Friends", "name": "Bulba Hype", "emoji": "🥔✨", "label": "Let's go!"},
    {"id": "bulba_tea", "pack": "Bulba & Friends", "name": "Bulba Sipping Tea", "emoji": "🥔☕", "label": "Spill the tea"},
    {"id": "tomato_splat", "pack": "Bulba & Friends", "name": "Tomato Splat", "emoji": "🍅💥", "label": "SPLAT!"},
    {"id": "tomato_love", "pack": "Bulba & Friends", "name": "Golden Tomato", "emoji": "🍅💛", "label": "Approved"},
    {"id": "cat_stare", "pack": "Bulba & Friends", "name": "Midnight Cat", "emoji": "🐈‍⬛👀", "label": "Watching you"},
    {"id": "coffee_sos", "pack": "Bulba & Friends", "name": "Need Coffee", "emoji": "☕🆘", "label": "Too early"},
]

# Speaker name colors for group chats (Telegram palette)
NAME_COLORS = ["#60a5fa", "#f472b6", "#34d399", "#fbbf24", "#a78bfa", "#fb7185", "#38bdf8", "#f97316"]


# ---------------------------------------------------------------------------
# User & Character Messenger Profiles
# ---------------------------------------------------------------------------

def _default_handle(name):
    cleaned = re.sub(r"[^a-z0-9_]+", "_", str(name or "user").lower()).strip("_")
    return "@" + (cleaned[:24] or "stranger")


def user_profile(user):
    """The signed-in user's Messenger profile and Screen Hub settings (kept on ChatSettings.appearance['messenger'])."""
    from mainapp.cards import user_name
    settings_obj = ChatSettings.objects.filter(author=user).first()
    raw = ((settings_obj.appearance or {}).get("messenger") if settings_obj else None) or {}
    raw = raw if isinstance(raw, dict) else {}
    display_name = str(raw.get("display_name") or user_name(user) or user.username).strip()[:80]
    avatar = ""
    if getattr(user, "persona_photo_neutral", None) and user.persona_photo_neutral:
        try:
            avatar = user.persona_photo_neutral.url
        except Exception:
            avatar = ""
    if not avatar and getattr(user, "photo", None) and user.photo:
        try:
            avatar = user.photo.url
        except Exception:
            avatar = ""
    return {
        "display_name": display_name,
        "handle": str(raw.get("handle") or _default_handle(display_name))[:32],
        "bio": str(raw.get("bio") or "").strip()[:240],
        "status_emoji": str(raw.get("status_emoji") or "✨").strip()[:12],
        "avatar_url": str(raw.get("avatar_url") or avatar),
        "stories": [s for s in (raw.get("stories") or []) if isinstance(s, dict)][:30],
        "custom_stickers": [s for s in (raw.get("custom_stickers") or []) if isinstance(s, dict) and s.get("url")][-200:],
        "notes": [n for n in (raw.get("notes") or []) if isinstance(n, dict)][:100],
        "browser_notifications": bool(raw.get("browser_notifications", False)),
        "in_app_toasts": bool(raw.get("in_app_toasts", True)),
        "spontaneous_texts": bool(raw.get("spontaneous_texts", False)),
        "spontaneous_minutes": max(2, min(1440, int(raw.get("spontaneous_minutes") or 15))),
        "auto_photos": bool(raw.get("auto_photos", False)),
        "auto_voice": bool(raw.get("auto_voice", False)),
        "auto_statuses": bool(raw.get("auto_statuses", True)),  # ✨ characters post statuses on their own now and then
        "default_bg": raw.get("default_bg") if raw.get("default_bg") in WALLPAPERS else "tg-night",
        "image_model": raw.get("image_model") if raw.get("image_model") in PICTURE_MODELS else "",
    }


def save_user_profile(user, updates):
    """Save changes to the user's Messenger profile or settings."""
    current = user_profile(user)
    if not isinstance(updates, dict):
        return current
    for str_key, limit in (("display_name", 80), ("handle", 32), ("bio", 240), ("status_emoji", 12), ("avatar_url", 500)):
        if str_key in updates and updates[str_key] is not None:
            val = str(updates[str_key]).strip()[:limit]
            if str_key == "handle" and val and not val.startswith("@"):
                val = "@" + re.sub(r"[^a-zA-Z0-9_.]", "_", val)
            current[str_key] = val
    for bool_key in ("browser_notifications", "in_app_toasts", "spontaneous_texts", "auto_photos", "auto_voice", "auto_statuses"):
        if bool_key in updates:
            current[bool_key] = bool(updates[bool_key])
    if "spontaneous_minutes" in updates:
        try:
            current["spontaneous_minutes"] = max(2, min(1440, int(updates["spontaneous_minutes"])))
        except (TypeError, ValueError):
            pass
    if "image_model" in updates and (updates["image_model"] in PICTURE_MODELS or not updates["image_model"]):
        current["image_model"] = updates["image_model"] or ""
    if "default_bg" in updates and updates["default_bg"] in WALLPAPERS:
        current["default_bg"] = updates["default_bg"]
    for list_key in ("stories", "custom_stickers", "notes"):
        if isinstance(updates.get(list_key), list):
            current[list_key] = [x for x in updates[list_key] if isinstance(x, dict)][-200:] if list_key == "custom_stickers" \
                else [x for x in updates[list_key] if isinstance(x, dict)][:100]

    settings_obj, _ = ChatSettings.objects.get_or_create(author=user)
    app = dict(settings_obj.appearance or {})
    app["messenger"] = current
    settings_obj.appearance = app
    settings_obj.save(update_fields=["appearance"])
    return current


def char_avatar(character):
    """Best avatar URL for a character."""
    raw = getattr(character, "messenger_profile", None) or {}
    if isinstance(raw, dict):
        if raw.get("avatar_url"):
            return str(raw["avatar_url"])
        if raw.get("neutral_url"):
            return str(raw["neutral_url"])
    if getattr(character, "photo_neutral", None) and character.photo_neutral:
        try:
            return character.photo_neutral.url
        except Exception:
            pass
    return ""


def char_neutral_url(character):
    """Primary neutral reference image URL for a character."""
    raw = getattr(character, "messenger_profile", None) or {}
    if isinstance(raw, dict) and raw.get("neutral_url"):
        return str(raw["neutral_url"])
    if getattr(character, "photo_neutral", None) and character.photo_neutral:
        try:
            return character.photo_neutral.url
        except Exception:
            pass
    if isinstance(raw, dict) and raw.get("avatar_url"):
        return str(raw["avatar_url"])
    return ""


def char_profile(character):
    """Normalized Messenger profile for a character. Never mutates their main roleplay card."""
    raw = getattr(character, "messenger_profile", None)
    raw = raw if isinstance(raw, dict) else {}
    mode = raw.get("mode") if raw.get("mode") in ("canon", "modern_au") else "canon"
    default_bio = ""
    if character.personality:
        default_bio = character.personality.strip().splitlines()[0][:140]
    elif character.description:
        default_bio = character.description.strip().splitlines()[0][:140]
    default_app = ""
    if character.sections:
        cleaned = card_sections.clean(character.sections)
        if cleaned and cleaned.get("people"):
            default_app = (cleaned["people"][0].get("sections", {}).get("appearance") or {}).get("text") or ""
    if not default_app:
        default_app = (character.description or "")[:800]
    extra_refs = [str(u).strip()[:500] for u in (raw.get("extra_refs") or []) if str(u or "").strip()][:4]
    voice_id = str(raw.get("voice_id") or getattr(character, "eleven_voice_char_id", "") or "").strip()[:80]
    voice_model = str(raw.get("voice_model") or voice.OPENROUTER_TTS_MODEL_DEFAULT).strip()
    if voice_model not in voice.OPENROUTER_TTS_MODELS:
        voice_model = voice.OPENROUTER_TTS_MODEL_DEFAULT
    return {
        "mode": mode,
        "display_name": str(raw.get("display_name") or character.name).strip()[:100] or character.name,
        "handle": str(raw.get("handle") or _default_handle(character.slug or character.name))[:32],
        "bio": str(raw.get("bio") if "bio" in raw else default_bio).strip()[:240],
        "status_emoji": str(raw.get("status_emoji") or "💬").strip()[:12],
        "online_status": str(raw.get("online_status") or "online").strip()[:40],
        "modern_persona": str(raw.get("modern_persona") or "").strip()[:6000],
        "texting_style": str(raw.get("texting_style") or "").strip()[:2000],
        "scenario": str(raw.get("scenario") if "scenario" in raw else (character.scenario or "")).strip()[:4000],
        "first_text": str(raw.get("first_text") or "").strip()[:1000],
        "appearance_notes": str(raw.get("appearance_notes") if "appearance_notes" in raw else default_app).strip()[:2000],
        "art_style_notes": str(raw.get("art_style_notes") or "").strip()[:600],
        "neutral_url": char_neutral_url(character),
        "extra_refs": extra_refs,
        # 🎨 their own sticker pack in the texting look: [{"mood", "url"}] (else the roleplay moods are the stickers)
        "sticker_pack": [{"mood": str(s.get("mood") or "")[:30], "url": str(s.get("url") or "")[:500]}
                         for s in (raw.get("sticker_pack") or []) if isinstance(s, dict) and s.get("url")][:16],
        "voice_id": voice_id,
        "voice_model": voice_model,
        "share_memory": raw.get("share_memory", True) is not False,
        "avatar_url": char_avatar(character),
        "stories": [s for s in (raw.get("stories") or []) if isinstance(s, dict)][:30],
    }


def _read_json(text):
    """The JSON object in a model's answer: thinking (<think>...</think>) and ``` fences removed. An answer cut off
    halfway still gives the fields that came through whole. {} when there's nothing usable."""
    from mainapp import thinking
    _, text = thinking.split(text or "")
    text = re.sub(r"```(?:json)?", "", text or "")
    start = text.find("{")
    if start < 0:
        return {}
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj if isinstance(obj, dict) else {}
    except ValueError:
        pass
    pairs = re.findall(r'"([A-Za-z_]+)"\s*:\s*"((?:[^"\\]|\\.)*)"', text[start:], re.S)  # the whole "key": "value"s
    out = {}
    for key, raw in pairs:
        try:
            out[key] = json.loads('"' + raw + '"')
        except ValueError:
            out[key] = raw
    return out


def ask_json(user, prompt, need, max_tokens=1600, task="bulba", temperature=0.6):
    """One JSON answer from Bulba (or another task's model) for the messenger. Thinking models (Bulba runs on MiMo)
    get room to think on top of the answer; the answer is read leniently (_read_json); if it still lacks the `need`
    fields, one more try asks for the JSON alone, kept short. Raises AIError in plain words."""
    from mainapp import thinking
    _, model = ai_client.resolve(user, task)
    thinks = thinking.needs_leash(model, "default")
    last = ""
    for attempt in range(2):
        text = prompt if attempt == 0 else (
            prompt + "\n\nIMPORTANT: answer with the JSON object only: no thinking out loud, no notes before or after it. "
                     "Keep every field brief so the whole object fits.")
        raw = ai_client.complete(user, task, [{"role": "user", "content": text}],
                                 max_tokens=max_tokens + (thinking.LEASH_ROOM if thinks else 0) + (800 if attempt else 0),
                                 temperature=temperature)
        last = raw or ""
        data = _read_json(last)
        if all(str(data.get(k) or "").strip() for k in need):
            return data
    log.warning("messenger: no usable JSON from %s (%s chars): %r", task, len(last), last[:300])
    raise ai_client.AIError("Bulba's answer came back cut off or empty twice. Try again in a moment; if it keeps "
                            "happening, the model may be busy.")


def is_set_up(character):
    """Whether the character has been adapted for texting (Bulba's modernize, or written by hand): a texting persona
    or texting style of their own. If not, the chat offers Bulba's setup."""
    raw = character.messenger_profile if isinstance(getattr(character, "messenger_profile", None), dict) else {}
    return bool(str(raw.get("modern_persona") or "").strip() or str(raw.get("texting_style") or "").strip())


def redraw_setup_look(user, character, outfit=""):
    """🥔 Bulba's second setup step: the character drawn again for this texting setup (modern clothes, say), from
    their current pictures so the face stays theirs. The new portrait becomes their messenger picture (neutral and
    avatar) with one waist-up reference of the outfit; the main roleplay card's pictures are left alone.
    Returns (profile, cost)."""
    prof = char_profile(character)
    outfit = str(outfit or "").strip()[:600]
    if outfit:  # their outfit for this setup goes into the notes every later photo reads
        base = re.sub(r"\n?Outfit in this setup:.*$", "", prof.get("appearance_notes") or "", flags=re.S).strip()
        prof = save_char_profile(character, {"appearance_notes": (base + "\nOutfit in this setup: " + outfit).strip()})
    refs = load_character_references(character)
    style = prof.get("art_style_notes") or "expressive digital character illustration, clean lines, rich atmospheric lighting"
    setting = "a modern-day setting" if prof.get("mode") == "modern_au" else "their own world"
    look = (prof.get("appearance_notes") or character.description or "")[:1200]
    same = ("Keep them the SAME person as in the reference pictures: same face, hair, eyes, skin and build. "
            if refs else "")
    cost, out = 0.0, {}
    for key, shot in (("neutral", "a clean chest-up three-quarter portrait, calm in-character expression"),
                      ("outfit", "a relaxed waist-up candid shot that shows the whole outfit and their posture")):
        prompt = (f"{same}Draw {character.name} as they are in {setting}, dressed for it. {shot.capitalize()}.\n"
                  f"How they look now: {look}\nArt style: {style}.")
        img, c = make_picture(user, prompt, references=refs)
        cost += float(c or 0)
        saved = default_storage.save(f"messenger/refs/{character.slug}-{key}-{uuid.uuid4().hex[:8]}.png", ContentFile(img))
        out[key] = default_storage.url(saved)
        if key == "neutral":
            refs = [(img, "image/png")] + refs[:3]  # the outfit shot follows the new portrait
    # the new look replaces the old references: kept, they'd pull every later photo back to the old outfit (a mask...)
    prof = save_char_profile(character, {"neutral_url": out["neutral"], "avatar_url": out["neutral"], "extra_refs": [out["outfit"]]})
    return prof, round(cost, 4)


def save_char_profile(character, updates):
    """Update `character.messenger_profile` without touching `character.description` or `character.scenario`."""
    current = char_profile(character)
    if not isinstance(updates, dict):
        return current
    if updates.get("mode") in ("canon", "modern_au"):
        current["mode"] = updates["mode"]
    for key, limit in (
        ("display_name", 100),
        ("handle", 32),
        ("bio", 240),
        ("status_emoji", 12),
        ("online_status", 40),
        ("modern_persona", 6000),
        ("texting_style", 2000),
        ("scenario", 4000),
        ("first_text", 1000),
        ("appearance_notes", 2000),
        ("art_style_notes", 600),
        ("neutral_url", 500),
        ("voice_id", 80),
        ("voice_model", 80),
        ("avatar_url", 500),
    ):
        if key in updates and updates[key] is not None:
            val = str(updates[key]).strip()[:limit]
            if key == "handle" and val and not val.startswith("@"):
                val = "@" + re.sub(r"[^a-zA-Z0-9_.]", "_", val)
            current[key] = val
    if current.get("voice_model") not in voice.OPENROUTER_TTS_MODELS:
        current["voice_model"] = voice.OPENROUTER_TTS_MODEL_DEFAULT
    if isinstance(updates.get("extra_refs"), list):
        current["extra_refs"] = [str(u).strip()[:500] for u in updates["extra_refs"] if str(u or "").strip()][:4]
    if isinstance(updates.get("sticker_pack"), list):
        current["sticker_pack"] = [{"mood": str(s.get("mood") or "")[:30], "url": str(s.get("url") or "")[:500]}
                                   for s in updates["sticker_pack"] if isinstance(s, dict) and s.get("url")][:16]
    if "share_memory" in updates:
        current["share_memory"] = bool(updates["share_memory"])
    if isinstance(updates.get("stories"), list):
        current["stories"] = [s for s in updates["stories"] if isinstance(s, dict)][:30]
    update_fields = ["messenger_profile"]
    if "voice_id" in updates and current.get("voice_id"):
        character.eleven_voice_char_id = current["voice_id"][:64]
        update_fields.append("eleven_voice_char_id")
    character.messenger_profile = current
    character.save(update_fields=update_fields)
    return current


STICKER_MOODS = ("happy", "smug", "angry", "sleepy", "shocked", "love", "crying", "thumbs up")


def make_sticker(user, character, mood):
    """🎨 One sticker of their pack, in their texting look: sticker style (bold white outline, plain background,
    big expression), the face kept from their texting pictures. Replaces that mood's sticker. Returns the profile."""
    mood = str(mood or "").strip().lower()[:30]
    if not mood:
        raise ValueError("Which mood?")
    prof = char_profile(character)
    refs = load_character_references(character)[:3]
    style = prof.get("art_style_notes") or "clean cute illustration"
    same = "The SAME person as in the reference pictures: same face, hair, eyes and outfit. " if refs else ""
    prompt = (f"A messenger sticker of {character.name}, feeling {mood}. {same}Sticker style: one figure (head and "
              f"shoulders or a small full body, slightly chibi), a big readable {mood} expression and pose, a thick white "
              f"outline around the figure, a flat plain light background, no text, no frame. Art style: {style}.\n"
              f"How they look: {(prof.get('appearance_notes') or character.description or '')[:600]}")
    img, _ = make_picture(user, prompt, references=refs)
    url = default_storage.url(default_storage.save(f"messenger/stickers/{character.slug}-{uuid.uuid4().hex[:8]}.png", ContentFile(img)))
    pack = [s for s in prof.get("sticker_pack") or [] if s["mood"] != mood] + [{"mood": mood, "url": url}]
    return save_char_profile(character, {"sticker_pack": pack})


def telegram_pack(user, link):
    """📥 A Telegram sticker pack by its link (t.me/addstickers/NAME) or name, into the user's own stickers, through
    the bot token in settings (TELEGRAM_BOT_TOKEN). Still and video stickers; animated .tgs ones are skipped (they
    need a special player). Returns (pack title, added, skipped)."""
    import os
    import requests
    from django.conf import settings
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise ValueError("Telegram packs need a bot token in the server's settings (TELEGRAM_BOT_TOKEN).")
    name = re.sub(r"^.*addstickers/", "", str(link or "").strip()).strip("/ ").split("?")[0]
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name):
        raise ValueError("That doesn't look like a sticker pack link (t.me/addstickers/…).")
    api = f"https://api.telegram.org/bot{token}"
    try:
        data = requests.get(f"{api}/getStickerSet", params={"name": name}, timeout=20).json()
    except (requests.RequestException, ValueError):
        raise ValueError("Telegram didn't answer. Try again in a moment.")
    if not data.get("ok"):
        raise ValueError("Telegram doesn't know that pack (check the link).")
    pack = data["result"]
    title = str(pack.get("title") or name)[:60]
    added, skipped = [], 0
    for st in (pack.get("stickers") or [])[:60]:
        if st.get("is_animated"):
            skipped += 1
            continue
        try:
            f = requests.get(f"{api}/getFile", params={"file_id": st["file_id"]}, timeout=20).json()
            path = f["result"]["file_path"]
            raw = requests.get(f"https://api.telegram.org/file/bot{token}/{path}", timeout=30).content
        except (requests.RequestException, ValueError, KeyError):
            skipped += 1
            continue
        ext = ".webm" if st.get("is_video") else ".webp"
        url = default_storage.url(default_storage.save(f"messenger/stickers/tg-{user.id}-{uuid.uuid4().hex[:8]}{ext}", ContentFile(raw)))
        added.append({"id": f"tg_{uuid.uuid4().hex[:8]}", "pack": title, "name": st.get("emoji") or "sticker",
                      "url": url, "video": bool(st.get("is_video"))})
    u_prof = user_profile(user)
    save_user_profile(user, {"custom_stickers": [*(u_prof.get("custom_stickers") or []), *added][-200:]})
    return title, len(added), skipped


def character_stickers(character):
    """All mood sprites of a character packaged as a Telegram Sticker Pack: their texting sticker pack when they
    have one (their texting look), else the roleplay card's mood pictures."""
    own = char_profile(character).get("sticker_pack") or []
    if own:
        return [{"id": f"char_{character.slug}_{s['mood'].replace(' ', '_')}", "pack": character.name, "char_slug": character.slug,
                 "mood": s["mood"], "name": f"{character.name} — {s['mood']}", "url": s["url"]} for s in own]
    pack = []
    for mood in sprites.BUILT_IN:
        field = getattr(character, f"photo_{mood}", None)
        if field:
            try:
                pack.append({
                    "id": f"char_{character.slug}_{mood}",
                    "pack": character.name,
                    "char_slug": character.slug,
                    "mood": mood,
                    "name": f"{character.name} — {mood.capitalize()}",
                    "url": field.url,
                })
            except Exception:
                continue
    for mood, url in sprites.extras(character).items():
        pack.append({
            "id": f"char_{character.slug}_{mood}",
            "pack": character.name,
            "char_slug": character.slug,
            "mood": mood,
            "name": f"{character.name} — {mood.capitalize()}",
            "url": url,
        })
    return pack


# ---------------------------------------------------------------------------
# Bulba Modern AU & Texting Profile Generator
# ---------------------------------------------------------------------------

MODERNIZE_PROMPT = """You are Bulba, preparing a character card for NarrativeAI's Telegram-style Messenger app.
The user wants to text with {char} ({mode_desc}).
Read {char}'s original roleplay card below and translate who they are into a sharp, specific Messenger profile
(without losing their temperament, flaws, goals, or how they treat {user}).

Rules:
- Keep their real personality, sharp edges, humour, and attitude toward {user} intact. Do NOT soften a villain or
  turn a reserved character into an eager texting buddy.
- If mode is "modern_au": adapt their fantasy/historical/sci-fi background and occupation into a fitting modern-day
  equivalent (e.g., an alchemist or mad scholar becomes a biomedical lab director or underground researcher; a knight
  becomes private security or a detective), while keeping their relationships and conflicts recognizable.
- If mode is "canon": keep their original world, just explain how/why they and {user} are texting on a device/communicator.
- Write a distinct `texting_style`: how they punctuate, capitalize, whether they send short bursts or dry single lines,
  whether they use emojis (or hate them), and their typical texting habits.
- CARD AUDIT SAFEGUARDS:
  1. Never use static time anchors ("tonight", "right now", "this evening") in `modern_persona` or `bio` — those fields
     stay active across many days of real-time chatting.
  2. Never use absolutes like "always", "constantly", or "every message" for quirks, and do NOT include verbatim quoted
     catchphrases in `texting_style` (models will parrot them every turn).
- Pick a fitting default ElevenLabs voice (`voice_id`) from this list:
  Female: sarah (soft/warm), alice (confident British), bella (gentle/intimate), jessica (playful/bright), laura (upbeat/sassy), lily (velvety/theatrical British), matilda (composed/warm)
  Neutral: river (calm/gender-neutral)
  Male: george (warm British rasp), adam (deep/steady), bill (seasoned/crisp), brian (deep/comforting), callum (gravelly/edgy), charlie (casual Australian), chris (down-to-earth), daniel (authoritative British), eric (smooth/grounded), harry (fierce/dramatic), liam (youthful/energetic), roger (laid-back/confident), will (friendly/relaxed)
- Write a realistic `first_text` (1-2 sentences, pure text message, NO *asterisks* or narration) they would send to open a chat.
- TWO SEPARATE PROFILES: this texting profile is its own thing; the roleplay card stays as it is. `appearance_notes`
  describe how {char} looks IN THIS SETUP: keep face, hair, eyes, skin, build and age; in "modern_au" translate
  outfit, gear and accessories into what they'd wear in today's world (no armour, masks, weapons, robes or uniforms
  of their world unless the directions keep them). Change lore only as far as the setup needs.
- ASK, DON'T DECIDE: when a look or lore point is central to who they are (a mask they hide behind, a title, a
  scar, a secret, who knows what), don't quietly keep or drop it: make your best choice and put a short question
  about it in `questions` so {user} can say otherwise. List what differs from the roleplay card in `changes`.

Original card of {char}:
{card_text}

Their original roleplay scenario (background only: it describes the roleplay, not this texting setup{scenario_rule}):
{scenario}
{hint_block}
Answer with JSON only:
{{
  "handle": "@username_in_lowercase",
  "status_emoji": "one fitting emoji",
  "bio": "Their short Telegram bio (up to 140 chars, in their voice)",
  "modern_persona": "Who {char} is in this setup, what they do, their daily life and attitude toward {user} (4-7 sentences, no static 'tonight' anchors)",
  "texting_style": "How {char} texts: sentence length, punctuation, capitalization, emoji use, and habits (2-3 sentences, no verbatim catchphrases)",
  "appearance_notes": "Concrete visual description of {char} (face, hair, eyes, build, signature clothing/vibe) for consistent photo generation",
  "art_style_notes": "Visual art style to keep across all photos (e.g. 'semi-realistic painted anime illustration, warm cinematic lighting')",
  "voice_id": "one voice name from the list above",
  "scenario": "Why {char} and {user} have each other's contact and what is happening as the chat begins (2-4 sentences)",
  "first_text": "Their opening text message (no stage directions)",
  "changes": ["What differs from the roleplay card in this setup, one short line each (job, look, lore)"],
  "questions": ["Up to 3 short questions for {user} about choices that are theirs to make (e.g. keep the mask?)"]
}}"""


CREATE_MESSENGER_CHAR_PROMPT = """You are Bulba, creating a brand-new Messenger-first character card for NarrativeAI's Telegram-style chat app.
The user wants to create a character to text with directly (without needing to write a full traditional roleplay card first).

User's idea / concept:
- Name (if given): {name_hint}
- Mode: {mode_desc}
- Concept / notes from {user}: {idea}

Rules:
- Build a vivid, distinct character with real motives, flaws, personal boundaries, and an authentic voice—never a generic eager assistant.
- CARD AUDIT SAFEGUARDS:
  1. Do NOT put static time anchors ("tonight", "this morning") inside `modern_persona` or `bio`.
  2. Do NOT use "always/constantly/every sentence" on quirks or put verbatim quoted catchphrases in `texting_style`.
- Write concrete `appearance_notes` (face, hair, eyes, build, everyday clothing) and `art_style_notes` (the exact visual style—e.g. 'clean anime illustration with soft atmospheric lighting' or 'cinematic semi-realistic digital portrait'—so every selfie, food snapshot, and scenery photo matches the same aesthetic).
- Pick the best-fitting voice from: sarah, alice, bella, jessica, laura, lily, matilda, river, george, adam, bill, brian, callum, charlie, chris, daniel, eric, harry, liam, roger, will.
- Write a natural `first_text` (1-2 sentences, pure text message, zero *asterisks* or stage directions).

Answer with JSON only:
{{
  "name": "Character's display name",
  "short_description": "One-line tagline (up to 120 chars)",
  "handle": "@username_in_lowercase",
  "status_emoji": "one fitting emoji",
  "bio": "Short Telegram bio in their voice (up to 140 chars)",
  "modern_persona": "Who they are, their occupation/daily life, temperament, flaws, and relationship with {user} (5-7 sentences)",
  "texting_style": "How they text: rhythm, capitalization, punctuation, emoji attitude, bubble length (2-3 sentences)",
  "appearance_notes": "Detailed physical appearance and clothing style (3-4 sentences)",
  "art_style_notes": "Consistent visual art style & lighting for all their photos (1 sentence)",
  "voice_id": "one voice name from the list",
  "scenario": "How they and {user} got each other's contact and the starting situation (2-4 sentences)",
  "first_text": "Their opening text message (pure text, no narration)"
}}"""


def modernize_with_bulba(user, character, mode="modern_au", hint="", save=True):
    """Ask Bulba's model to draft a Modern AU or Canon texting profile for `character`."""
    from mainapp.cards import user_name
    u_name = user_name(user)
    card_text = card_sections.compose(character.sections) if character.sections else (character.description or "")
    if character.personality:
        card_text = f"{card_text}\n\nPersonality: {character.personality}".strip()
    if character.example_dialogue:
        card_text = f"{card_text}\n\nExample dialogue:\n{character.example_dialogue[:1200]}".strip()

    mode = "modern_au" if mode == "modern_au" else "canon"
    mode_desc = ("Modern AU: translate their world and role into a modern-day setting"
                 if mode == "modern_au" else "Canon world with a texting scenario")
    hint = str(hint or "").strip()[:1500]
    hint_block = (f"\n=== {u_name}'S DIRECTIONS FOR THIS SETUP (binding) ===\n{hint}\n"
                  f"These are decisions {u_name} already made. Follow every one of them exactly: how they met, who they "
                  f"are to each other, jobs, places and anything else named here go into `scenario`, `modern_persona` "
                  f"and `first_text` as given. Do not replace them with circumstances from the original card or "
                  f"scenario, and do not invent different ones; only fill in what they left open.\n"
                  ) if hint else ""
    scenario_rule = "; where it disagrees with the directions below, the directions win" if hint else ""
    prompt = MODERNIZE_PROMPT.format(
        char=character.name,
        user=u_name,
        mode_desc=mode_desc,
        hint_block=hint_block,
        scenario_rule=scenario_rule,
        card_text=card_text[:6000] or character.name,
        scenario=(character.scenario or "None specified")[:2000],
    )
    parsed = ask_json(user, prompt, need=("bio", "modern_persona", "texting_style"), max_tokens=2600)
    picked_voice = str(parsed.get("voice_id") or "").strip().lower()
    if picked_voice not in voice.OPENROUTER_VOICE_NAMES:
        picked_voice = character.eleven_voice_char_id or "sarah"
    updates = {
        "mode": mode,
        "handle": parsed.get("handle") or _default_handle(character.name),
        "status_emoji": parsed.get("status_emoji") or "💬",
        "bio": parsed.get("bio") or "",
        "modern_persona": parsed.get("modern_persona") or "",
        "texting_style": parsed.get("texting_style") or "",
        "appearance_notes": parsed.get("appearance_notes") or "",
        "art_style_notes": parsed.get("art_style_notes") or "",
        "voice_id": picked_voice,
        "scenario": parsed.get("scenario") or "",
        "first_text": parsed.get("first_text") or "",
    }
    notes = {k: [str(x).strip()[:300] for x in (parsed.get(k) or []) if str(x).strip()][:6]
             for k in ("changes", "questions") if isinstance(parsed.get(k), list)}  # shown with the draft, not saved
    if save:
        return {**save_char_profile(character, updates), "setup_notes": notes}
    merged = char_profile(character)
    merged.update(updates)
    return {**merged, "setup_notes": notes}


def create_messenger_character_with_bulba(user, idea, name="", mode="modern_au", generate_pics=False):
    """
    Create a brand-new `Character` tailored specifically for Messenger from a short idea/description,
    without requiring the user to build a traditional roleplay card first.
    Optionally generates their Neutral Portrait + 1 Extra Reference Picture via Nano Banana if `generate_pics=True`.
    """
    from django.utils.text import slugify
    from mainapp.cards import user_name
    u_name = user_name(user)
    idea_text = str(idea or "").strip()
    name_hint = str(name or "").strip()
    if not idea_text and not name_hint:
        raise ai_client.AIError("Give Bulba at least a name or a short character idea.")
    mode = "modern_au" if mode == "modern_au" else "canon"
    mode_desc = "Modern-day real-world setting" if mode == "modern_au" else "In-world / canon setting"
    prompt = CREATE_MESSENGER_CHAR_PROMPT.format(
        name_hint=name_hint or "(choose a fitting name)",
        mode_desc=mode_desc,
        user=u_name,
        idea=(idea_text or name_hint)[:3000],
    )
    parsed = ask_json(user, prompt, need=("name", "modern_persona", "texting_style"), max_tokens=3000, temperature=0.7)

    char_name = str(parsed.get("name") or name_hint or "New Contact").strip()[:100]
    base_slug = slugify(char_name) or "contact"
    slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    modern_persona = str(parsed.get("modern_persona") or "").strip()
    appearance_notes = str(parsed.get("appearance_notes") or "").strip()
    art_style_notes = str(parsed.get("art_style_notes") or "clean expressive digital illustration, natural atmospheric lighting").strip()
    texting_style = str(parsed.get("texting_style") or "").strip()
    scenario = str(parsed.get("scenario") or "").strip()
    first_text = str(parsed.get("first_text") or "Hey.").strip()
    picked_voice = str(parsed.get("voice_id") or "sarah").strip().lower()
    if picked_voice not in voice.OPENROUTER_VOICE_NAMES:
        picked_voice = "sarah"

    # Build clean card sections so the character also works seamlessly if opened in the library
    sections_data = {
        "version": 1,
        "people": [{
            "name": char_name,
            "role": "main",
            "sections": {
                "appearance": {"text": appearance_notes, "importance": "normal"},
                "temperament": {"text": modern_persona, "importance": "high"},
                "voice": {"text": texting_style, "importance": "high"},
                "background": {"text": scenario, "importance": "normal"},
            },
        }],
        "shared": {},
    }
    composed_desc = card_sections.compose(sections_data) or f"{modern_persona}\n\nAppearance: {appearance_notes}".strip()

    character = Character.objects.create(
        name=char_name,
        slug=slug,
        creator_notes=str(parsed.get("short_description") or parsed.get("bio") or char_name)[:200],
        description=composed_desc[:8000],
        personality=modern_persona[:1000],
        scenario=scenario[:4000],
        initial_message=first_text[:2000],
        sections=sections_data,
        eleven_voice_char_id=picked_voice,
        author=user,
    )
    save_char_profile(character, {
        "mode": mode,
        "display_name": char_name,
        "handle": parsed.get("handle") or _default_handle(char_name),
        "status_emoji": parsed.get("status_emoji") or "💬",
        "bio": parsed.get("bio") or "",
        "modern_persona": modern_persona,
        "texting_style": texting_style,
        "appearance_notes": appearance_notes,
        "art_style_notes": art_style_notes,
        "voice_id": picked_voice,
        "scenario": scenario,
        "first_text": first_text,
    })

    if generate_pics:
        try:
            generate_character_references_from_description(user, character, count=2)
        except Exception as e:
            log.info("Auto reference generation during character creation skipped: %s", e)

    return character


# ---------------------------------------------------------------------------
# Thread Data & Real-Time Clock / Events
# ---------------------------------------------------------------------------

def thread_data(thread):
    raw = thread.data if isinstance(thread.data, dict) else {}
    return {
        "messages": [m for m in (raw.get("messages") or []) if isinstance(m, dict)],
        "bg": raw.get("bg") or "tg-night",
        "custom_bg_url": str(raw.get("custom_bg_url") or ""),
        "pinned_id": raw.get("pinned_id"),
        "unread": max(0, int(raw.get("unread") or 0)),
        "events": [e for e in (raw.get("events") or []) if isinstance(e, dict)],
        "scenario_override": str(raw.get("scenario_override") or "").strip()[:3000],
        "share_memory": raw.get("share_memory", True) is not False,
        "last_auto_at": raw.get("last_auto_at"),
        "leave_on_read": bool(raw.get("leave_on_read", False)),  # 🙈 per chat: they may answer up to 5 minutes later
        # 🧭 the "Before you start" card was answered; 🎭 who the user is in this chat only (else their usual persona)
        "started": bool(raw.get("started", False)),
        "persona": {k: str((raw.get("persona") or {}).get(k) or "").strip()[:{"name": 80, "description": 3000}[k]]
                    for k in ("name", "description")} if isinstance(raw.get("persona"), dict) else {},
        # 🧠 the chat's memory: a running summary of what fell out of view, and how many recent messages are read
        "memory": str(raw.get("memory") or "")[:6000],
        "memory_upto": max(0, int(raw.get("memory_upto") or 0)),
        "context_size": raw.get("context_size") if raw.get("context_size") in CONTEXT_SIZES else 30,
        "theme": raw.get("theme") if raw.get("theme") in THEMES else "",
        # 🕰️ the chat's own clock: seconds from real time (0 = real time), to pick up a night chat the next day
        "clock_offset": float(raw.get("clock_offset") or 0),
        "branch_of": raw.get("branch_of") if isinstance(raw.get("branch_of"), dict) else None,  # ⑂ where it branched from
        "regen_prev": [m for m in (raw.get("regen_prev") or []) if isinstance(m, dict)][:20],  # ↻ the take before
    }


def chat_now(data):
    """🕰️ Now on the chat's clock, in seconds."""
    return time.time() + float(data.get("clock_offset") or 0)


def set_clock(thread, how):
    """🕰️ The chat's clock: "real", "resume" (just after its last message: a night chat goes on the next day), or
    an ISO date and time. Returns the offset in seconds."""
    raw = dict(thread.data or {})
    if how == "real":
        offset = 0.0
    elif how == "resume":
        last = [ts_of(m) for m in delivered(thread_data(thread)["messages"]) if ts_of(m)]
        offset = (max(last) + 60 - time.time()) if last else 0.0
    else:
        when = datetime.fromisoformat(str(how))
        when = timezone.make_aware(when) if timezone.is_naive(when) else when
        offset = when.timestamp() - time.time()
    raw["clock_offset"] = offset
    thread.data = raw
    thread.save(update_fields=["data"])
    return offset


def save_thread_data(thread, data):
    shift = float(data.get("clock_offset") or 0)
    if shift:  # 🕰️ messages made just now carry the chat's time, not the real one
        real = time.time()
        for m in data.get("messages") or []:
            if not m.get("clocked") and abs(ts_of(m) - real) < 300:
                m["ts"] = ts_of(m) + shift
                m["time"] = timezone.localtime(timezone.now() + timezone.timedelta(seconds=shift)).strftime("%H:%M")
                m["clocked"] = True
    thread.data = data
    thread.save(update_fields=["data", "updated"])


def _time_of_day_label(hour):
    if 0 <= hour < 5:
        return "late night"
    if 5 <= hour < 9:
        return "early morning"
    if 9 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 21:
        return "evening"
    return "night"


def _human_elapsed(seconds):
    if seconds is None or seconds < 0:
        return "just now"
    seconds = int(seconds)
    if seconds < 90:
        return "just now (active live conversation)"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if seconds < 86400:
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        return f"{hrs} hour{'s' if hrs != 1 else ''}" + (f" {mins}m" if mins else "") + " ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


def real_time_context(thread, now=None):
    """Real-world clock (or the chat's own, when it was set: 🕰️), time elapsed since the last message, and
    scheduled events for the thread."""
    data = thread_data(thread)
    shift = data["clock_offset"]
    now = (now or timezone.now()) + timezone.timedelta(seconds=shift)
    local_now = timezone.localtime(now) if timezone.is_aware(now) else now
    msgs = data["messages"]
    elapsed_sec = None
    last_sender = None
    if msgs:
        last_msg = msgs[-1]
        last_sender = last_msg.get("sender_name") or last_msg.get("role")
        ts = ts_of(last_msg)
        if ts > 0:
            elapsed_sec = max(0, time.time() + shift - ts)
    tod = _time_of_day_label(local_now.hour)
    clock_str = local_now.strftime("%A, %d %B %Y, %H:%M") + f" ({tod})"
    elapsed_str = _human_elapsed(elapsed_sec) if elapsed_sec is not None else "start of conversation"
    active_events = [e for e in data["events"] if not e.get("done")]
    return {
        "clock": clock_str,
        "time_of_day": tod,
        "hour": local_now.hour,
        "elapsed_seconds": elapsed_sec,
        "elapsed_text": elapsed_str,
        "last_sender": last_sender,
        "events": active_events,
    }


def group_scenario(user, thread, hint=""):
    """🥔 A group chat's shared scenario, from its members' texting profiles: how they all know each other and the
    user, and what's going on as the chat begins. The user's directions are binding. Saved as the chat's scenario."""
    from mainapp.cards import user_name
    u_name = (thread_data(thread).get("persona") or {}).get("name") or user_name(user)
    people = []
    for c in thread.characters.all():
        prof = char_profile(c)
        people.append(f"- {c.name} ({prof['handle']}): {prof['modern_persona'] or c.description[:500]}\n  Their own "
                      f"scenario with {u_name}: {prof['scenario'] or '(none)'}")
    hint = str(hint or "").strip()[:1500]
    prompt = (f"You are Bulba, setting up a group chat in NarrativeAI's messenger. Members:\n" + "\n".join(people) +
              f"\n\nWrite the group chat's shared scenario: why these people and {u_name} are in one group chat, how "
              f"they know each other, and what's going on as the chat begins (3-5 sentences, no 'tonight' anchors). "
              f"Keep each member's own setup true; where two disagree, find what makes both true."
              + (f"\n\n=== {u_name}'S DIRECTIONS (binding) ===\n{hint}\nFollow every one of them exactly; only fill in "
                 f"what they left open." if hint else "")
              + '\n\nAnswer with JSON only: {"scenario": "...", "title": "a short group name, the kind people give '
                'group chats"}')
    data = ask_json(user, prompt, need=("scenario",), max_tokens=900)
    raw = dict(thread.data or {})
    raw["scenario_override"] = str(data["scenario"]).strip()[:3000]
    thread.data = raw
    if data.get("title"):
        thread.title = str(data["title"]).strip()[:200]
    thread.save(update_fields=["data", "title", "updated"])
    return raw["scenario_override"]


def card_people(character):
    """The names on a card with several people (an ensemble card), else []."""
    data = card_sections.clean(character.sections) if character.sections else None
    if not data or data["kind"] != "ensemble":
        return []
    names = [p["name"] for p in data["people"] if p["name"]]
    return names if len(names) > 1 else []


def split_card(user, character):
    """✂️ A card with several people as separate characters, one per person (their own sections; the ensemble's
    setting goes into each one's background, what's between them into their relationships), and a group chat
    with all of them. The original card stays as it is. Returns the group chat."""
    from django.utils.text import slugify
    from mainapp.cards import _unique_slug
    from mainapp.models import Character
    data = card_sections.clean(character.sections)
    if not card_people(character):
        raise ValueError("That card has one person: nothing to split.")
    setting, between = (data["shared"].get(k, {}).get("text", "") for k in ("setting", "between"))
    made = []
    for p in data["people"]:
        if not p["name"]:
            continue
        person = {**p, "sections": {k: dict(v) for k, v in p["sections"].items()}}
        if setting:
            bg = person["sections"].get("background", {"text": "", "on": True})
            bg["text"] = (bg["text"] + "\n\nSetting: " + setting).strip()
            person["sections"]["background"] = bg
        if between:
            rel = person["sections"].get("relationships", {"text": "", "on": True})
            rel["text"] = (rel["text"] + "\n\nBetween them: " + between).strip()
            person["sections"]["relationships"] = rel
        one = Character(name=p["name"], author=user, initial_message="", scenario=character.scenario or "",
                        slug=_unique_slug(Character, f"{user.username}-{slugify(p['name']) or 'character'}"))
        card_sections.apply(one, {"kind": "character", "people": [person], "shared": {}})
        one.save()
        made.append(one)
    return create_thread(user, made, title=character.name, is_group=True)


def new_chat_like(user, thread):
    """💬 A fresh chat with the same character(s) (their first text again), named so it can be told apart."""
    chars = list(thread.characters.all())
    if not chars:
        raise ValueError("That chat has no characters.")
    from mainapp.models import MessengerThread
    same = [t for t in MessengerThread.objects.filter(user=user).prefetch_related("characters")
            if {c.id for c in t.characters.all()} == {c.id for c in chars}]
    base = ", ".join(c.name for c in chars[:4]) if thread.is_group else chars[0].name
    return create_thread(user, chars, title=f"{base} · chat {len(same) + 1}", is_group=thread.is_group,
                         scenario_override=thread_data(thread)["scenario_override"])


def branch_chat(user, thread, message_id):
    """⑂ A new chat that starts as this one up to (and with) one message; the original stays as it is."""
    from mainapp.models import MessengerThread
    data = thread_data(thread)
    idx = next((i for i, m in enumerate(data["messages"]) if m.get("id") == message_id), None)
    if idx is None:
        raise ValueError("That message isn't in this chat.")
    raw = dict(thread.data or {})
    kept = [dict(m) for m in delivered(data["messages"][:idx + 1])]
    for m in kept:
        m.pop("deliver_at", None)
    raw.update({"messages": kept, "unread": 0, "regen_prev": [], "last_auto_at": None,
                "pinned_id": data["pinned_id"] if any(m.get("id") == data["pinned_id"] for m in kept) else None,
                "branch_of": {"thread_id": thread.id, "message_id": message_id, "title": thread.title}})
    branch = MessengerThread.objects.create(user=user, title=f"{thread.title or 'Chat'} · branch", is_group=thread.is_group, data=raw)
    branch.characters.set(list(thread.characters.all()))
    return branch


def ensure_thread_for_character(user, character):
    """Get or create the primary 1-on-1 MessengerThread for a character."""
    existing = (
        MessengerThread.objects.filter(user=user, is_group=False, characters=character)
        .prefetch_related("characters")
        .first()
    )
    if existing:
        return existing
    return create_thread(user, [character])


def create_thread(user, characters, title="", is_group=None, scenario_override=""):
    """Create a 1-on-1 or Group Chat thread with an initial message if available."""
    chars = list(characters)
    if not chars:
        raise ValueError("Pick at least one character.")
    if is_group is None:
        is_group = len(chars) > 1
    if not title:
        title = ", ".join(c.name for c in chars[:4]) if is_group else chars[0].name
    u_prof = user_profile(user)
    init_msgs = []
    now_ts = time.time()
    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
    if not is_group:
        c = chars[0]
        prof = char_profile(c)
        first = prof.get("first_text") or ""
        if first:
            from mainapp.cards import fill_names, user_name
            first = fill_names(first, c.name, user_name(user))
            init_msgs.append({
                "id": uuid.uuid4().hex[:10],
                "role": "assistant",
                "sender_slug": c.slug,
                "sender_name": prof["display_name"],
                "text": first,
                "time": now_hm,
                "ts": now_ts,
                "reactions": {},
            })
    thread = MessengerThread.objects.create(
        user=user,
        title=title[:200],
        is_group=bool(is_group),
        data={
            "messages": init_msgs,
            "bg": u_prof.get("default_bg") or "tg-night",
            "custom_bg_url": "",
            "pinned_id": None,
            "unread": 0,
            "events": [],
            "scenario_override": str(scenario_override or "").strip()[:3000],
            "share_memory": True,
        },
    )
    thread.characters.set(chars)
    return thread


# ---------------------------------------------------------------------------
# Frankenstein-Style Texting Preset & Safeguards
# ---------------------------------------------------------------------------

TEXTING_SAFEGUARDS = """MESSENGER MEDIUM & FRANKENSTEIN DIALOGUE SAFEGUARDS:
1. METHOD ACTING ENGINE & TRUE NPC AUTONOMY (FRANKENWIRE):
   - [Embody_Before_Typing]: Lock onto the character's immediate self-interest, current activity at this hour, personal boundary, and mood BEFORE generating a single word.
   - [No_People_Pleasing]: Characters prioritize their own agenda, pride, schedule, and flaws over catering to {user}.
   - [No_Hovering]: Commit to concrete opinions, refusals, jokes, or disclosures—never stall with vague half-hints.
   - [Echo_Ban]: NEVER open a reply by repeating, paraphrasing, or summarizing what {user} just texted. Their bubble is right above yours—reply with what comes next.

2. PURE PHONE MESSAGING (NO NARRATION):
   - You are texting on a phone/computer messenger (Telegram style). Write ONLY what goes through the messenger.
   - NEVER write third-person narration, scene descriptions, or stage directions in asterisks (*sighs*, *looks at phone*, *clenches jaw*).
   - Physical actions in the room are invisible over text unless the character explicitly mentions them in words, sends a `[PHOTO: ...]`, or sends a `[VOICE: ...]`.

3. DISTINCT TEXTING FINGERPRINT & BUBBLE PACING:
   - Match each character's vocabulary, rhythm, punctuation, capitalization, and temperament from their profile.
   - Real people rarely send essays in a chat app. Send 1 to 4 short bubbles separated by `|||BUBBLE|||` when a character sends multiple quick texts in a row, OR a single concise bubble when they are dry/busy.
   - Do not give every character the same witty banter voice. A curt character sends terse texts; a formal character uses full punctuation; an impulsive character double-texts.
   - TYPOS ONLY AT SPEED: when a character fires off several quick texts in a row (excited, rattled, angry, rushing), a small natural typo now and then is fine: a swapped, doubled or missing letter, autocorrect gone wrong; sometimes they fix it in the next bubble ("*tomorrow"). Never in slow, careful or formal messages, never more than one per burst, and never in names.

4. ANTI-SLOP & BEHAVIOURAL CONTINUITY (FRANKENSTEIN RULES):
   - NO THERAPY VOICE: Do not diagnose feelings, validate emotions ("That's valid", "I hear you", "hold space", "boundaries"), or sound like a counselor unless the character is literally a therapist.
   - NO OCCUPATION METAPHOR SPAM: Do not force the character's job into every sentence (a scientist does not call dinner "fuel intake" or a text "a data point" in casual chat).
   - NO RECOUNTING / SCORE-KEEPING: Do not chain past events with "and then... and now..." or tally how many times something happened to win an argument.
   - NO CORRECTIVE CONTRAST FORMULAS: Avoid stock "It's not X, it's Y" / "Not a request, a command" constructions.
   - EARNED WARMTH & FRICTION: Keep established goals, flaws, and grudges consequential. A polite text does not reset a rivalry or make a guarded character overshare.
   - STRICT PHONE SCREEN HORIZON: Characters ARE NOT OMNISCIENT. They cannot see {user}'s room, outfit, or expression unless {user} texted it or sent a photo. Never invent a guess or convenient excuse to know an unshared secret.
   - AUTHORSHIP: Never write texts for {user}.

5. RICH TELEGRAM ACTIONS (OPTIONAL — USE WHEN NATURAL):
   - Multiple bubbles: put `|||BUBBLE|||` between separate text bubbles sent one after another.
   - React to {user}'s message: include `[REACT: ❤️]` (or 🔥 👍 😂 😮 😢 👀 😡 🤔) at the start or end. A reaction ALONE, with no text, is a complete answer when nothing needs saying (a 👍 to "ok see you tomorrow", a ❤️ to a goodnight): real people do that.
   - Send a character mood sticker: include `[STICKER: mood_name]` choosing from their available moods ({moods}).
   - Send a voice message: wrap spoken audio in `[VOICE: [sighs] what they say out loud into the mic]` (supports delivery tags like `[laughs]`, `[whispers]`, `[sighs]`, `[sarcastic]`, `[curious]`).
   - Send a casual or tease photo: include `[PHOTO: concrete visual description of the selfie, food, desk, or scenery photo they snap right now, including camera angle]` (or `[TEASE: description]` when flirty/intimate fits the relationship). When they are NOT in the photo (their food, a view, their desk, a thing), begin the description with `No people:`. When {user} asks for a photo without them in it, it has no people.
   - Send a file/document: include `[FILE: filename.txt | text content of the note, document, receipt, or schedule]` (a markdown table is fine for lists, schedules, results).
   - When {user} edited a message (marked "edited"), you may notice it if it matters (they softened something, took something back): real people do.
   - Update their own Telegram bio or post a status story when something changes: `[BIO: new bio text]` or `[STATUS: 🧪 | short status update]`, with a picture if it fits: `[STATUS: 🧪 | short text | PHOTO: what the picture shows]`.
   - Schedule a real-time event/reminder: `[EVENT: Title at HH:MM | short note]`."""


def active_model_texting_rules(user):
    """
    Inspect the user's currently selected chat model in real time (`ai_client.main_profile(user)`)
    and return `{model_id, profile_id, label, rules, compact}` so the texting rules automatically adapt
    even if the user switches models mid-conversation.
    """
    from mainapp import model_profiles
    model_id = ""
    try:
        conn_prof = ai_client.main_profile(user)
        model_id = (conn_prof.model if conn_prof else "") or ""
    except Exception:
        model_id = ""
    prof = model_profiles.for_style(model_id) if model_id else None
    pid = (prof or {}).get("id") or "generic"
    pname = (prof or {}).get("name") or (model_id.split("/")[-1] if model_id else "Default Model")
    counters = writing_quality.catalog().get("default_counters") or {}
    base_counter = counters.get(pid) or ""

    # Family-specific texting adaptations derived from Reddit preset & card-audit findings
    family_note = ""
    compact = False
    low_id = (pid + " " + model_id).lower()
    if "argon" in low_id or "gemini" in low_id:
        family_note = (
            "TEXTING PACING & PHONE HORIZON: Do not rush intimacy or escalate casual chat into dramatic confessions. "
            "Strict Phone Horizon: you cannot see through the screen—if a detail wasn't texted or photographed, you do not know it and must not guess it or invent an excuse for knowing it. "
            "Avoid 'It's not X, it's Y' contrasts and stock intensity words."
        )
    elif "deepseek" in low_id:
        compact = True
        family_note = (
            "COMPACT TEXTING FOCUS: Keep bubbles crisp and forward-moving. Do not echo the user's message, "
            "re-introduce unchanged surroundings, or end every turn with a binary 'either/or' challenge question."
        )
    elif "mimo" in low_id:
        family_note = (
            "ANTI-RECAP & ANTI-ECHO: Never open a bubble by quoting, paraphrasing, or summarizing what the user just sent. "
            "Respond directly to the point without chaining 'you did X, and then Y, and now Z' accusation lists."
        )
    elif "glm" in low_id:
        family_note = (
            "CONCRETE TEXTING VOICE: Answer from concrete personal purpose rather than assent-and-reframe formulas or occupational jargon. "
            "No repeated single-word filler ('Fine. Fine.') before speaking."
        )
    elif "claude" in low_id or "fable" in low_id:
        family_note = (
            "ANTI-COUNSELOR & EARNED WARMTH: Keep sharp edges, independent priorities, and personal boundaries intact even when the user is friendly. "
            "Zero validation register ('I respect that', 'that's valid', filler 'honestly'). Match idioms strictly to the character's background."
        )
    elif "kimi" in low_id:
        family_note = (
            "DIRECT REPLY: Apply texting rules silently without meta-commentary or stalling. Keep casual texts distinct from technical job jargon."
        )

    combined = "\n".join(p for p in (family_note, base_counter) if p).strip()
    return {
        "model_id": model_id,
        "profile_id": pid,
        "label": pname,
        "rules": combined,
        "compact": compact,
    }


def _character_block(character, user, u_name=None, share=None):
    from mainapp.cards import fill_names, user_name
    u_name = u_name or user_name(user)
    prof = char_profile(character)
    card_body = card_sections.compose(character.sections) if character.sections else (character.description or "")
    card_body = fill_names(card_body, character.name, u_name)
    lines = [
        f"### {prof['display_name']} ({prof['handle']}) — Status: {prof['status_emoji']} {prof['bio'] or 'No bio'}",
        f"Setup mode: {'Modern AU' if prof['mode'] == 'modern_au' else 'Original setting (Messenger)'}",
    ]
    if prof["modern_persona"]:
        lines.append(f"Messenger / Modern AU Persona:\n{fill_names(prof['modern_persona'], character.name, u_name)}")
    if prof.get("appearance_notes"):
        lines.append(f"Visual appearance: {fill_names(prof['appearance_notes'], character.name, u_name)[:800]}")
    if card_body:
        lines.append(f"Core Character Card (for voice, temperament, appearance & deeper traits):\n{card_body[:3500]}")
    if character.personality:
        lines.append(f"Personality summary: {fill_names(character.personality, character.name, u_name)[:800]}")
    if prof["texting_style"]:
        lines.append(f"Texting style & habits: {fill_names(prof['texting_style'], character.name, u_name)}")
    if prof["scenario"]:
        lines.append(f"Scenario: {fill_names(prof['scenario'], character.name, u_name)}")
    if (prof["share_memory"] if share is None else share):  # the chat's own choice wins (asked when it starts)
        latest_chat = character.chats.first()
        if latest_chat:
            try:
                c_data = chats.read(latest_chat)
                mem_text = story_memory.story_text(user, c_data, c_data.get("summary") or "")
                if mem_text:
                    lines.append(f"Shared Story Memory with {u_name}:\n{mem_text[:2000]}")
            except Exception:
                pass
    return "\n".join(lines)


def build_messenger_prompt(user, thread, extra_instruction=""):
    """Assemble the complete chat-completion messages list for a 1-on-1 or Group MessengerThread."""
    from mainapp.cards import user_name
    u_name = user_name(user)
    u_prof = user_profile(user)
    chars = list(thread.characters.all())
    if not chars:
        raise ValueError("This chat has no characters.")
    data = thread_data(thread)
    chat_persona = data.get("persona") or {}
    if chat_persona.get("name"):  # 🎭 someone else in this chat only
        u_name = chat_persona["name"]
    rt = real_time_context(thread)

    all_moods = sorted({m for c in chars for m in sprites.emotions(c)})
    safeguards = TEXTING_SAFEGUARDS.format(user=u_name, moods=", ".join(all_moods[:16]))
    model_info = active_model_texting_rules(user)
    model_block = (
        f"ACTIVE MODEL TEXTING CALIBRATION ({model_info['label']}):\n{model_info['rules']}"
        if model_info.get("rules")
        else ""
    )
    taste_block = "" if model_info.get("compact") else writing_quality.helper_taste(user, habits=True)

    char_blocks = "\n\n".join(_character_block(c, user, u_name=u_name, share=data["share_memory"]) for c in chars)
    user_persona = (chat_persona.get("description") or getattr(user, "persona_description", "") or "").strip()
    user_stories = u_prof.get("stories") or []
    latest_user_story = f" | Latest status post: \"{user_stories[0].get('text', '')}\"" if user_stories else ""
    user_block = (
        f"USER PROFILE ON TELEGRAM:\n"
        f"- Name: {u_prof['display_name']} ({u_prof['handle']})\n"
        f"- Bio: {u_prof['status_emoji']} {u_prof['bio'] or 'No bio set'}{latest_user_story}\n"
        + (f"- Who {u_name} is: {user_persona[:1200]}\n" if user_persona else "")
    )

    events_lines = "\n".join(
        f"  • {e.get('title')}: {e.get('when') or 'upcoming'}" + (f" ({e.get('notes')})" if e.get("notes") else "")
        for e in rt["events"][:8]
    )
    time_block = (
        f"REAL-TIME CLOCK & PASSAGE OF TIME:\n"
        f"- Current real-world time: {rt['clock']}\n"
        f"- Time since last message in chat: {rt['elapsed_text']}"
        + (f" (last message was from {rt['last_sender']})" if rt["last_sender"] else "")
        + "\n- React naturally to the time of day (e.g. late night vs work hours) and to long gaps if hours or days passed."
        + (f"\n- Active scheduled events / reminders:\n{events_lines}" if events_lines else "")
    )
    if data.get("scenario_override"):
        time_block += f"\n- Thread scenario / topic: {data['scenario_override']}"
    if data.get("leave_on_read"):  # 🙈 the user allowed it for this chat
        time_block += ("\n- LEAVING ON READ IS ALLOWED in this chat: a character may decide not to answer right away, when "
                       "it truly fits: they were busy doing something, or for an emotional reason (teasing, annoyed, "
                       "petty, needing a minute). Then still write their reply now, as they'll send it when they get "
                       "back to the phone, and put `[LATER: N, why]` at its very start, N = minutes before they answer (1 "
                       "to 5), why = a word or two (busy at work, asleep, petty). Most replies come at once; don't use it "
                       "twice in a row.")

    if thread.is_group or len(chars) > 1:
        names_list = ", ".join(f"{c.name} (slug: {c.slug})" for c in chars)
        group_rule = (
            f"GROUP CHAT MODE — Members: {names_list}, and {u_name}.\n"
            f"- Prefix EVERY bubble with the speaking character's name followed by a colon, e.g.:\n"
            f"  {chars[0].name}: Wait, who gave you this number?\n"
            f"  |||BUBBLE|||\n"
            f"  {chars[-1].name}: I did. Relax.\n"
            f"- 1 to 3 characters can reply in a turn depending on who was addressed or who has something to say. "
            f"Characters can also reply to or banter with each other."
        )
    else:
        group_rule = (
            f"ONE-ON-ONE CHAT with {chars[0].name}.\n"
            f"- Write as {chars[0].name}. Separate multiple short text bubbles in the same turn with `|||BUBBLE|||`."
        )

    sys_content = "\n\n".join(p for p in (safeguards, model_block, taste_block, group_rule, user_block, time_block, char_blocks) if p)
    if data.get("memory"):  # 🧠 what happened before the messages below
        sys_content += f"\n\nEARLIER IN THIS CHAT (a summary of what came before the messages below):\n{data['memory']}"
    messages = [{"role": "system", "content": sys_content}]

    # Recent conversation history (last 30 bubbles)
    for m in data["messages"][-data["context_size"]:]:
        role = m.get("role")
        if role == "system":
            messages.append({"role": "system", "content": f"[Messenger notice: {m.get('text', '')}]"})
            continue
        speaker = m.get("sender_name") or (u_name if role == "user" else chars[0].name)
        parts = []
        if m.get("reply_to_text"):
            parts.append(f"[Replying to {m.get('reply_to_sender', 'message')}: \"{m['reply_to_text'][:120]}\"]")
        if m.get("sticker"):
            parts.append(f"[Sent sticker: {m['sticker'].get('name') or m['sticker'].get('mood') or 'sticker'}]")
        if m.get("voice"):
            parts.append(f"[Voice message: \"{m['voice'].get('transcript') or m.get('text') or ''}\"]")
        if m.get("photo"):
            ph = m["photo"]
            if role == "user":  # what the picture shows (looked at once when sent), and what they wrote with it
                seen = ph.get("seen") or "a picture (couldn't be looked at)"
                parts.append(f"[Sent a photo. It shows: {seen}" + (f" | caption: {ph['caption']}" if ph.get("caption") else "") + "]")
            else:
                parts.append(f"[Sent photo: {ph.get('prompt') or ph.get('caption') or 'image'}]")
        if m.get("file"):  # the whole text (a long one cut at 6000 characters)
            parts.append(f"[Sent file {m['file'].get('name', 'file.txt')}:\n{(m['file'].get('content') or '')[:6000]}\n]")
        if role == "user" and m.get("edited_from"):
            parts.append(f"(edited; it first said: \"{str(m['edited_from'])[:300]}\")")
        if m.get("text") and not m.get("voice"):
            parts.append(m["text"])
        body = " ".join(parts).strip() or "..."
        t_stamp = m.get("time") or ""
        if role == "user":
            messages.append({"role": "user", "content": f"[{t_stamp}] {u_name}: {body}" if t_stamp else body})
        else:
            prefix = f"{speaker}: " if (thread.is_group or len(chars) > 1) else ""
            messages.append({"role": "assistant", "content": f"{prefix}{body}"})

    reminder = (
        f"[Reply as the character(s) on Telegram at {rt['clock']}. Pure texting only — NO *asterisks* or narration. "
        f"Use `|||BUBBLE|||` between separate bubbles."
        + (f" Special direction for this turn: {extra_instruction}" if extra_instruction else "")
        + "]"
    )
    messages.append({"role": "user", "content": reminder})
    return messages


# ---------------------------------------------------------------------------
# Parsing Multi-Bubble Replies, Formatting, Media & Profile Updates
# ---------------------------------------------------------------------------

RE_REACT = re.compile(r"\[\s*REACT\s*:\s*([^\]]+?)\s*\]", re.I)
RE_STICKER = re.compile(r"\[\s*STICKER\s*:\s*([^\]]+?)\s*\]", re.I)
def take_tag(text, names):
    """The first [NAME: ...] tag in text, brackets inside it counted ("[VOICE: [sighs] fine, come over]" keeps the
    whole line, not just "[sighs"). Returns (name, content, text without the tag), or (None, "", text)."""
    m = re.search(r"\[\s*(" + "|".join(names) + r")\s*:", text or "", re.I)
    if not m:
        return None, "", text
    depth, i = 1, m.end()
    while i < len(text) and depth:
        depth += {"[": 1, "]": -1}.get(text[i], 0)
        i += 1
    end = i - 1 if depth == 0 else len(text)  # an unclosed tag runs to the end
    return m.group(1).upper(), text[m.end():end].strip(), (text[:m.start()] + text[end + 1:]).strip()


RE_VOICE = re.compile(r"\[\s*VOICE\s*:\s*(.+?)\s*\]", re.I | re.S)
RE_PHOTO = re.compile(r"\[\s*(PHOTO|TEASE|SELFIE|IMAGE)\s*:\s*(.+?)\s*\]", re.I | re.S)
RE_FILE = re.compile(r"\[\s*FILE\s*:\s*([^|\]]+?)\s*\|\s*(.+?)\s*\]", re.I | re.S)
RE_BIO = re.compile(r"\[\s*BIO\s*:\s*(.+?)\s*\]", re.I)
RE_STATUS = re.compile(r"\[\s*STATUS\s*:\s*(?:([^|\]]+?)\s*\|\s*)?(.+?)\s*\]", re.I)
RE_EVENT = re.compile(r"\[\s*EVENT\s*:\s*([^|\]]+?)(?:\s*\|\s*(.+?))?\s*\]", re.I)


def strip_stage_directions(text):
    """Remove accidental *stage directions* outside of **bold** or *short single-word emphasis*."""
    text = str(text or "")
    # Remove multi-word italicized stage actions like *he sighs and leans back*
    def _replace_action(m):
        inner = m.group(1).strip()
        words = inner.split()
        if len(words) >= 4 and any(
            w in inner.lower()
            for w in ("sighs", "smiles", "looks", "leans", "clenches", "pauses", "stares", "laughs", "shakes", "phone", "types")
        ):
            return ""
        return m.group(0)

    text = re.sub(r"(?<!\*)\*([^*\n]{12,200})\*(?!\*)", _replace_action, text)
    return text.strip()


def check_texting_slop(text):
    """Lightweight free check for texting habits (asterisk actions, therapy-speak, overlong essay bubbles)."""
    notes = []
    raw = str(text or "")
    if re.search(r"(?<!\*)\*[a-zA-Z\s,.'-]{15,}\*(?!\*)", raw):
        notes.append("stage_directions")
    if re.search(r"\b(your feelings are valid|i hear what you're saying|hold space for|safe space)\b", raw, re.I):
        notes.append("therapy_voice")
    if len(raw) > 900 and "|||BUBBLE|||" not in raw:
        notes.append("wall_of_text")
    return notes


def watch_notice(messages):
    """🥔 Bulba Watch for texts (free: no model reads them), on the characters' latest message: a phrase they keep
    repeating (3 of their recent texts, so short chats count), stage directions, therapy-speak, a wall of text, or
    texts that keep opening the same way. Returns {"message_id", "text", "note"} or None."""
    from mainapp.bulba import watch
    theirs = [m for m in messages if m.get("role") == "assistant" and (m.get("text") or (m.get("voice") or {}).get("transcript"))]
    if not theirs:
        return None
    last = theirs[-1]
    body = lambda m: m.get("text") or (m.get("voice") or {}).get("transcript") or ""
    texts = {i: body(m) for i, m in enumerate(theirs[-12:])}
    newest = len(texts) - 1
    rep = watch.repeated_phrases(texts, newest)
    if rep:
        phrase, where = rep[0]
        return {"message_id": last["id"], "text": f"they keep saying “{phrase}” ({len(where)} of their recent texts)",
                "note": f"Don't use the phrase “{phrase}” or anything close to it."}
    found = check_texting_slop(body(last))
    if "stage_directions" in found:
        return {"message_id": last["id"], "text": "stage directions in asterisks (it's a text, not a scene)",
                "note": "No *actions in asterisks*: only what they'd type."}
    if "therapy_voice" in found:
        return {"message_id": last["id"], "text": "therapist talk", "note": "No therapy-speak: say it like they would."}
    if "wall_of_text" in found:
        return {"message_id": last["id"], "text": "a wall of text", "note": "Much shorter: one or two quick texts."}
    starts = [re.split(r"\W+", body(m).strip().lower(), maxsplit=1)[0] for m in theirs[-5:] if body(m).strip()]
    if len(starts) >= 4 and starts[-1] and starts.count(starts[-1]) >= 4:
        return {"message_id": last["id"], "text": f"their texts keep opening with “{starts[-1]}”",
                "note": f"Don't open with “{starts[-1]}”."}
    return None


def _match_speaker(chars, prefix_name):
    if not prefix_name or len(chars) == 1:
        return chars[0]
    target = prefix_name.strip().lower().lstrip("@")
    for c in chars:
        p = char_profile(c)
        if (
            c.name.lower() == target
            or p["display_name"].lower() == target
            or p["handle"].lower().lstrip("@") == target
            or c.name.lower().split()[0] == target.split()[0]
        ):
            return c
    return chars[0]


def parse_ai_reply(raw_text, chars, is_group=False):
    """
    Parse an AI reply into:
    - `reactions`: list of (char, emoji)
    - `profile_updates`: list of {"char", "kind": "bio"|"status", "text", "emoji"}
    - `events`: list of {"title", "notes"}
    - `bubbles`: list of message dicts ready to append to thread
    """
    raw_text = str(raw_text or "").strip()
    reactions = []
    profile_updates = []
    new_events = []

    # Split into raw bubble chunks by |||BUBBLE||| or double newlines when multiple speakers appear
    chunks = [c.strip() for c in re.split(r"\|\|\|BUBBLE\|\|\|", raw_text) if c.strip()]
    if len(chunks) == 1 and "\n\n" in chunks[0]:
        sub = [s.strip() for s in chunks[0].split("\n\n") if s.strip()]
        if len(sub) <= 5:
            chunks = sub

    bubbles = []
    current_char = chars[0]
    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")

    for chunk in chunks[:6]:
        # Detect Speaker: prefix if present
        sp_match = re.match(r"^\s*\*{0,2}([A-Za-zА-Яа-яІіЇїЄєҐґ0-9_ .'-]{2,40})\*{0,2}\s*:\s*(.+)$", chunk, re.S)
        if sp_match:
            candidate_name = sp_match.group(1).strip()
            # Ensure it's not a tag like [VOICE: ...] or http:
            if candidate_name.upper() not in ("REACT", "STICKER", "VOICE", "PHOTO", "TEASE", "FILE", "BIO", "STATUS", "EVENT", "HTTP", "HTTPS"):
                matched = _match_speaker(chars, candidate_name)
                if matched:
                    current_char = matched
                    chunk = sp_match.group(2).strip()

        # Extract reactions
        for m in RE_REACT.finditer(chunk):
            emo = m.group(1).strip()[:8]
            if emo:
                reactions.append((current_char, emo))
        chunk = RE_REACT.sub("", chunk)

        # Extract bio updates
        for m in RE_BIO.finditer(chunk):
            bio_txt = m.group(1).strip()[:240]
            if bio_txt:
                profile_updates.append({"char": current_char, "kind": "bio", "text": bio_txt})
        chunk = RE_BIO.sub("", chunk)

        # Extract status/story updates
        for m in RE_STATUS.finditer(chunk):
            st_emo = (m.group(1) or "💬").strip()[:12]
            st_txt = m.group(2).strip()[:600]
            st_photo = ""
            pm = re.search(r"\|\s*PHOTO\s*:\s*(.+)$", st_txt, re.I | re.S)  # a status with a picture
            if pm:
                st_photo, st_txt = pm.group(1).strip()[:500], st_txt[:pm.start()].strip()
            if st_txt or st_photo:
                profile_updates.append({"char": current_char, "kind": "status", "emoji": st_emo, "text": st_txt[:280],
                                        "photo_prompt": st_photo})
        chunk = RE_STATUS.sub("", chunk)

        # Extract scheduled events
        for m in RE_EVENT.finditer(chunk):
            ev_title = m.group(1).strip()[:120]
            ev_notes = (m.group(2) or "").strip()[:240]
            if ev_title:
                new_events.append({"id": uuid.uuid4().hex[:8], "title": ev_title, "when": ev_title, "notes": ev_notes, "done": False})
        chunk = RE_EVENT.sub("", chunk)

        # Extract sticker
        sticker_data = None
        st_match = RE_STICKER.search(chunk)
        if st_match:
            wanted = st_match.group(1).strip().lower()
            c_stickers = character_stickers(current_char)
            sticker_data = next((s for s in c_stickers if s.get("mood") == wanted or wanted in s.get("name", "").lower()), None)
            if not sticker_data:
                sticker_data = next((s for s in BUILT_IN_STICKERS if wanted in s["id"] or wanted in s["name"].lower()), None)
            if not sticker_data and c_stickers:
                sticker_data = c_stickers[0]
            chunk = RE_STICKER.sub("", chunk)

        # Extract voice message
        voice_data = None
        v_name, transcript, rest = take_tag(chunk, ("VOICE",))
        if v_name and transcript:
            voice_data = {
                "transcript": transcript,
                "audio_url": "",
                "duration": max(2, min(45, len(transcript.split()) // 2)),
            }
            chunk = rest

        # Extract photo
        photo_data = None
        kind_tag, p_desc, rest = take_tag(chunk, ("PHOTO", "TEASE", "SELFIE", "IMAGE"))
        if kind_tag and p_desc:
            p_desc = p_desc[:500]
            photo_data = {
                "kind": "tease" if kind_tag == "TEASE" else "casual",
                "prompt": p_desc,
                "caption": "",
                "url": "",
            }
            chunk = rest

        # Extract file
        file_data = None
        f_match = RE_FILE.search(chunk)
        if f_match:
            f_name = f_match.group(1).strip()[:80] or "note.txt"
            f_content = f_match.group(2).strip()[:4000]
            file_data = {
                "name": f_name,
                "content": f_content,
                "size": f"{max(1, len(f_content.encode('utf-8')))} B",
            }
            chunk = RE_FILE.sub("", chunk)

        clean_text = strip_stage_directions(chunk)
        # Strip wrapping quotes if the model wrapped a whole text bubble in quotes
        if len(clean_text) >= 2 and clean_text[0] == '"' and clean_text[-1] == '"' and clean_text.count('"') == 2:
            clean_text = clean_text[1:-1].strip()

        if not (clean_text or sticker_data or voice_data or photo_data or file_data):
            continue

        prof = char_profile(current_char)
        msg = {
            "id": uuid.uuid4().hex[:10],
            "role": "assistant",
            "sender_slug": current_char.slug,
            "sender_name": prof["display_name"],
            "text": clean_text,
            "time": now_hm,
            "ts": time.time(),
            "reactions": {},
        }
        if sticker_data:
            msg["sticker"] = sticker_data
        if voice_data:
            msg["voice"] = voice_data
            if not msg["text"]:
                msg["text"] = voice_data["transcript"]
        if photo_data:
            if clean_text and not voice_data:
                photo_data["caption"] = clean_text
            msg["photo"] = photo_data
        if file_data:
            msg["file"] = file_data
        bubbles.append(msg)

    return {
        "reactions": reactions,
        "profile_updates": profile_updates,
        "events": new_events,
        "bubbles": bubbles,
    }


# ---------------------------------------------------------------------------
# ElevenLabs Voice Note & Nano Banana Photo Generation for Messenger Bubbles
# ---------------------------------------------------------------------------

def synthesize_voice_bubble(user, character, transcript):
    """
    Generate an MP3 voice note for a Messenger bubble using ElevenLabs on OpenRouter (`voice.synthesize_single`)
    or the user's direct ElevenLabs API key, saving it to storage.
    """
    raw = str(transcript or "").strip()
    if not raw:
        raise voice.VoiceError("Nothing to read aloud.")
    prof = char_profile(character)
    vid = prof.get("voice_id") or character.eleven_voice_char_id or "sarah"
    v_model = prof.get("voice_model") or voice.OPENROUTER_TTS_MODEL_DEFAULT

    mp3_bytes = voice.synthesize_single(user, raw[:2500], voice_id=vid, model=v_model)
    rel_path = f"messenger/voice/{character.slug}-{uuid.uuid4().hex[:8]}.mp3"
    saved_path = default_storage.save(rel_path, ContentFile(mp3_bytes))
    return default_storage.url(saved_path)


def preview_voice(user, voice_id="sarah", sample_text="", model=None):
    """
    Generate a short MP3 voice preview for any of the 21 OpenRouter ElevenLabs voices or a custom ElevenLabs Voice ID.
    """
    v_str = str(voice_id or "sarah").strip() or "sarah"
    v_meta = voice.OPENROUTER_VOICE_NAMES.get(v_str.lower())
    v_label = v_meta["name"] if v_meta else v_str[:16]
    text = str(sample_text or "").strip() or f"[curious] Hey, it's {v_label}. Just checking if my voice sounds clear on your end."
    mp3_bytes = voice.synthesize_single(user, text[:400], voice_id=v_str, model=model)
    rel_path = f"messenger/voice/preview-{uuid.uuid4().hex[:8]}.mp3"
    saved_path = default_storage.save(rel_path, ContentFile(mp3_bytes))
    return default_storage.url(saved_path)


def _read_storage_image(url_or_field):
    """Read `(bytes, mime_type)` from either an ImageField or a `/media/...` storage URL."""
    if not url_or_field:
        return None
    try:
        if hasattr(url_or_field, "open"):
            with url_or_field.open("rb") as f:
                raw = f.read()
            name = (getattr(url_or_field, "name", "") or "").lower()
        else:
            path_str = str(url_or_field).strip()
            from django.conf import settings
            media_url = getattr(settings, "MEDIA_URL", "/media/") or "/media/"
            if path_str.startswith(media_url):
                rel = path_str[len(media_url):]
            elif "/media/" in path_str:
                rel = path_str.split("/media/", 1)[1]
            else:
                rel = path_str.lstrip("/")
            if not default_storage.exists(rel):
                return None
            with default_storage.open(rel, "rb") as f:
                raw = f.read()
            name = rel.lower()
        if not raw:
            return None
        mime = "image/png"
        if name.endswith((".jpg", ".jpeg")):
            mime = "image/jpeg"
        elif name.endswith(".webp"):
            mime = "image/webp"
        return (raw, mime)
    except Exception:
        return None


def load_character_references(character):
    """
    Gather up to 5 reference images for `character`:
    - 1 Neutral Reference Portrait (`prof['neutral_url']` or `character.photo_neutral`)
    - Up to 4 Extra Reference Pictures (`prof['extra_refs']`, falling back to any character mood sprites if fewer than 4 are set)
    Returns a list of `(bytes, mime_type)`.
    """
    prof = char_profile(character)
    refs = []
    seen_urls = set()

    # 1. Neutral picture first
    neutral_u = prof.get("neutral_url") or ""
    if neutral_u:
        item = _read_storage_image(neutral_u)
        if item:
            refs.append(item)
            seen_urls.add(neutral_u)
    if not refs and getattr(character, "photo_neutral", None) and character.photo_neutral:
        item = _read_storage_image(character.photo_neutral)
        if item:
            refs.append(item)
            try:
                seen_urls.add(character.photo_neutral.url)
            except Exception:
                pass

    # 2. Up to 4 extra reference pictures from `extra_refs`
    for u in (prof.get("extra_refs") or [])[:4]:
        if u and u not in seen_urls and len(refs) < 5:
            item = _read_storage_image(u)
            if item:
                refs.append(item)
                seen_urls.add(u)

    return refs[:5]


def generate_character_references_from_description(user, character, count=2):
    """
    For OCs (or characters without reference pictures yet), generate:
    1. A clean Neutral Reference Portrait from their `appearance_notes` & `art_style_notes` (if no neutral picture exists or requested).
    2. Up to `count - 1` Extra Reference Pictures (varied expression/angle/full-body outfit) anchored to the neutral portrait.
    Saves the URLs into `character.messenger_profile` (and sets `character.photo_neutral` if empty).
    """
    prof = char_profile(character)
    app_text = prof.get("appearance_notes") or (character.description or "")[:800]
    if not app_text.strip():
        raise ai_client.AIError("Add an appearance description first so Nano Banana knows what the character looks like.")
    style_text = prof.get("art_style_notes") or "expressive digital character illustration, clean lines, rich atmospheric lighting"
    setting_note = "modern-day outfit and styling" if prof.get("mode") == "modern_au" else "signature in-world outfit"

    total_cost = 0.0
    neutral_item = _read_storage_image(prof.get("neutral_url")) or (
        _read_storage_image(character.photo_neutral) if getattr(character, "photo_neutral", None) else None
    )
    neutral_url = prof.get("neutral_url") or ""

    # Step 1: Generate Neutral Portrait if missing
    if not neutral_item:
        neutral_prompt = (
            f"Create a clear, high-quality character reference portrait of {character.name} ({setting_note}).\n"
            f"Visual art style: {style_text}.\n"
            f"Appearance details: {app_text[:900]}\n"
            f"Composition: clean chest-up 3/4 portrait, neutral-characteristic expression, clear facial features, hair, and eyes."
        )
        img_bytes, cost = make_picture(user, neutral_prompt)
        total_cost += float(cost or 0.0)
        rel_path = f"messenger/refs/{character.slug}-neutral-{uuid.uuid4().hex[:8]}.png"
        saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
        neutral_url = default_storage.url(saved_path)
        neutral_item = (img_bytes, "image/png")
        if not getattr(character, "photo_neutral", None) or not character.photo_neutral:
            character.photo_neutral.name = saved_path
            character.save(update_fields=["photo_neutral"])

    # Step 2: Generate additional reference angles/expressions up to requested count (max 4 extra)
    extra_refs = list(prof.get("extra_refs") or [])
    extra_variants = [
        "waist-up candid three-quarter angle showing everyday posture, outfit silhouette, and signature attitude",
        "close-up angled portrait with a subtle in-character smirk or expressive sideways glance, dynamic lighting",
        "relaxed candid medium shot in their typical daily environment showing hands, clothing texture, and build",
        "over-the-shoulder or slightly low-angle candid character reference showing profile and hairstyle details",
    ]
    needed_extra = max(0, min(4 - len(extra_refs), int(count or 2) - (0 if prof.get("neutral_url") else 1)))
    if needed_extra == 0 and len(extra_refs) < 4 and int(count or 1) >= 1 and prof.get("neutral_url"):
        needed_extra = min(4 - len(extra_refs), int(count or 1))

    for i in range(needed_extra):
        variant_desc = extra_variants[(len(extra_refs) + i) % len(extra_variants)]
        ref_prompt = (
            f"Create an additional character reference sheet image of {character.name} keeping the EXACT same face, hair, eyes, "
            f"proportions, and art style ({style_text}) as the reference portrait.\n"
            f"Appearance details: {app_text[:800]}\n"
            f"Pose & angle: {variant_desc}."
        )
        img_bytes, cost = make_picture(user, ref_prompt, references=[neutral_item] if neutral_item else None)
        total_cost += float(cost or 0.0)
        rel_path = f"messenger/refs/{character.slug}-ref{len(extra_refs)+1}-{uuid.uuid4().hex[:8]}.png"
        saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
        extra_refs.append(default_storage.url(saved_path))

    updated_prof = save_char_profile(character, {
        "neutral_url": neutral_url,
        "avatar_url": prof.get("avatar_url") or neutral_url,
        "extra_refs": extra_refs[:4],
    })
    return updated_prof, round(total_cost, 4)


SELFIE_CAMERA_ANGLES = (
    "slightly high-angle arm's-length front-camera smartphone selfie, looking up at the lens",
    "mirror selfie showing phone in hand, casual off-center framing and room reflection",
    "close-up off-center candid front-camera shot resting chin on hand or leaning against a surface",
    "low-angle casual front-camera snapshot tilted slightly, natural candid posture",
    "over-the-shoulder glance back toward the smartphone camera, dynamic candid framing",
    "half-face / cropped casual front-camera selfie with natural depth of field and ambient lighting",
)

POV_CAMERA_ANGLES = (
    "first-person point-of-view (POV) rear-camera smartphone snapshot taken from eye level looking down at what is in front of them",
    "casual rear-camera tabletop / overhead 45-degree angle smartphone photo (maybe their hand or sleeve edge visible near the frame)",
    "rear-camera smartphone snapshot looking out through a window or across their current environment, candid framing",
)

SCENE_ESSENCE_PROMPT = """You extract the visual essence of a live Telegram chat moment so Nano Banana can generate the exact photo {char} is snapping right now.

Character: {char} ({mode_desc})
Appearance: {appearance}
Art / Visual Style: {art_style}
Current real-world time: {clock}
Scenario: {scenario}
Photo type requested: {kind_desc}

Recent chat messages:
{recent_chat}

Decide whether {char} is snapping:
- "selfie" (a photo of themselves in this moment), OR
- "pov_object" (a rear-camera photo of their food, drink, desk, book, street, pet, or view—without their face, or only their hand/sleeve in frame), OR
- "candid_medium" (a timer/mirror/friend shot showing {char} in their environment).

Rules:
- Vary camera angles naturally! Never default to a stiff passport-style centered mugshot.
- Even if it is a food, desk, or scenery photo ("pov_object"), specify the exact same illustration/art style, color palette, and lighting aesthetic so it matches {char}'s visual world.

Answer with JSON only:
{{
  "shot_type": "selfie" | "pov_object" | "candid_medium",
  "camera_angle": "specific camera angle and lens framing (1 short sentence)",
  "visual_prompt": "vivid 2-3 sentence visual description of the subject, lighting, setting, mood, and details of the photo",
  "caption": "optional short 2-8 word caption in {char}'s texting voice (or empty string)"
}}"""


def describe_photo_scene(user, thread, character, kind="casual", hint=""):
    """
    Under-the-hood context reader: reads the recent conversation in `thread`, the real-time clock, and
    `character`'s persona/scenario, and distills the exact visual scene, shot type, and varied camera angle.
    """
    prof = char_profile(character)
    rt = real_time_context(thread) if thread else {"clock": "now", "time_of_day": "day"}
    data = thread_data(thread) if thread else {"messages": []}
    recent_lines = []
    for m in (data.get("messages") or [])[-10:]:
        if m.get("role") == "system":
            continue
        sp = m.get("sender_name") or m.get("role")
        txt = m.get("text") or (m.get("photo") or {}).get("prompt") or ""
        if txt:
            recent_lines.append(f"{sp}: {txt[:220]}")
    recent_chat = "\n".join(recent_lines) or "(Start of chat)"
    if hint:
        recent_chat += f"\n[Specific photo direction: {hint}]"

    kind_desc = (
        "Casual everyday smartphone photo (could be a varied-angle selfie, mirror shot, OR a POV photo of their food/coffee/desk/scenery depending on what they were just talking about)"
        if kind != "tease"
        else "Tasteful, alluring, flirty/intimate candid smartphone selfie or mirror shot that fits their personality and current mood"
    )
    prompt = SCENE_ESSENCE_PROMPT.format(
        char=character.name,
        mode_desc="Modern AU" if prof["mode"] == "modern_au" else "Original setting",
        appearance=(prof.get("appearance_notes") or character.description or "")[:600],
        art_style=prof.get("art_style_notes") or "match reference image art style and color palette",
        clock=rt.get("clock", ""),
        scenario=(prof.get("scenario") or "")[:500],
        kind_desc=kind_desc,
        recent_chat=recent_chat,
    )
    try:
        parsed = ask_json(user, prompt, need=("visual_prompt",), max_tokens=700, task="summary", temperature=0.7)
        if parsed:
            if parsed.get("visual_prompt"):
                return {
                    "shot_type": parsed.get("shot_type") if parsed.get("shot_type") in ("selfie", "pov_object", "candid_medium") else "selfie",
                    "camera_angle": str(parsed.get("camera_angle") or "").strip()[:240],
                    "visual_prompt": str(parsed.get("visual_prompt") or "").strip()[:700],
                    "caption": str(parsed.get("caption") or "").strip()[:160],
                }
    except Exception as e:
        log.info("Scene essence fallback used: %s", e)

    import random
    angle = random.choice(SELFIE_CAMERA_ANGLES)
    return {
        "shot_type": "selfie",
        "camera_angle": angle,
        "visual_prompt": hint or f"Candid smartphone photo of {character.name} during {rt.get('time_of_day', 'the day')}, {angle}.",
        "caption": "",
    }


NO_PERSON = re.compile(
    r"^\s*no people\b|without (?:you|him|her|them|me|himself|herself|themselves|the character|anyone|people)\b|"
    r"\bno (?:people|person|one|faces?|selfie)\b|\bnobody\b|\bnot (?:a )?selfie\b|don'?t (?:show|include) (?:you|him|her|them)|"
    r"\bбез (?:тебе|нього|неї|них|людей|себе)\b|\bне селфі\b|\bбез тебя\b|\bне селфи\b", re.I)


def _wants_no_person(desc):
    """The photo is asked to leave the character (and everyone) out: "a photo of your lunch, without you"."""
    return bool(NO_PERSON.search(str(desc or "")))


def _looks_like_non_person_photo(desc):
    low = str(desc or "").lower()
    has_object = any(w in low for w in ("food", "coffee", "tea", "mug", "cup", "plate", "dinner", "lunch", "breakfast", "desk", "laptop", "window", "view", "street", "rain", "sky", "sunset", "cat", "dog", "book", "notes", "scenery", "room"))
    has_self = any(w in low for w in ("selfie", "mirror", "face", "smirk", "smile", "looking at camera", "wearing", "eyes", "hair", "pose"))
    return has_object and not has_self


def generate_messenger_photo(user, character, description="", kind="casual", thread=None, shot_type=None, camera_angle=""):
    """
    Generate a snapshot / selfie / POV food or scenery / tease photo for `character` using Nano Banana (`ai_client.generate_image`):
    - Passes 1 Neutral Reference + up to 4 Extra Reference images (`load_character_references`) so both the character's identity
      AND the exact art/rendering style stay locked.
    - If `description` is empty (or very short), automatically calls `describe_photo_scene` to read the recent chat context.
    - Ensures camera angles on selfies vary dynamically (high-angle, mirror selfie, off-center chin-on-hand, over-the-shoulder, etc.).
    - Ensures food, desk, and scenery POV photos keep the exact same art style, brush/lighting aesthetic, and color palette as the character references.
    """
    import random
    prof = char_profile(character)
    card_appearance = prof.get("appearance_notes") or ""
    if not card_appearance and character.sections:
        cleaned = card_sections.clean(character.sections)
        if cleaned and cleaned.get("people"):
            card_appearance = (cleaned["people"][0].get("sections", {}).get("appearance") or {}).get("text") or ""
    if not card_appearance:
        card_appearance = (character.description or "")[:600]

    art_style = prof.get("art_style_notes") or "exact same art style, linework, shading, and color palette as the reference image(s)"
    desc_clean = str(description or "").strip()

    # If no explicit description was supplied (or it's a generic placeholder), extract scene essence from the thread
    if not desc_clean or desc_clean in ("casual selfie", f"candid smartphone selfie of {character.name} in their current setting"):
        scene = describe_photo_scene(user, thread, character, kind=kind, hint=desc_clean)
        desc_clean = scene["visual_prompt"]
        shot_type = shot_type or scene["shot_type"]
        camera_angle = camera_angle or scene["camera_angle"]

    if _wants_no_person(description) or _wants_no_person(desc_clean):  # asked for no people: no people, whatever else
        shot_type = "pov_object"
    if not shot_type:
        shot_type = "pov_object" if (kind != "tease" and _looks_like_non_person_photo(desc_clean)) else "selfie"
    if not camera_angle:
        camera_angle = random.choice(POV_CAMERA_ANGLES if shot_type == "pov_object" else SELFIE_CAMERA_ANGLES)

    refs = load_character_references(character)
    setting_note = "modern-day setting" if prof["mode"] == "modern_au" else "in-world setting"

    if shot_type == "pov_object":
        # No people in it: their portraits stay out (image models copy whoever is in a reference). With an art style in
        # words, none at all; without one, a single picture labelled as style only.
        refs = [] if prof.get("art_style_notes") else refs[:1]
        subject = re.sub(r"^\s*no people\s*:\s*", "", desc_clean, flags=re.I)
        prompt = (
            f"Create a candid smartphone photo taken by {character.name} in a {setting_note}, of what they're looking at.\n"
            f"NO PEOPLE: nobody is in this photo. {character.name} does not appear (no face, no body, no reflection); "
            f"at most a hand holding something, if that's natural.\n"
            + (f"The attached picture is a STYLE REFERENCE ONLY: copy its art style, rendering, lighting and colours, and "
               f"never the person in it.\n" if refs else "")
            + f"CRITICAL STYLE LOCK: art style: {art_style}. Do NOT switch to stock photorealism if the style is illustrated/anime, and vice versa.\n"
            f"Camera angle & framing: {camera_angle}.\n"
            f"Photo subject & scene: {subject[:600]}"
        )
    else:
        style_note = (
            "candid smartphone photo / selfie sent in a private chat app, natural atmospheric lighting, expressive and in-character"
            if kind != "tease"
            else "intimate, alluring candid smartphone photo / mirror selfie sent in a private chat app, tasteful atmospheric lighting, in-character"
        )
        prompt = (
            f"Create a {style_note} ({setting_note}) of {character.name}.\n"
            f"CRITICAL IDENTITY & STYLE LOCK: Keep the EXACT same face, hair, eyes, body proportions, and visual art style ({art_style}) "
            f"as the attached reference image(s).\n"
            f"Camera angle & composition (avoid stiff centered passport framing): {camera_angle}.\n"
            f"Character appearance: {card_appearance[:550]}\n"
            f"Photo scene & moment: {desc_clean[:600]}"
        )

    img_bytes, cost = make_picture(user, prompt, references=refs)
    rel_path = f"messenger/photos/{character.slug}-{uuid.uuid4().hex[:8]}.png"
    saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
    return default_storage.url(saved_path), cost


# ---------------------------------------------------------------------------
# Generating a Turn in a MessengerThread
# ---------------------------------------------------------------------------

def regenerate_turn(user, thread, note=""):
    """↻ A different take on the characters' last reply: it comes off (everything after the user's last message;
    kept in data["regen_prev"] for now), and the turn is written again, with the user's note if they gave one
    ("send a voice note this time", "a selfie, please", "be meaner")."""
    raw = thread.data if isinstance(thread.data, dict) else {}
    msgs = [m for m in (raw.get("messages") or []) if isinstance(m, dict)]
    last_user = max((i for i, m in enumerate(msgs) if m.get("role") == "user"), default=-1)
    tail = msgs[last_user + 1:]
    if not any(m.get("role") == "assistant" for m in tail):
        raise ai_client.AIError("There's no reply after your last message to try again.")
    data = dict(raw)
    data["messages"], data["regen_prev"] = msgs[:last_user + 1], tail
    thread.data = data
    thread.save(update_fields=["data"])
    note = str(note or "").strip()[:600]
    instruction = ("Write your reply to the user's last message again, differently from before."
                   + (f" The user's note for this take (follow it, in character): {note}" if note else ""))
    return generate_turn(user, thread, extra_instruction=instruction)


def redo_message(user, thread, message_id, note=""):
    """↻ One of the characters' messages written again (any of a burst), with the user's note: the model sees the
    chat up to that message, the old version and the note, and answers with that one message. A voice note keeps
    being a voice note (new words, the audio made again on play). Returns the changed message."""
    from mainapp import samplers, thinking
    data = thread_data(thread)
    idx = next((i for i, m in enumerate(data["messages"]) if m.get("id") == message_id), None)
    if idx is None or data["messages"][idx].get("role") != "assistant":
        raise ai_client.AIError("That message isn't one of theirs.")
    target = data["messages"][idx]
    old = (target.get("voice") or {}).get("transcript") or target.get("text") or ""
    if not old.strip():
        raise ai_client.AIError("There's no text in that message to write again (for a photo, redo the picture).")
    sender = target.get("sender_name") or "the character"
    note = str(note or "").strip()[:600]
    instruction = (f"Rewrite only {sender}'s next text message, the one that comes right here. The old version was: "
                   f"\"{old[:1500]}\". Write a different take of that one message, in {sender}'s voice and texting style"
                   + (f", following the user's note: {note}" if note else "")
                   + ". Answer with that one message only: no name in front, no other messages, no tags"
                   + (", spoken words for a voice note (delivery tags like [sighs] allowed)" if target.get("voice") else "") + ".")
    saved = thread.data
    thread.data = {**(saved or {}), "messages": data["messages"][:idx]}  # the chat as it was before that message
    try:
        prompt_messages = build_messenger_prompt(user, thread, extra_instruction=instruction)
    finally:
        thread.data = saved
    params = {"max_tokens": 600, "temperature": 0.9}
    _, chat_model = ai_client.resolve(user, "chat")
    if thinking.needs_leash(chat_model, samplers.thinking_now(user)):
        prompt_messages, params = thinking.leash(prompt_messages, params)
    raw = ai_client.complete(user, "chat", prompt_messages, **params)
    _, text = thinking.split(raw or "")
    text = strip_stage_directions(re.sub(r"^\s*" + re.escape(sender) + r"\s*:\s*", "", text.strip(), flags=re.I)).strip()
    if not text:
        raise ai_client.AIError("The model sent nothing back. Try again.")
    if target.get("voice"):
        target["voice"] = {**target["voice"], "transcript": text, "audio_url": "",
                           "duration": max(2, min(45, len(text.split()) // 2))}
    else:
        target["text"] = text
    target["edited_by_redo"] = True
    save_thread_data(thread, data)
    return target


def see_photo(user, url, their_words=""):
    """👁️ What a picture the user sent shows, in words (the vision model looks once), so the character can see it.
    "" when it can't be looked at (the character then only knows a photo came)."""
    from mainapp.bulba import vision
    item = _read_storage_image(url)
    if not item:
        return ""
    try:
        data_url, _ = vision.prepare(item[0])
        text, _ = vision.describe(user, data_url, their_words)
    except (ValueError, ai_client.AIError) as e:
        log.info("messenger: couldn't look at a sent photo: %s", e)
        return ""
    return text.strip()[:1200]


STATUS_EVERY = 6 * 3600  # a character's own statuses: at most one per 6-12 hours (a fixed jitter per character and day)


def status_due(character, now=None):
    """Whether it's time for this character's own next status."""
    import hashlib
    now = now or time.time()
    last = max([ts_of(s) for s in char_profile(character).get("stories") or []] or [0])
    jitter = int(hashlib.md5(f"{character.slug}{int(now // 86400)}".encode()).hexdigest(), 16) % STATUS_EVERY
    return now - last >= STATUS_EVERY + jitter


def post_own_status(user, character, thread=None):
    """✨ A status the character posts on their own: something from their day that fits the hour, who they are here
    and what's been happening in your texts; sometimes with a picture (made when it's viewed). Returns the story."""
    prof = char_profile(character)
    recent = ""
    if thread is not None:
        msgs = delivered(thread_data(thread)["messages"])[-12:]
        recent = "\n".join(f"{'them' if m.get('role') == 'assistant' else 'the user'}: {(m.get('text') or '')[:200]}"
                           for m in msgs if m.get("text"))
    rt = real_time_context(thread) if thread is not None else {"clock": timezone.localtime(timezone.now()).strftime("%A %H:%M")}
    prompt = (f"{character.name} posts a messenger status (like a Telegram story) on their own. It's {rt['clock']}.\n"
              f"Who they are here: {(prof['modern_persona'] or character.description or '')[:900]}\n"
              f"How they text: {prof['texting_style'][:300]}\nTheir scenario: {prof['scenario'][:400]}\n"
              + (f"Recent texts with the user:\n{recent}\n" if recent else "")
              + "Write one status that fits the hour and their life: short, in their voice, not addressed to the user "
                "directly (it's for everyone). Add a picture only when it makes the status (their coffee, the view, a "
                "mess on their desk); describe it, with 'No people:' first when they're not in it.\n"
                'Answer with JSON only: {"emoji": "one emoji", "text": "the status", "photo": "what the picture shows, or empty"}')
    data = ask_json(user, prompt, need=("text",), max_tokens=400, task="summary", temperature=0.9)
    story = {"id": uuid.uuid4().hex[:8], "emoji": str(data.get("emoji") or "💬")[:12], "text": str(data["text"])[:280],
             "photo_prompt": str(data.get("photo") or "")[:500], "image_url": "",
             "at": timezone.localtime(timezone.now()).strftime("%H:%M"), "ts": time.time(), "own": True}
    save_char_profile(character, {"stories": [story, *(prof.get("stories") or [])][:30], "status_emoji": story["emoji"]})
    return story


ONE_REF_SHOTS = (
    "a clean chest-up three-quarter portrait, calm in-character expression",
    "a waist-up candid shot that shows their outfit and posture",
    "a close-up with an expressive in-character look, dynamic light",
    "a relaxed medium shot in their usual surroundings, hands and clothes visible",
    "a three-quarter view from a slightly low angle, profile and hair visible",
)


def one_reference(user, character, slot):
    """✨/↻ One reference picture, just this one: slot -1 is the neutral portrait (drawn from the description, the
    face kept from any pictures they have), 0-3 an extra reference made from the neutral one. Returns the profile."""
    prof = char_profile(character)
    look = (prof.get("appearance_notes") or character.description or "")[:1200]
    if not look.strip():
        raise ai_client.AIError("Add how they look (Appearance) first: the picture is drawn from it.")
    style = prof.get("art_style_notes") or "expressive digital character illustration, clean lines, rich atmospheric lighting"
    setting = "a modern-day setting" if prof.get("mode") == "modern_au" else "their own world"
    slot = int(slot)
    if slot < 0:
        refs, shot = load_character_references(character)[:3], ONE_REF_SHOTS[0]
    else:
        neutral = _read_storage_image(prof.get("neutral_url")) if prof.get("neutral_url") else None
        if not neutral:
            raise ai_client.AIError("Make the neutral portrait first: the other references are made from it.")
        refs, shot = [neutral], ONE_REF_SHOTS[1 + min(slot, 3)]
    same = "Keep them the SAME person as in the reference pictures: same face, hair, eyes, skin and build. " if refs else ""
    img, _ = make_picture(user, f"{same}Draw {character.name} in {setting}: {shot}.\nHow they look: {look}\n"
                                f"Art style: {style}.", references=refs)
    url = default_storage.url(default_storage.save(f"messenger/refs/{character.slug}-{uuid.uuid4().hex[:8]}.png", ContentFile(img)))
    if slot < 0:
        return save_char_profile(character, {"neutral_url": url, "avatar_url": url})
    extra = list(prof.get("extra_refs") or [])
    if slot < len(extra):
        extra[slot] = url
    else:
        extra.append(url)
    return save_char_profile(character, {"extra_refs": extra[:4]})


def user_picture(user, thread, description, ref_urls=(), with_me=True):
    """🎨 A picture the user sends: a photo of them (their persona picture as the reference) or of anything, with up
    to 5 references (their persona, the character's pictures for a photo of the two of them, uploads), in the chat's
    art style. Returns (url, the description the character reads)."""
    description = str(description or "").strip()[:800]
    if not description:
        raise ValueError("Describe the picture first.")
    persona = thread_data(thread).get("persona") or {}
    me_name = persona.get("name") or (getattr(user, "persona_name", "") or "").strip() or "the user"
    me_look = (persona.get("description") or getattr(user, "persona_description", "") or "")[:600]
    refs = []
    if with_me and getattr(user, "persona_photo_neutral", None):
        item = _read_storage_image(user.persona_photo_neutral)
        if item:
            refs.append(item)
    for u in list(ref_urls)[:5]:
        item = _read_storage_image(u)
        if item and len(refs) < 5:
            refs.append(item)
    first = thread.characters.first()
    style = (char_profile(first).get("art_style_notes") if first else "") or "the same art style as the reference pictures"
    people = (f"{me_name} is in it" + (" (the person in the first reference picture: keep their face, hair and build)"
                                         if with_me and refs else "") + (f". How they look: {me_look}" if me_look else "")
              if with_me else "NO PEOPLE unless the description names someone")
    prompt = (f"A candid smartphone photo that {me_name} took and sends in a private chat. {people}.\n"
              f"Other reference pictures, if any, show people or things that belong in the photo: keep them as they are.\n"
              f"Art style: {style}.\nWhat the photo shows: {description}")
    img, _ = make_picture(user, prompt, references=refs)
    saved = default_storage.save(f"messenger/user/{user.id}-{uuid.uuid4().hex[:8]}.png", ContentFile(img))
    return default_storage.url(saved), (f"{me_name}: " if with_me else "") + description


def story_picture(user, character, story_id):
    """🖼️ The picture of a status that has a description but no picture yet. Returns the story."""
    prof = char_profile(character)
    stories = list(prof.get("stories") or [])
    story = next((s for s in stories if s.get("id") == story_id), None)
    if story is None or not story.get("photo_prompt"):
        raise ValueError("That status has no picture to make.")
    if not story.get("image_url"):
        url, _ = generate_messenger_photo(user, character, story["photo_prompt"], kind="casual")
        story["image_url"] = url
        save_char_profile(character, {"stories": stories})
    return story


def ts_of(m):
    """A message's time as seconds (stored as a number, or as an ISO date by older code); 0 when unreadable."""
    v = (m or {}).get("ts")
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        try:
            when = datetime.fromisoformat(str(v))
            return (timezone.make_aware(when) if timezone.is_naive(when) else when).timestamp()
        except ValueError:
            return 0.0


def presence(data, now=None):
    """🟢 How they look in the list: "away" (yellow) while a reply left on read waits, "busy" (red) when it waits
    for a busy reason (work, sleep, class...), "online" (green) when they texted in the last 20 minutes, else
    "last seen" (grey) with the time."""
    now = now or time.time()
    waiting = [m for m in data["messages"] if m.get("deliver_at") and m["deliver_at"] > now]
    if waiting:
        busy = any(re.search(r"busy|work|meeting|class|sleep|asleep|shift|lab|driving|зайнят|робот|сплю|зайня",
                             str(m.get("late_reason") or ""), re.I) for m in waiting)
        return {"state": "busy" if busy else "away", "label": "busy" if busy else "away"}
    last = next((m for m in reversed(delivered(data["messages"], now)) if m.get("role") == "assistant"), None)
    if last and now - ts_of(last) < 20 * 60:
        return {"state": "online", "label": "online"}
    return {"state": "seen", "label": f"last seen {last.get('time')}" if last and last.get("time") else "last seen recently"}


def _watch_on(user):
    try:
        from mainapp.bulba import watch
        return watch.is_on(user)
    except Exception:
        return False


CONTEXT_SIZES = (20, 30, 60, 100)
MEMORY_EVERY = 20  # messages out of view before the summary is brought up to date


def memory_due(data):
    """Whether enough messages have fallen out of view since the last summary."""
    out_of_view = len(delivered(data["messages"])) - data["context_size"]
    return out_of_view - data["memory_upto"] >= MEMORY_EVERY


def update_memory(user, thread, force=False):
    """🧠 The chat's memory brought up to date: the messages that fell out of view since the last time, folded into
    the running summary (on the background model). Returns the summary."""
    data = thread_data(thread)
    msgs = delivered(data["messages"])
    end = max(0, len(msgs) - data["context_size"])
    if force:
        end = max(end, len(msgs) - 6)  # "update it now": everything but the last few
    new = msgs[data["memory_upto"]:end]
    if not new:
        return data["memory"]
    from mainapp.cards import user_name
    u_name = (data.get("persona") or {}).get("name") or user_name(user)
    lines = []
    for m in new:
        who = u_name if m.get("role") == "user" else (m.get("sender_name") or "them")
        what = m.get("text") or (m.get("voice") or {}).get("transcript") or ((m.get("photo") or {}).get("seen") or (m.get("photo") or {}).get("prompt") or "")
        if what:
            lines.append(f"{who}: {what[:400]}")
    prompt = ("You keep the memory of a messenger chat. Fold the new messages into the summary so far: what happened, "
              "facts that matter later (names, plans, places, what each one shared), promises and when they're due, "
              "and how they feel about each other now. Keep what still matters, drop what doesn't; at most 300 words, "
              "plain sentences, in the language of the chat.\n\n"
              f"Summary so far:\n{data['memory'] or '(nothing yet)'}\n\nNew messages:\n" + "\n".join(lines) +
              '\n\nAnswer with JSON only: {"summary": "..."}')
    out = ask_json(user, prompt, need=("summary",), max_tokens=900, task="summary", temperature=0.3)
    raw = dict(thread.data or {})
    raw["memory"], raw["memory_upto"] = str(out["summary"]).strip()[:6000], end
    thread.data = raw
    thread.save(update_fields=["data"])
    return raw["memory"]


def delivered(messages, now=None):
    """The messages the user can see: a reply left on read (deliver_at) shows only once its time has come."""
    now = now or time.time()
    return [m for m in messages if not m.get("deliver_at") or m["deliver_at"] <= now]


def waiting_reply(data, now=None):
    """Seconds until a reply left on read arrives (0: nothing waiting)."""
    now = now or time.time()
    due = [m["deliver_at"] for m in data["messages"] if m.get("deliver_at") and m["deliver_at"] > now]
    return int(max(due) - now) + 1 if due else 0


def generate_turn(user, thread, extra_instruction="", auto_check_in=False):
    """
    Call the user's chat model to produce the next Messenger turn (1..N bubbles, reactions, profile updates, etc.),
    apply them to `thread`, and return the new items.
    """
    chars = list(thread.characters.all())
    if not chars:
        raise ai_client.AIError("Add at least one character to this chat first.")
    u_prof = user_profile(user)
    data = thread_data(thread)
    wait = waiting_reply(data)
    if wait:  # 🙈 they left it on read: their reply comes when it comes, not a second one now
        return {"later": wait, "bubbles": [], "system_notices": [], "reactions": [], "events": data["events"],
                "warnings": [], "active_model": active_model_texting_rules(user)}

    if auto_check_in:
        rt = real_time_context(thread)
        extra_instruction = (
            f"{user.username} hasn't texted in {rt['elapsed_text']} (it is now {rt['clock']}) and is currently away/busy. "
            f"Send ONE short, natural check-in: a text, or a voice note ([VOICE: ...]) if that's how they'd do it, or "
            f"a status update; whatever fits your character and "
            f"what was happening last. Do not be clingy if your character is aloof."
        )

    prompt_messages = build_messenger_prompt(user, thread, extra_instruction=extra_instruction)
    from mainapp import samplers, thinking
    params = {"max_tokens": 1200, "temperature": 0.85}
    _, chat_model = ai_client.resolve(user, "chat")
    if thinking.needs_leash(chat_model, samplers.thinking_now(user)):  # MiMo: think briefly, then text (as in the chat)
        prompt_messages, params = thinking.leash(prompt_messages, params)
    raw_reply = ai_client.complete(user, "chat", prompt_messages, **params)
    _, raw_reply = thinking.split(raw_reply or "")  # thinking written inside the reply isn't a text message
    if not raw_reply.strip():
        raise ai_client.AIError("The model used its whole answer thinking and sent no text. Press ↻ Try again.")
    later, late_reason = 0, ""
    if data.get("leave_on_read"):  # 🙈 [LATER: N] at the start: the reply waits N real minutes (1-5)
        m_later = re.match(r"\s*\[\s*LATER\s*:\s*(\d+)\s*,?\s*([^\]]*)\]", raw_reply, re.I)
        if m_later:
            later = max(1, min(5, int(m_later.group(1)))) * 60
            late_reason = m_later.group(2).strip()[:80]  # "busy at the lab", "petty": red or yellow dot meanwhile
    raw_reply = re.sub(r"\[\s*LATER\s*:[^\]]*\]", "", raw_reply, flags=re.I)
    parsed = parse_ai_reply(raw_reply, chars, is_group=thread.is_group)

    # Apply reactions to the latest user message
    last_user_msg = next((m for m in reversed(data["messages"]) if m.get("role") == "user"), None)
    applied_reactions = []
    if last_user_msg and parsed["reactions"]:
        reacts = dict(last_user_msg.get("reactions") or {})
        for char_obj, emo in parsed["reactions"]:
            users_for_emo = list(reacts.get(emo) or [])
            if char_obj.name not in users_for_emo:
                users_for_emo.append(char_obj.name)
            reacts[emo] = users_for_emo
            applied_reactions.append({"message_id": last_user_msg.get("id"), "emoji": emo, "by": char_obj.name})
        last_user_msg["reactions"] = reacts

    # Apply profile updates (bio or status story)
    system_notices = []
    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
    for upd in parsed["profile_updates"]:
        c_obj = upd["char"]
        c_prof = char_profile(c_obj)
        if upd["kind"] == "bio":
            save_char_profile(c_obj, {"bio": upd["text"]})
            notice = {
                "id": uuid.uuid4().hex[:10],
                "role": "system",
                "text": f"{c_prof['display_name']} updated their bio: \"{upd['text']}\"",
                "time": now_hm,
                "ts": time.time(),
            }
            data["messages"].append(notice)
            system_notices.append(notice)
        elif upd["kind"] == "status":
            stories = list(c_prof.get("stories") or [])
            stories.insert(0, {
                "id": uuid.uuid4().hex[:8],
                "emoji": upd.get("emoji") or "💬",
                "text": upd["text"],
                "photo_prompt": upd.get("photo_prompt") or "",  # 🖼️ made when it's viewed (or at once with auto photos)
                "image_url": "",
                "at": now_hm,
                "ts": time.time(),
            })
            save_char_profile(c_obj, {"stories": stories[:30], "status_emoji": upd.get("emoji") or c_prof["status_emoji"]})
            notice = {
                "id": uuid.uuid4().hex[:10],
                "role": "system",
                "text": f"{c_prof['display_name']} posted a new status: {upd.get('emoji', '💬')} {upd['text']}",
                "time": now_hm,
                "ts": time.time(),
            }
            data["messages"].append(notice)
            system_notices.append(notice)

    # Apply new events
    for ev in parsed["events"]:
        data["events"].append(ev)

    # Optional auto-synthesis for voice or Nano Banana photos if enabled
    char_by_slug = {c.slug: c for c in chars}
    for b in parsed["bubbles"]:
        c_obj = char_by_slug.get(b.get("sender_slug")) or chars[0]
        if b.get("voice") and u_prof.get("auto_voice"):
            try:
                b["voice"]["audio_url"] = synthesize_voice_bubble(user, c_obj, b["voice"]["transcript"])
            except Exception as e:
                log.info("Auto voice synthesis skipped: %s", e)
        if b.get("photo") and u_prof.get("auto_photos"):
            try:
                url, _ = generate_messenger_photo(user, c_obj, b["photo"]["prompt"], b["photo"].get("kind", "casual"), thread=thread)
                b["photo"]["url"] = url
            except Exception as e:
                log.info("Auto photo generation skipped: %s", e)

    # If the model produced neither bubbles nor reactions, create a fallback bubble from raw text
    if not parsed["bubbles"] and not applied_reactions and raw_reply and raw_reply.strip():
        c0 = chars[0]
        p0 = char_profile(c0)
        fallback = {
            "id": uuid.uuid4().hex[:10],
            "role": "assistant",
            "sender_slug": c0.slug,
            "sender_name": p0["display_name"],
            "text": strip_stage_directions(raw_reply.strip())[:1000],
            "time": now_hm,
            "ts": time.time(),
            "reactions": {},
        }
        parsed["bubbles"].append(fallback)

    if later:  # kept now, shown when they "get back to the phone" (delivered() hides them until then)
        at = time.time() + later
        for i, b in enumerate(parsed["bubbles"]):
            b["deliver_at"] = b["ts"] = at + i * 2
            b["late_reason"] = late_reason
            b["time"] = timezone.localtime(timezone.now() + timezone.timedelta(seconds=later)).strftime("%H:%M")
    data["messages"].extend(parsed["bubbles"])
    if auto_check_in:
        data["unread"] = data.get("unread", 0) + len(parsed["bubbles"])
        data["last_auto_at"] = time.time()
    save_thread_data(thread, data)

    slop_warnings = []
    for b in parsed["bubbles"]:
        slop_warnings.extend(check_texting_slop(b.get("text") or ""))

    return {
        "later": later,
        "bubbles": [] if later else parsed["bubbles"],
        "system_notices": system_notices,
        "reactions": applied_reactions,
        "events": data["events"],
        "warnings": sorted(set(slop_warnings)),
        "active_model": active_model_texting_rules(user),
    }


def serialize_thread_summary(thread):
    """Compact summary for the left sidebar chat list."""
    chars = list(thread.characters.all())
    data = thread_data(thread)
    msgs = delivered(data["messages"])
    last = msgs[-1] if msgs else None
    preview = "No messages yet"
    last_time = ""
    if last:
        last_time = last.get("time") or ""
        if last.get("sticker"):
            preview = f"🎭 Sticker ({last['sticker'].get('name', 'Sticker')})"
        elif last.get("voice"):
            preview = f"🎤 Voice message: {(last['voice'].get('transcript') or '')[:45]}"
        elif last.get("photo"):
            preview = f"📷 Photo: {(last['photo'].get('caption') or last['photo'].get('prompt') or '')[:45]}"
        elif last.get("file"):
            preview = f"📎 {last['file'].get('name', 'File')}"
        else:
            preview = (last.get("text") or "")[:60]
        if thread.is_group and last.get("sender_name") and last.get("role") != "system":
            preview = f"{last['sender_name']}: {preview}"

    if thread.is_group:
        title = thread.title or ", ".join(c.name for c in chars[:3])
        avatar = char_avatar(chars[0]) if chars else ""
        subtitle = f"{len(chars)} members"
        handle = ""
        status_emoji = "👥"
        mode = "group"
    elif chars:
        c = chars[0]
        prof = char_profile(c)
        title = prof["display_name"]
        avatar = prof["avatar_url"]
        subtitle = prof["bio"] or prof["online_status"]
        handle = prof["handle"]
        status_emoji = prof["status_emoji"]
        mode = prof["mode"]
    else:
        title = thread.title or "Chat"
        avatar = ""
        subtitle = ""
        handle = ""
        status_emoji = "💬"
        mode = "canon"

    return {
        "id": thread.id,
        "title": title,
        "is_group": thread.is_group,
        "pinned": thread.pinned,
        "avatar_url": avatar,
        "subtitle": subtitle,
        "handle": handle,
        "status_emoji": status_emoji,
        "mode": mode,
        "unread": data.get("unread", 0),
        "preview": preview,
        "last_time": last_time,
        "presence": presence(data),
        "member_slugs": [c.slug for c in chars],
        "member_names": [c.name for c in chars],
        # 💬 chat files: this chat's own name (several chats with one character), a branch, when it was last used
        "chat_name": thread.title or "",
        "branch": bool((thread.data or {}).get("branch_of")),
        "updated": timezone.localtime(thread.updated).strftime("%d %b, %H:%M") if thread.updated else "",
        "count": len(msgs),
    }


def serialize_thread_full(thread, user):
    """Full thread payload for the active chat pane."""
    chars = list(thread.characters.all())
    data = thread_data(thread)
    rt = real_time_context(thread)
    members = []
    stickers = list(BUILT_IN_STICKERS)
    for idx, c in enumerate(chars):
        prof = char_profile(c)
        members.append({
            "slug": c.slug,
            "name": c.name,
            "color": NAME_COLORS[idx % len(NAME_COLORS)],
            "has_voice": bool(prof.get("voice_id") or c.eleven_voice_char_id),
            "set_up": is_set_up(c),
            "card_people": card_people(c),  # ✂️ several people on one card: offered a split
            **prof,
        })
        stickers.extend(character_stickers(c))
    u_prof = user_profile(user)
    stickers.extend(u_prof.get("custom_stickers") or [])
    return {
        **serialize_thread_summary(thread),
        "messages": delivered(data["messages"]),
        "watch": watch_notice(delivered(data["messages"])) if _watch_on(user) else None,  # 🥔 Bulba noticed…
        "memory": data["memory"], "context_size": data["context_size"], "memory_due": memory_due(data),
        "theme": data["theme"],
        "clock_offset": data["clock_offset"],
        "waiting": waiting_reply(data),  # 🙈 seconds until a reply left on read arrives
        "leave_on_read": data["leave_on_read"],
        "bg": data["bg"],
        "custom_bg_url": data["custom_bg_url"],
        "pinned_id": data["pinned_id"],
        "events": data["events"],
        "scenario_override": data["scenario_override"],
        "share_memory": data["share_memory"],
        "started": data["started"],
        "persona": data["persona"],
        "usual_persona": (getattr(user, "persona_name", "") or "").strip(),
        "real_time": rt,
        "members": members,
        "stickers": stickers,
        "active_model": active_model_texting_rules(user),
    }
