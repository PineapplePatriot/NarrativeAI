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
        "custom_stickers": [s for s in (raw.get("custom_stickers") or []) if isinstance(s, dict) and s.get("url")][:60],
        "notes": [n for n in (raw.get("notes") or []) if isinstance(n, dict)][:100],
        "browser_notifications": bool(raw.get("browser_notifications", False)),
        "in_app_toasts": bool(raw.get("in_app_toasts", True)),
        "spontaneous_texts": bool(raw.get("spontaneous_texts", False)),
        "spontaneous_minutes": max(2, min(1440, int(raw.get("spontaneous_minutes") or 15))),
        "auto_photos": bool(raw.get("auto_photos", False)),
        "auto_voice": bool(raw.get("auto_voice", False)),
        "default_bg": raw.get("default_bg") if raw.get("default_bg") in WALLPAPERS else "tg-night",
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
    for bool_key in ("browser_notifications", "in_app_toasts", "spontaneous_texts", "auto_photos", "auto_voice"):
        if bool_key in updates:
            current[bool_key] = bool(updates[bool_key])
    if "spontaneous_minutes" in updates:
        try:
            current["spontaneous_minutes"] = max(2, min(1440, int(updates["spontaneous_minutes"])))
        except (TypeError, ValueError):
            pass
    if "default_bg" in updates and updates["default_bg"] in WALLPAPERS:
        current["default_bg"] = updates["default_bg"]
    for list_key in ("stories", "custom_stickers", "notes"):
        if isinstance(updates.get(list_key), list):
            current[list_key] = [x for x in updates[list_key] if isinstance(x, dict)][:100]

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
        img, c = ai_client.generate_image(user, prompt, references=refs)
        cost += float(c or 0)
        saved = default_storage.save(f"messenger/refs/{character.slug}-{key}-{uuid.uuid4().hex[:8]}.png", ContentFile(img))
        out[key] = default_storage.url(saved)
        if key == "neutral":
            refs = [(img, "image/png")] + refs[:3]  # the outfit shot follows the new portrait
    extra = [out["outfit"]] + [u for u in prof.get("extra_refs") or [] if u != out["outfit"]]
    prof = save_char_profile(character, {"neutral_url": out["neutral"], "avatar_url": out["neutral"], "extra_refs": extra[:4]})
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


def character_stickers(character):
    """All mood sprites of a character packaged as a Telegram Sticker Pack."""
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
  "first_text": "Their opening text message (no stage directions)"
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
    if save:
        return save_char_profile(character, updates)
    merged = char_profile(character)
    merged.update(updates)
    return merged


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
        "regen_prev": [m for m in (raw.get("regen_prev") or []) if isinstance(m, dict)][:20],  # ↻ the take before
    }


def save_thread_data(thread, data):
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
    """Real-world clock, time elapsed since the last message, and scheduled events for the thread."""
    now = now or timezone.now()
    local_now = timezone.localtime(now) if timezone.is_aware(now) else now
    data = thread_data(thread)
    msgs = data["messages"]
    elapsed_sec = None
    last_sender = None
    if msgs:
        last_msg = msgs[-1]
        last_sender = last_msg.get("sender_name") or last_msg.get("role")
        ts = last_msg.get("ts")
        if isinstance(ts, (int, float)) and ts > 0:
            elapsed_sec = max(0, time.time() - float(ts))
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
   - React to {user}'s message: include `[REACT: ❤️]` (or 🔥 👍 😂 😮 😢 👀 😡 🤔) at the start or end.
   - Send a character mood sticker: include `[STICKER: mood_name]` choosing from their available moods ({moods}).
   - Send a voice message: wrap spoken audio in `[VOICE: [sighs] what they say out loud into the mic]` (supports delivery tags like `[laughs]`, `[whispers]`, `[sighs]`, `[sarcastic]`, `[curious]`).
   - Send a casual or tease photo (Nano Banana): include `[PHOTO: concrete visual description of the selfie, food, desk, or scenery photo they snap right now, including camera angle]` (or `[TEASE: description]` when flirty/intimate fits the relationship).
   - Send a file/document: include `[FILE: filename.txt | text content of the note, document, receipt, or schedule]`.
   - Update their own Telegram bio or post a status story when something changes: `[BIO: new bio text]` or `[STATUS: 🧪 | short status update]`.
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


def _character_block(character, user):
    from mainapp.cards import fill_names, user_name
    u_name = user_name(user)
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
    if prof["share_memory"]:
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

    char_blocks = "\n\n".join(_character_block(c, user) for c in chars)
    user_persona = (getattr(user, "persona_description", "") or "").strip()
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
    messages = [{"role": "system", "content": sys_content}]

    # Recent conversation history (last 30 bubbles)
    for m in data["messages"][-30:]:
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
            parts.append(f"[Sent photo: {m['photo'].get('prompt') or m['photo'].get('caption') or 'image'}]")
        if m.get("file"):
            parts.append(f"[Sent file {m['file'].get('name', 'file.txt')}: {(m['file'].get('content') or '')[:300]}]")
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
            st_txt = m.group(2).strip()[:280]
            if st_txt:
                profile_updates.append({"char": current_char, "kind": "status", "emoji": st_emo, "text": st_txt})
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
        v_match = RE_VOICE.search(chunk)
        if v_match:
            transcript = v_match.group(1).strip()
            voice_data = {
                "transcript": transcript,
                "audio_url": "",
                "duration": max(2, min(45, len(transcript.split()) // 2)),
            }
            chunk = RE_VOICE.sub("", chunk)

        # Extract photo
        photo_data = None
        p_match = RE_PHOTO.search(chunk)
        if p_match:
            kind_tag = p_match.group(1).upper()
            p_desc = p_match.group(2).strip()[:500]
            photo_data = {
                "kind": "tease" if kind_tag == "TEASE" else "casual",
                "prompt": p_desc,
                "caption": "",
                "url": "",
            }
            chunk = RE_PHOTO.sub("", chunk)

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
        img_bytes, cost = ai_client.generate_image(user, neutral_prompt)
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
        img_bytes, cost = ai_client.generate_image(user, ref_prompt, references=[neutral_item] if neutral_item else None)
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

    if not shot_type:
        shot_type = "pov_object" if (kind != "tease" and _looks_like_non_person_photo(desc_clean)) else "selfie"
    if not camera_angle:
        camera_angle = random.choice(POV_CAMERA_ANGLES if shot_type == "pov_object" else SELFIE_CAMERA_ANGLES)

    refs = load_character_references(character)
    setting_note = "modern-day setting" if prof["mode"] == "modern_au" else "in-world setting"

    if shot_type == "pov_object":
        prompt = (
            f"Create a candid smartphone photo taken by {character.name} in a {setting_note}.\n"
            f"CRITICAL STYLE LOCK: Render this food, object, or scenery photo in the EXACT SAME visual art style, "
            f"medium, brushwork/rendering, lighting aesthetic, and color temperature as the attached reference image(s) ({art_style}). "
            f"Do NOT switch to stock photorealism if the reference is illustrated/anime, and vice versa.\n"
            f"Camera angle & framing: {camera_angle}.\n"
            f"Photo subject & scene: {desc_clean[:600]}"
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

    img_bytes, cost = ai_client.generate_image(user, prompt, references=refs)
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

    if auto_check_in:
        rt = real_time_context(thread)
        extra_instruction = (
            f"{user.username} hasn't texted in {rt['elapsed_text']} (it is now {rt['clock']}) and is currently away/busy. "
            f"Send ONE short, natural check-in or spontaneous text (or a status update) that fits your character and "
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

    data["messages"].extend(parsed["bubbles"])
    if auto_check_in:
        data["unread"] = data.get("unread", 0) + len(parsed["bubbles"])
        data["last_auto_at"] = time.time()
    save_thread_data(thread, data)

    slop_warnings = []
    for b in parsed["bubbles"]:
        slop_warnings.extend(check_texting_slop(b.get("text") or ""))

    return {
        "bubbles": parsed["bubbles"],
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
    msgs = data["messages"]
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
        "member_slugs": [c.slug for c in chars],
        "member_names": [c.name for c in chars],
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
            **prof,
        })
        stickers.extend(character_stickers(c))
    u_prof = user_profile(user)
    stickers.extend(u_prof.get("custom_stickers") or [])
    return {
        **serialize_thread_summary(thread),
        "messages": data["messages"],
        "bg": data["bg"],
        "custom_bg_url": data["custom_bg_url"],
        "pinned_id": data["pinned_id"],
        "events": data["events"],
        "scenario_override": data["scenario_override"],
        "share_memory": data["share_memory"],
        "real_time": rt,
        "members": members,
        "stickers": stickers,
        "active_model": active_model_texting_rules(user),
    }
