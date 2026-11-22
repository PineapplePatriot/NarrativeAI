"""
Visual Novel Meet-Up Scene Mode & CG Gallery for the Digital Screen Hub.

When characters in TeleChat are about to meet in person (or when triggered manually),
the Digital Screen transitions into a Visual Novel environment:
- Central character expression sprite stage + location backdrop + background music chosen by the model
  from `media_library.built_in("music")` and the character's theme track.
- Splits narration/action and character dialogue into step-by-step Visual Novel beats, matching an
  expression mood (`emotion`) to every line and deciding when to hand input to the user (`handoff`).
- Dynamically generates new expression sprites when a beat calls for a mood the character doesn't have yet,
  and stores them permanently on the character (`Character.photo_<mood>` or `sprites.save`).
- Saves a completed episode and its full transcript independently of optional illustration generation,
  writes its summary back to the originating TeleChat thread, and lets the user return to the phone.
- Carries an explicit continuity record and participant references into image requests; outfit-specific
  expression assets are kept with the episode rather than replacing the character's regular sprites.
"""

import json
import copy
import hashlib
import logging
import re
import time
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone

from mainapp import ai_client, media_library, messenger, sprites, thinking, vn_support, vn_story
from mainapp.models import ChatSettings, MessengerThread

log = logging.getLogger(__name__)

MEETUP_CUE_RE = re.compile(
    r"\b(meet\s+up|meet\s+me|on\s+my\s+way|coming\s+over|come\s+over|at\s+the\s+door|outside\s+your|"
    r"see\s+you\s+in|see\s+you\s+at|waiting\s+for\s+you|at\s+the\s+cafe|at\s+the\s+bar|at\s+the\s+lab|"
    r"let's\s+hang|hang\s+out|grab\s+coffee|grab\s+a\s+drink| grab\s+dinner|pick\s+you\s+up|i'm\s+here|"
    r"knocking|downstairs|lobby)\b",
    re.I,
)


def _get_settings_obj(user):
    settings_obj, _ = ChatSettings.objects.get_or_create(author=user)
    if not isinstance(settings_obj.appearance, dict):
        settings_obj.appearance = {}
    return settings_obj


def get_vn_state(user):
    """Return `{active_scene: dict|None, gallery: [dict, ...]}` from the user's `ChatSettings.appearance['vn_scenes']`."""
    settings_obj = _get_settings_obj(user)
    raw = (settings_obj.appearance or {}).get("vn_scenes")
    if not isinstance(raw, dict):
        raw = {}
    active = raw.get("active_scene") if isinstance(raw.get("active_scene"), dict) else None
    gallery = [g for g in (raw.get("gallery") or []) if isinstance(g, dict)]
    return {
        "active_scene": active,
        "gallery": gallery,
        "drafts": raw.get("drafts") or [],
        "music_catalog": available_music_tracks(),
        "bg_catalog": available_backgrounds(),
    }


@transaction.atomic
def save_vn_state(user, updates, expected=None):
    settings_obj = _get_settings_obj(user)
    settings_obj = ChatSettings.objects.select_for_update().get(pk=settings_obj.pk)
    app = dict(settings_obj.appearance or {})
    cur = dict(app.get("vn_scenes") or {})
    active = cur.get("active_scene") or {}
    if expected is not None and (active.get("id", ""), active.get("revision", 0)) != expected:
        raise ai_client.AIError("This episode changed in another request. Reload it before continuing.")
    if isinstance(updates.get("active_scene"), dict):
        updates["active_scene"]["revision"] = active.get("revision", 0) + 1
    cur.update(updates)
    app["vn_scenes"] = cur
    settings_obj.appearance = app
    settings_obj.save(update_fields=["appearance"])
    return cur


def available_music_tracks(characters=None):
    """Return all available music tracks from `media_library.built_in('music')` plus any character theme tracks."""
    tracks = []
    seen = set()
    for c in (characters or []):
        t_music = (getattr(c, "theme", None) or {}).get("music")
        if isinstance(t_music, dict) and t_music.get("url") and t_music["url"] not in seen:
            tracks.append({
                "id": f"char_music_{c.slug}",
                "name": t_music.get("name") or f"{c.name}'s Theme",
                "url": t_music["url"],
            })
            seen.add(t_music["url"])
    for idx, t in enumerate(media_library.built_in("music")):
        if t["url"] not in seen:
            tracks.append({
                "id": f"builtin_music_{idx}",
                "name": t["name"],
                "url": t["url"],
            })
            seen.add(t["url"])
    return tracks


def available_backgrounds(characters=None):
    """Return all available scene backgrounds from `media_library.built_in('backgrounds')` plus character theme BGs."""
    bgs = []
    seen = set()
    for c in (characters or []):
        t_bg = (getattr(c, "theme", None) or {}).get("bg")
        if t_bg and isinstance(t_bg, str) and t_bg not in seen:
            bgs.append({
                "id": f"char_bg_{c.slug}",
                "name": f"{c.name}'s Backdrop",
                "url": t_bg,
            })
            seen.add(t_bg)
    for idx, b in enumerate(media_library.built_in("backgrounds")):
        if b["url"] not in seen:
            bgs.append({
                "id": f"builtin_bg_{idx}",
                "name": b["name"],
                "url": b["url"],
            })
            seen.add(b["url"])
    return bgs


def detect_meetup_cue(thread):
    """
    Inspect the last 4 messages in `thread` to check if the characters and user are about to meet up in person.
    Returns `{ready: bool, reason: str}` so TeleChat can surface a '🎬 Start Meet-Up Scene' prompt.
    """
    if not thread:
        return {"ready": False, "reason": ""}
    td = messenger.thread_data(thread)
    recent = [m for m in (td.get("messages") or [])[-4:] if m.get("role") in ("user", "assistant")]
    for m in reversed(recent):
        txt = str(m.get("text") or "")
        match = MEETUP_CUE_RE.search(txt)
        if match:
            return {
                "ready": True,
                "reason": f"Meet-up cue detected in chat (\"{match.group(0)}\")",
                "trigger_text": txt[:140],
            }
    return {"ready": False, "reason": ""}


def all_character_sprites(character):
    """Return `{emotion_lower: url}` of every sprite currently stored for `character`."""
    out = {}
    for emo in sprites.BUILT_IN:
        field = getattr(character, f"photo_{emo}", None)
        if field and getattr(field, "name", ""):
            try:
                out[emo] = field.url
            except ValueError:
                pass
    for emo, url in sprites.extras(character).items():
        out[emo.lower()] = url
    return out


def resolve_or_generate_sprite(user, character, emotion, auto_generate=False, outfit="", scene_assets=None):
    """
    Look up the character's sprite URL for `emotion`.
    - If `character` already has a sprite for `emotion`, return `{url, emotion, is_new: False, needs_gen: False}`.
    - If missing and `auto_generate=True`, dynamically generate a waist-up Visual Novel character sprite for
      `emotion` using `messenger.make_picture` (with 1 neutral + up to 4 extra references and art style lock)
      and store it permanently on `character` (`photo_<emotion>` or `sprites.save`).
    - If missing and `auto_generate=False`, fall back to their neutral/avatar image and flag `needs_gen: True`
      so the user can generate and save it with one click on the VN stage.
    """
    emo_clean = sprites.clean_name(emotion) or "neutral"
    existing = all_character_sprites(character)
    scoped = scene_assets is not None and (bool(outfit) or character.author_id != user.pk)
    asset_key = hashlib.sha256(f"{character.slug}|{emo_clean}|{outfit}".encode()).hexdigest()[:24]
    if scoped and asset_key in scene_assets:
        return {**scene_assets[asset_key], "is_new": False, "needs_gen": False}
    if emo_clean in existing and not scoped:
        return {
            "url": existing[emo_clean],
            "emotion": emo_clean,
            "is_new": False,
            "needs_gen": False,
        }

    prof = messenger.char_profile(character)
    fallback_url = existing.get("neutral") or prof.get("neutral_url") or prof.get("avatar_url") or ""

    if not auto_generate:
        return {
            "url": fallback_url,
            "emotion": emo_clean,
            "is_new": False,
            "needs_gen": True,
        }

    # Dynamically generate the missing expression sprite and store it permanently!
    refs = messenger.load_character_references(character)
    appearance = prof.get("appearance_notes") or (character.description or "")[:650]
    art_style = prof.get("art_style_notes") or "exact same visual art style, linework, shading, and color palette as the attached reference portrait(s)"
    setting_note = "modern-day outfit" if prof.get("mode") == "modern_au" else "signature outfit"

    prompt = (
        f"Create a Visual Novel character expression sprite of {character.name} ({setting_note}) showing a clear '{emo_clean}' expression and body language.\n"
        f"IDENTITY & STYLE: Preserve face, hair, eyes, proportions and visual art style ({art_style}) from the references.\n"
        f"Outfit for this scene: {outfit or 'keep the reference outfit design'}. Outfit directions override reference clothing, not identity.\n"
        f"Composition: clean waist-up centered Visual Novel character sprite portrait facing the viewer, expressive '{emo_clean}' emotion, clean simple subtle backdrop.\n"
        f"Character appearance: {appearance[:550]}"
    )
    img_bytes, cost = messenger.make_picture(user, prompt, references=refs)

    if scoped:
        path = default_storage.save(f"messenger/vn_sprites/{user.pk}/{asset_key}-{uuid.uuid4().hex[:8]}.png", ContentFile(img_bytes))
        new_url = default_storage.url(path)
        scene_assets[asset_key] = {"url": new_url, "emotion": emo_clean, "cost": cost}
    elif emo_clean in sprites.BUILT_IN:
        field_name = f"photo_{emo_clean}"
        rel_path = f"photos/vn/{character.slug}-{emo_clean}-{uuid.uuid4().hex[:6]}.png"
        saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
        getattr(character, field_name).name = saved_path
        character.save(update_fields=[field_name])
        new_url = default_storage.url(saved_path)
    else:
        try:
            new_url = sprites.save(character, emo_clean, img_bytes, ext="png")
        except ValueError:
            rel_path = f"photos/vn/{character.slug}-{emo_clean.replace(' ', '-')}-{uuid.uuid4().hex[:6]}.png"
            saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
            new_url = default_storage.url(saved_path)

    return {
        "url": new_url,
        "emotion": emo_clean,
        "is_new": True,
        "needs_gen": False,
        "cost": cost,
    }


VN_SCENE_PROMPT = """You are directing an interactive **Visual Novel Meet-Up Scene** launched from {user}'s TeleChat messenger.
The texting phase has transitioned into an in-person scene!

Current Real-World Clock: {clock}
{model_rules}

VISUAL NOVEL ENGINE RULES:
1. WRITE COMPLETE NARRATIVE BLOCKS; DISPLAY SPLITTING IS THE ENGINE'S JOB:
   - Let the user's requested length and style guide the prose. Descriptive narration, asides and substantial dialogue are welcome when they fit.
   - Never shorten or stretch a passage to reach a line count. There is no required number of blocks or sentences.
   - Keep each speaker's dialogue separate from narration; a block may contain multiple paragraphs.
   - Preserve each character's current intention, knowledge, voice and relationship. Do not add hostility, attraction or a confession to manufacture drama.
   - Follow the explicit interaction and authorship mode below; it defines who the model may write for.
   - You are in person now. Characters can perceive what is present, but cannot know private thoughts or events they did not witness.
   - Vary speech according to character and circumstance. Do not recycle the previous turn's sentence shape, accusation list or rhetorical exchange merely with synonyms.
   - Continue until the situation offers a meaningful opening for user input. Scene changes require narrative cause; preserve outfits, objects, injuries and positions until an event changes them.
   - Top-level background, music and location describe the opening, not the end of the passage.
   - For EACH block, include `stage` containing changes that take effect at that block: background/music IDs, location, and a continuity patch (outfits, positions, time, summary, open_threads). Do not apply later changes to earlier blocks. Copy unchanged outfit descriptions verbatim.
   - Update `continuity` cumulatively: retain earlier facts and unresolved matters, and record actual changes. Time follows the story clock, not the wall clock.
   - Each item in `beats` must be either narration or one character's spoken dialogue.
   - Format examples below describe speaker metadata only; they are not length requirements.
   - Just like a real visual novel, each item in `"beats"` must be EITHER:
     * A **Narration / Action block** (`"speaker_slug": "narrator"`, `"speaker": "Narrator"`, `"emotion": "neutral"`, `"text": "Complete narration or action, without dialogue quote marks"`), OR
     * A **Character Dialogue block** (`"speaker_slug": "<character slug>"`, `"speaker": "<character name>"`, `"emotion": "<specific expression mood>"`, `"text": "Their complete spoken dialogue without narration tags"`).
   - Write as much or as little as the scene and user directions call for.
2. DYNAMIC EXPRESSION SPRITES:
   - On every block with character speech or a silent reaction, set `"emotion"` to the exact mood that matches their face right now.
   - You can pick from their existing moods ({existing_moods}) OR invent a specific new mood (1-2 lowercase words like `"flustered"`, `"smug"`, `"tired"`, `"blushing"`, `"laughing"`, `"annoyed"`, `"lovestruck"`, `"drenched"`, `"scheming"`) — the engine can dynamically generate and store new expression sprites!
3. MUSIC & BACKDROP SELECTION:
   - Choose `"music"` from the available music tracks list below that best matches the current emotional tone of the scene.
   - Choose `"background"` from the available backgrounds list below (or keep the current one).
4. TURN HANDOFF (CHOOSE WHEN TO LET {user} TYPE):
   - Set `"handoff"` to:
     * `"user_turn"` — Pause at a natural moment so {user} can type a short action or dialogue reply (and provide 2-3 short `"choices"` {user} can click or adapt).
     * `"auto_continue"` — The character is in the middle of an unfolding action/moment; let {user} click "Continue ▶" (or interrupt if they want).
     * `"climax_ready"` — The scene has reached a memorable peak or parting moment and is ready to conclude with a full Finale CG illustration!

AVAILABLE MUSIC TRACKS:
{music_list}

AVAILABLE BACKGROUNDS:
{bg_list}

USER PROFILE:
- Name: {user} — {user_persona}

PARTICIPATING CHARACTER(S):
{char_roster}

RECENT TELECHAT MESSAGES LEADING INTO THIS MEET-UP:
{telechat_context}

SCENE STATE SO FAR:
{scene_history}

LATEST INPUT / DIRECTION FOR THIS STEP:
{step_input}

Return ONLY a valid JSON object matching this exact structure (no markdown fences):
{{
  "title": "Short evocative title for this meet-up scene (e.g. 'Midnight at the Sumeru Lab')",
  "location": "Specific location & time label (e.g. 'Zurich Biotech Lab · 01:40 AM')",
  "background": "Exact name of chosen background from AVAILABLE BACKGROUNDS",
  "music": "Exact name of chosen music track from AVAILABLE MUSIC TRACKS",
  "handoff": "user_turn",
  "handoff_prompt": "Short 4-10 word cue for {user}, e.g. 'How do you answer Il Dottore?' or 'Scene climax reached — capture Finale CG!'",
  "choices": [
    "Short action or dialogue option 1 (under 14 words)",
    "Short action or dialogue option 2 (under 14 words)"
  ],
  "continuity": {{
    "summary": "Cumulative events and relationship changes; retain earlier consequential facts",
    "location": "Current setting, lighting, weather and relevant objects",
    "time": "Current story date and time; advance only as the scene warrants",
    "outfits": {{"<character slug>": "Current clothes and changes from their reference"}},
    "positions": {{"<character slug>": "Current position and action"}},
    "open_threads": ["Unresolved plans, promises, questions or injuries"]
  }},
  "beats": [
    {{
      "speaker_slug": "narrator",
      "speaker": "Narrator",
      "character_slug": "<slug of the character currently visible center-stage>",
      "emotion": "neutral",
      "stage": {{}},
      "text": "The complete narration block OR spoken dialogue"
    }}
  ]
}}"""


FINALE_CG_PROMPT = """You are creating the **Finale Event CG** and memory summary to conclude a Visual Novel Meet-Up Scene between {user} and {char_names}.

Scene Title: {title}
Location: {location}
Character Appearance & Art Style:
{char_visuals}

Scene Transcript:
{transcript}

User's optional Finale CG hint: {cg_hint}

Distill the most memorable, cinematic climax or closing moment of this scene into:
1. `"visual_prompt"`: A rich 2-3 sentence Visual Novel Event CG illustration prompt showing {char_names} in this exact setting, lighting, pose, expression, and atmosphere.
2. `"camera_angle"`: Cinematic visual-novel CG framing (e.g. dramatic close-up, atmospheric two-shot POV, golden-hour window framing, rain-lit neon reflection).
3. `"finale_quote"`: The defining quote or 1-sentence caption written on the Finale CG card in the gallery.
4. `"chat_summary"`: A 1-2 sentence summary of what happened during this in-person meet-up so the characters remember it when they go back to texting on TeleChat.

Return ONLY a valid JSON object:
{{
  "visual_prompt": "...",
  "camera_angle": "...",
  "finale_quote": "...",
  "chat_summary": "..."
}}"""


def _call_vn_json(user, prompt, scene=None, generation="normal"):
    _, model = ai_client.resolve(user, "chat")
    thinks = thinking.needs_leash(model, "default")
    pack = vn_story.prepare(user, scene, prompt, generation) if scene is not None else None
    params = dict(pack["params"]) if pack else {}
    params.setdefault("max_tokens", 4500 + (thinking.LEASH_ROOM if thinks else 0))
    params.setdefault("temperature", 0.82)
    raw = ai_client.complete(user, "chat", pack["messages"] if pack else [{"role": "user", "content": prompt}], **params)
    parsed = messenger._read_json(raw)
    if not isinstance(parsed, dict) or not parsed:
        raise ai_client.AIError("Could not parse Visual Novel scene blocks from model. Try again.")
    return parsed


def _build_char_roster(chars, user=None, context=None):
    lines = []
    all_moods = set(sprites.BUILT_IN + sprites.SUGGESTED)
    for c in chars:
        p = messenger.char_profile(c)
        c_sprites = all_character_sprites(c)
        all_moods.update(c_sprites.keys())
        context = context or {}
        persona = messenger._character_block(c, user or c.author, u_name=context.get("user_name"),
                                             share=context.get("share_memory") if c.author_id == (user or c.author).pk else False)
        app = p.get("appearance_notes") or (c.description or "")
        lines.append(
            f"- {p['display_name']} (slug: `{c.slug}`, mode: {p['mode']})\n"
            f"  Existing sprite moods ready: {', '.join(sorted(c_sprites.keys())) or 'neutral'}\n"
            f"  Appearance: {app}\n"
            f"  Persona & voice: {persona}"
        )
    return "\n".join(lines), ", ".join(sorted(all_moods))


def _match_track(tracks, name):
    if not tracks:
        return {"id": "none", "name": "Silence", "url": ""}
    key = str(name or "").strip().lower()
    for t in tracks:
        if t.get("id", "").lower() == key or t["name"].lower() == key or (key and key in t["name"].lower()):
            return t
    return {"id": "none", "name": "Silence", "url": ""}


def _match_bg(bgs, name):
    if not bgs:
        return {"id": "none", "name": "Midnight Stage", "url": ""}
    key = str(name or "").strip().lower()
    for b in bgs:
        if b.get("id", "").lower() == key or b["name"].lower() == key or (key and key in b["name"].lower()):
            return b
    return {"id": "none", "name": "No backdrop", "url": ""}


def _enrich_beats(user, chars, raw_beats, auto_generate_sprites=False, continuity=None, scene_assets=None,
                  initial_stage=None, authoring_mode="roleplay", user_participant=None):
    if not isinstance(raw_beats, list):
        raise ai_client.AIError("The model returned invalid scene blocks. Try again.")
    char_by_slug = {c.slug: c for c in chars}
    current = copy.deepcopy(initial_stage or {"continuity": continuity or {}})
    user_participant = user_participant or vn_story.user_participant(user, vn_support.scene_context(user))
    tracks, bgs = available_music_tracks(chars), available_backgrounds(chars)
    boxes = []
    for rb in raw_beats:
        if not isinstance(rb, dict) or not str(rb.get("text") or "").strip():
            continue
        txt = str(rb["text"]).strip()
        before = copy.deepcopy(current)
        current = vn_story.advance_stage(current, rb.get("stage"), tracks, bgs)
        sp_raw = str(rb.get("speaker_slug") or rb.get("speaker") or "").strip().strip("`").strip()
        sp_low = sp_raw.casefold()
        narrator = rb.get("kind") == "narration" or sp_low in ("narrator", "narration", "system", "")
        user_speaks = sp_low == "user" and not narrator
        speaker_char = char_by_slug.get(sp_raw) or next((c for c in chars if sp_low in (
            c.slug.casefold(), c.name.casefold(), messenger.char_profile(c)["display_name"].casefold())), None)
        if user_speaks and authoring_mode != "director":
            raise ai_client.AIError("The model wrote for your character. Your previous scene is saved; try again.")
        if not narrator and not user_speaks and speaker_char is None:
            raise ai_client.AIError("The model wrote dialogue for someone outside the selected cast. Try again with the same setup.")
        stage_slug = str(rb.get("character_slug") or ("user" if user_speaks else speaker_char.slug if speaker_char else chars[0].slug))
        if stage_slug == "user" and authoring_mode != "director":
            stage_slug = speaker_char.slug if speaker_char else chars[0].slug
        emotion = sprites.clean_name(rb.get("emotion") or "neutral") or "neutral"
        if stage_slug == "user":
            stage_name = user_participant["name"]
            sp_info = {"emotion": emotion, "url": user_participant["sprites"].get(emotion) or user_participant["avatar_url"], "needs_gen": False}
        else:
            stage_char = char_by_slug.get(stage_slug) or speaker_char or chars[0]
            stage_slug = stage_char.slug
            stage_name = messenger.char_profile(stage_char)["display_name"]
            outfits = (current.get("continuity") or {}).get("outfits") or {}
            outfit = str(outfits.get(stage_slug) or "") if isinstance(outfits, dict) else ""
            sp_info = resolve_or_generate_sprite(user, stage_char, emotion, auto_generate=auto_generate_sprites and not narrator,
                                                 outfit=outfit, scene_assets=scene_assets)
        block_id = "vnb_" + uuid.uuid4().hex[:8]
        speaker = "narrator" if narrator else "user" if user_speaks else speaker_char.slug
        speaker_name = "Narrator" if narrator else user_participant["name"] if user_speaks else messenger.char_profile(speaker_char)["display_name"]
        for i, part in enumerate(vn_support.split_display_text(txt)):
            boxes.append({"id": "vnb_" + uuid.uuid4().hex[:8], "block_id": block_id,
                          "kind": "narration" if narrator else "dialogue", "generated": True,
                          "speaker": speaker, "speaker_slug": speaker, "speaker_name": speaker_name,
                          "character_slug": stage_slug, "character_name": stage_name, "emotion": sp_info["emotion"],
                          "sprite_url": sp_info["url"], "is_new_sprite": sp_info.get("is_new", False),
                          "needs_sprite_gen": False if narrator else sp_info.get("needs_gen", False),
                          "text": part, "block_text": txt if i == 0 else "",
                          "original_text": (rb.get("original_text") or "") if i == 0 else "",
                          "stage": copy.deepcopy(current), "stage_before": before})
    return boxes


def start_scene(user, thread=None, characters=None, location_hint="", auto_generate_sprites=False,
                direction="", polish_enabled=False, interaction_mode="mixed", authoring_mode="roleplay", pulse_event=None, generate_background=False):
    """
    Launch a new Visual Novel Meet-Up Scene from a TeleChat `thread` (or selected `characters`).
    Selects music & backdrop, generates the opening narrative, resolves or generates character sprites,
    and saves `active_scene` into the user's VN state.
    """
    if get_vn_state(user).get("active_scene"):
        raise ai_client.AIError("An episode is already open. Resume or finish it before starting another.")
    chars = list(characters or (thread.characters.all() if thread else []))
    if not chars:
        raise ai_client.AIError("Pick at least one character for the scene.")

    context = vn_support.scene_context(user, thread)
    if pulse_event:
        # Freeze the plan at launch. Calendar edits cannot rewrite an episode already in progress.
        context["clock"] = pulse_event["when_label"]
        context["pulse_event"] = copy.deepcopy(pulse_event)
        location_hint = location_hint or pulse_event["location"]
        direction = (f"PULSE PLAN: {pulse_event['title']}\nScheduled time: {pulse_event['when_label']}\n"
                     f"Place: {pulse_event['location']}\nPurpose: {pulse_event['purpose']}\n"
                     "Stage this meeting at its scheduled time. Do not assume it already happened. "
                     "Only the scheduled participants are present; group membership alone does not put someone in the room. "
                     "This scene does not advance the phone's clock or mark the calendar plan completed.\n" + direction)
    u_name = context["user_name"]
    now_local = timezone.localtime(timezone.now())
    clock_str = context["clock"]

    tracks = available_music_tracks(chars)
    bgs = available_backgrounds(chars)
    roster_text, moods_list = _build_char_roster(chars, user, context)

    telechat_context = ("Earlier memory:\n" + context["memory"] + "\nThread scenario:\n" + context["scenario"]
                        + "\nConversation:\n" + context["conversation"])

    model_rules = ""  # Writing instructions come from the selected preset, without a second hidden baseline.

    seed = {"thread_id": thread.id if thread else None, "context": context, "direction": direction,
            "character_slugs": [c.slug for c in chars], "beats": [],
            "interaction_mode": interaction_mode if interaction_mode in vn_story.INTERACTIONS else "mixed",
            "authoring_mode": authoring_mode if authoring_mode in vn_story.AUTHORING else "roleplay",
            "user_participant": vn_story.user_participant(user, context),
            "phone_snapshot": copy.deepcopy(thread.data or {}) if thread else {}}
    if pulse_event:
        seed["pulse_event"] = copy.deepcopy(pulse_event)
    prompt = VN_SCENE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        model_rules=model_rules,
        existing_moods=moods_list,
        music_list="\n".join(f"- {t['name']} (id: {t['id']})" for t in tracks) or "- Default Theme",
        bg_list="\n".join(f"- {b['name']} (id: {b['id']})" for b in bgs) or "- Default Backdrop",
        user_persona=context["persona"],
        char_roster=roster_text,
        telechat_context=telechat_context,
        scene_history="(Scene is just beginning — set the stage as they meet!)",
        step_input=(location_hint or "Begin the in-person scene right where the latest texts left off.")
                   + "\nUser's writing directions: " + direction,
    )

    parsed = _call_vn_json(user, prompt, seed)
    chosen_music = _match_track(tracks, parsed.get("music_id") or parsed.get("music"))
    chosen_bg = _match_bg(bgs, parsed.get("background_id") or parsed.get("background"))
    raw_blocks = parsed.get("blocks") or parsed.get("beats") or []
    raw_blocks, polish_error = vn_support.polish_blocks(user, raw_blocks, telechat_context, polish_enabled)
    continuity = {"time": context["clock"]}
    scene_assets = {}
    beats = _enrich_beats(user, chars, raw_blocks, auto_generate_sprites=auto_generate_sprites,
                        continuity=continuity, scene_assets=scene_assets,
                        initial_stage={"background": chosen_bg, "music": chosen_music, "location": parsed.get("location") or location_hint, "continuity": continuity},
                        authoring_mode=seed["authoring_mode"], user_participant=seed["user_participant"])
    if not beats:
        raise ai_client.AIError("The model returned no scene text. Try starting the episode again.")

    scene = {
        **seed,
        "id": "vns_" + uuid.uuid4().hex[:8],
        "thread_id": thread.id if thread else None,
        "context": context,
        "direction": direction,
        "polish_enabled": bool(polish_enabled),
        "polish_error": polish_error,
        "continuity": continuity,
        "sprite_cache": scene_assets,
        "character_slugs": [c.slug for c in chars],
        "character_names": [messenger.char_profile(c)["display_name"] for c in chars],
        "title": str(parsed.get("title") or f"Meet-Up with {chars[0].name}").strip()[:120],
        "location": str(parsed.get("location") or location_hint or now_local.strftime("%H:%M")).strip()[:120],
        "background": chosen_bg,
        "music": chosen_music,
        "handoff": parsed.get("handoff") if parsed.get("handoff") in ("user_turn", "auto_continue", "climax_ready") else "user_turn",
        "handoff_prompt": str(parsed.get("handoff_prompt") or "What do you do or say?").strip()[:140],
        "choices": [str(ch).strip()[:120] for ch in (parsed.get("choices") or []) if str(ch or "").strip()][:3],
        "beats": list(beats),
        "current_beats": list(beats),
        "history": list(beats),
        "auto_generate_sprites": bool(auto_generate_sprites),
        "started_at": now_local.strftime("%d %b %H:%M"),
        "ts": time.time(),
    }
    if generate_background:
        opening = beats[0]["stage"]
        location = opening.get("location") or scene["location"]
        try:
            image, cost = messenger.make_picture(user, (
                f"Create an immersive visual novel background of {location}. "
                f"Scene context: {beats[0]['text']}\n"
                f"Setting details: {json.dumps(opening.get('continuity') or {}, ensure_ascii=False)}\n"
                "Environment only, no people, no portraits, no lettering. Wide establishing shot."
            ))
            path = default_storage.save(
                f"messenger/vn_backgrounds/{user.pk}/{uuid.uuid4().hex}.png", ContentFile(image))
            generated_bg = {"id": "generated_" + scene["id"], "name": location,
                            "url": default_storage.url(path)}
            original_bg = opening.get("background")
            for beat in beats:
                for key in ("stage", "stage_before"):
                    if beat[key].get("background") == original_bg:
                        beat[key]["background"] = copy.deepcopy(generated_bg)
        except ai_client.AIError as exc:
            scene["background_error"] = "Episode ready, but the background could not be generated: " + str(exc)
    scene["initial_stage"] = copy.deepcopy(beats[0]["stage_before"])
    scene["current_stage"] = vn_story.finish_timeline(beats, parsed.get("continuity"))
    scene["continuity"] = scene["current_stage"]["continuity"]
    scene.update({k: scene["current_stage"].get(k) for k in ("background", "music", "location")})
    if scene["interaction_mode"] == "write": scene["choices"] = []
    scene["choice_cache"] = list(scene["choices"])
    save_vn_state(user, {"active_scene": scene}, expected=("", 0))
    return scene


def step_scene(user, user_input="", auto_generate_sprites=None, base_scene=None, generation="normal", turn_direction="", save_updates=None):
    """
    Advance the active Visual Novel scene by one turn (either with `user_input` action/dialogue or
    continuing automatically when `user_input` is empty).
    """
    state = get_vn_state(user)
    scene = copy.deepcopy(base_scene or state.get("active_scene"))
    if not scene:
        raise ai_client.AIError("No active Visual Novel scene. Start a scene first.")
    expected = (scene["id"], scene.get("revision", 0))

    chars = vn_support.scene_characters(user, scene.get("character_slugs") or [])
    if not chars:
        raise ai_client.AIError("Scene characters not found.")

    if auto_generate_sprites is None:
        auto_generate_sprites = bool(scene.get("auto_generate_sprites", False))
    else:
        scene["auto_generate_sprites"] = bool(auto_generate_sprites)

    context = scene.get("context") or vn_support.scene_context(user, vn_support.linked_thread(user, scene))
    scene["context"] = context
    u_name = context["user_name"]
    clock_str = (scene.get("continuity") or {}).get("time") or context["clock"]

    history = list(scene.get("beats") or scene.get("history") or [])
    if user_input and user_input.strip():
        directing = scene.get("authoring_mode") == "director"
        c0 = chars[0]
        last_beat = history[-1] if history else {}
        user_beat = {
            "id": "vnb_" + uuid.uuid4().hex[:8],
            "kind": "direction" if directing else "dialogue",
            "speaker": "director" if directing else "user",
            "speaker_slug": "director" if directing else "user",
            "speaker_name": "Director" if directing else u_name,
            "character_slug": last_beat.get("character_slug") or c0.slug,
            "character_name": last_beat.get("character_name") or c0.name,
            "emotion": last_beat.get("emotion") or "neutral",
            "sprite_url": last_beat.get("sprite_url") or "",
            "is_new_sprite": False,
            "needs_sprite_gen": False,
            "text": user_input.strip(),
            "generated": False, "stage": vn_story.stage_of(scene), "stage_before": vn_story.stage_of(scene),
        }
        history.append(user_beat)

    hist_lines = []
    for b in history[-40:]:
        emo_tag = f" [{b.get('emotion')}]" if b.get("speaker_slug") not in ("narrator", "user") else ""
        hist_lines.append(f"- {b.get('speaker_name') or b.get('speaker')}{emo_tag}: {b.get('text')}")

    tracks = available_music_tracks(chars)
    bgs = available_backgrounds(chars)
    roster_text, moods_list = _build_char_roster(chars, user, context)
    model_rules = ""  # Writing instructions come from the selected preset, without a second hidden baseline.

    step_dir = (
        (f"Director's instruction (not spoken dialogue): {user_input.strip()}. Follow this direction in the scene."
         if scene.get("authoring_mode") == "director"
         else f"{u_name} just did/said: \"{user_input.strip()}\". Respond until the next natural opportunity for input.")
        if (user_input and user_input.strip())
        else "Continue unfolding the scene until the next natural opportunity for input."
    )

    prompt = VN_SCENE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        model_rules=model_rules,
        existing_moods=moods_list,
        music_list="\n".join(f"- {t['name']} (id: {t['id']})" for t in tracks) or "- Default Theme",
        bg_list="\n".join(f"- {b['name']} (id: {b['id']})" for b in bgs) or "- Default Backdrop",
        user_persona=context["persona"],
        char_roster=roster_text,
        telechat_context=json.dumps(context, ensure_ascii=False),
        scene_history=("Continuity record (carry earlier facts forward):\n"
                       + json.dumps(scene.get("continuity") or {}, ensure_ascii=False)
                       + "\nRecent transcript:\n" + "\n".join(hist_lines)),
        step_input=step_dir + "\nUser's writing directions: " + scene.get("direction", ""),
    )

    scene["beats"] = history
    parsed = _call_vn_json(user, prompt + "\n" + turn_direction, scene, generation)
    raw_blocks = parsed.get("blocks") or parsed.get("beats") or []
    raw_blocks, scene["polish_error"] = vn_support.polish_blocks(
        user, raw_blocks, prompt, scene.get("polish_enabled", False))
    continuity = vn_support.continuity_update(scene.get("continuity"), parsed.get("continuity"))
    new_beats = _enrich_beats(user, chars, raw_blocks, auto_generate_sprites=auto_generate_sprites,
                            continuity=continuity, scene_assets=scene.setdefault("sprite_cache", {}),
                            initial_stage=vn_story.stage_of(scene), authoring_mode=scene.get("authoring_mode", "roleplay"),
                            user_participant=scene.get("user_participant"))
    if not new_beats:
        raise ai_client.AIError("The model returned no scene text. Your previous turn is still saved; try again.")
    history.extend(new_beats)
    scene["current_beats"] = new_beats
    scene["beats"] = history
    scene["history"] = history
    scene["current_stage"] = vn_story.finish_timeline(new_beats, parsed.get("continuity"))
    scene["continuity"] = scene["current_stage"]["continuity"]
    scene.update({k: scene["current_stage"].get(k) for k in ("background", "music", "location")})
    scene["handoff"] = parsed.get("handoff") if parsed.get("handoff") in ("user_turn", "auto_continue", "climax_ready") else "user_turn"
    scene["handoff_prompt"] = str(parsed.get("handoff_prompt") or "What do you do or say?").strip()[:140]
    scene["choices"] = [str(ch).strip()[:120] for ch in (parsed.get("choices") or []) if str(ch or "").strip()][:3]

    if scene.get("interaction_mode") == "write": scene["choices"] = []
    scene["choice_cache"] = list(scene["choices"])
    save_vn_state(user, {**(save_updates or {}), "active_scene": scene}, expected=expected)
    return scene, new_beats


def suggest_choices(user):
    """Offer options at the current endpoint without advancing the story or generating images."""
    from mainapp import vn_history
    _, scene = vn_history.current(user)
    if scene.get("interaction_mode") == "write":
        raise ai_client.AIError("Switch to choices or mixed mode before requesting options.")
    expected = (scene["id"], scene.get("revision", 0))
    prompt = ("Suggest up to three distinct, scene-specific actions or lines of dialogue the user could choose "
              "at the current moment. Preserve character, knowledge and authorship mode. Do not advance the scene, "
              "invent an event, change continuity or write a continuation. Return ONLY JSON {\"choices\": [\"option\"]}.")
    result = _call_vn_json(user, prompt, scene)
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices or any(not isinstance(c, str) or not c.strip() for c in choices):
        raise ai_client.AIError("The model returned no usable options. The episode is unchanged.")
    scene["choices"] = [c.strip()[:240] for c in choices[:3]]
    scene["choice_cache"] = list(scene["choices"])
    if scene.get("last_request"):
        scene["last_request"]["operation"] = "suggest_choices"
    save_vn_state(user, {"active_scene": scene}, expected=expected)
    return scene


def generate_beat_sprite(user, beat_id="", char_slug="", emotion=""):
    """
    Dynamically generate and permanently store an expression sprite for `(char_slug, emotion)` on demand,
    updating any matching beats in the active scene.
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    candidates = vn_support.scene_characters(user, scene.get("character_slugs") or []) if scene else []
    target_char = next((c for c in candidates if c.slug == char_slug), None)
    if not target_char and scene:
        for b in (scene.get("beats") or scene.get("current_beats") or []):
            if b.get("id") == beat_id:
                target_char = next((c for c in candidates if c.slug == b.get("character_slug")), None)
                emotion = emotion or b.get("emotion")
                break
    if not target_char:
        raise ai_client.AIError("Character not found for sprite generation.")

    expected = (scene["id"], scene.get("revision", 0))
    target_beat = next((b for b in scene.get("beats", []) if b.get("id") == beat_id), {})
    target_state = target_beat.get("stage") or vn_story.stage_of(scene)
    outfits = (target_state.get("continuity") or {}).get("outfits") or {}
    outfit = str(outfits.get(target_char.slug) or "") if isinstance(outfits, dict) else ""
    sp_info = resolve_or_generate_sprite(user, target_char, emotion or "neutral", auto_generate=True,
                                       outfit=outfit, scene_assets=scene.setdefault("sprite_cache", {}))

    if scene:
        for collection in (scene.get("beats") or [], scene.get("current_beats") or [], scene.get("history") or []):
            for b in collection:
                selected = bool(target_beat) and (b.get("block_id") or b.get("id")) == (target_beat.get("block_id") or target_beat.get("id"))
                if b.get("character_slug") == target_char.slug and (selected or b.get("emotion") == sp_info["emotion"]):
                    other_outfits = ((b.get("stage") or {}).get("continuity") or {}).get("outfits") or {}
                    other_outfit = str(other_outfits.get(target_char.slug) or "") if isinstance(other_outfits, dict) else ""
                    if other_outfit != outfit:
                        continue
                    b["sprite_url"] = sp_info["url"]
                    b["emotion"] = sp_info["emotion"]
                    b["is_new_sprite"] = True
                    b["needs_sprite_gen"] = False
        save_vn_state(user, {"active_scene": scene}, expected=expected)

    return scene, sp_info["url"], sp_info["emotion"], float(sp_info.get("cost") or 0.0)


def finish_scene_with_cg(user, cg_hint="", capture_image=True):
    """
    End the active Visual Novel scene by generating a full widescreen Finale Event CG image
    (using the character's 1 neutral + up to 4 extra references and art style lock),
    saving the completed scene + CG into the Gallery, and logging a memory notice in the linked TeleChat thread.
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    if not scene:
        raise ai_client.AIError("No active Visual Novel scene to finish.")
    expected = (scene["id"], scene.get("revision", 0))

    chars = vn_support.scene_characters(user, scene.get("character_slugs") or [])
    if not chars:
        raise ai_client.AIError("Scene character not found.")
    lead_char = chars[0]
    lead_prof = messenger.char_profile(lead_char)

    from mainapp.cards import user_name
    u_name = (scene.get("context") or {}).get("user_name") or user_name(user)

    transcript_lines = []
    transcript_lines.append("Cumulative continuity: " + json.dumps(scene.get("continuity") or {}, ensure_ascii=False))
    for b in (scene.get("beats") or scene.get("history") or [])[-40:]:
        if b.get("kind") == "direction":
            continue
        transcript_lines.append(f"{b.get('speaker_name') or b.get('speaker')}: {b.get('text')}")

    char_visuals = []
    for c in chars:
        p = messenger.char_profile(c)
        char_visuals.append(
            f"- {p['display_name']}: {p.get('appearance_notes') or (c.description or '')[:400]} "
            f"(Art style: {p.get('art_style_notes') or 'match reference portrait style'})"
        )

    prompt = FINALE_CG_PROMPT.format(
        user=u_name,
        char_names=", ".join(scene.get("character_names") or [lead_char.name]),
        title=scene.get("title"),
        location=scene.get("location"),
        char_visuals="\n".join(char_visuals),
        transcript="\n".join(transcript_lines) or "(Short meet-up scene)",
        cg_hint=cg_hint or "Capture the emotional peak or parting moment of this scene.",
    )

    try:
        cg_meta = _call_vn_json(user, prompt)
    except Exception:
        cg_meta = {}

    visual_prompt = str(cg_meta.get("visual_prompt") or cg_hint or f"Cinematic Visual Novel Event CG of {lead_char.name} at {scene.get('location')}").strip()
    camera_angle = str(cg_meta.get("camera_angle") or "cinematic widescreen visual novel event CG composition, expressive lighting and depth").strip()
    finale_quote = str(
        cg_meta.get("finale_quote")
        or cg_meta.get("quote")
        or (scene.get("beats")[-1].get("text") if scene.get("beats") else scene.get("title"))
    ).strip()[:220]
    chat_summary = str(
        cg_meta.get("chat_summary")
        or cg_meta.get("summary")
        or (scene.get("continuity") or {}).get("summary")
        or f"Met up in person at {scene.get('location')} ({scene.get('title')})."
    ).strip()

    art_style = lead_prof.get("art_style_notes") or "exact same visual art style, brushwork, linework, shading, and color palette as the attached reference image(s)"
    # Give every participant a primary reference before filling the remaining slots.
    refs = []
    extra_refs = []
    ref_labels = []
    for c in chars:
        images = messenger.load_character_references(c)
        if images and len(refs) < 5:
            refs.append(images[0])
            ref_labels.append(f"Reference {len(refs)}: {messenger.char_profile(c)['display_name']}")
            extra_refs.extend(images[1:])
    player = scene.get("user_participant") or {}
    if player:
        char_visuals.append(f"- {player.get('name')}: {player.get('persona') or 'match their reference portrait'}")
        if player.get("avatar_url") and len(refs) < 5:
            reference = messenger._read_storage_image(player["avatar_url"])
            if reference:
                refs.append(reference)
                ref_labels.append(f"Reference {len(refs)}: {player['name']} (the user's character)")
    refs.extend(extra_refs[:max(0, 5 - len(refs))])

    full_cg_prompt = (
        f"Create a full-scene Visual Novel Event CG illustration featuring {', '.join(scene.get('character_names') or [lead_char.name])} at {scene.get('location')}.\n"
        f"CRITICAL IDENTITY & STYLE LOCK: Keep the EXACT same face, hair, eyes, proportions, and visual art style ({art_style}) as the attached reference image(s).\n"
        f"Camera angle & framing: {camera_angle}.\n"
        f"Reference identities: {'; '.join(ref_labels)}. Additional references support these same identities.\n"
        f"Participant appearances: {'; '.join(char_visuals)}\n"
        f"Established setting, clothing, positions and story time (override reference outfits where changed): {json.dumps(scene.get('continuity') or {}, ensure_ascii=False)}\n"
        f"Event CG scene: {visual_prompt}"
    )

    cg_url, cost, image_error = "", 0, ""
    if capture_image:
        try:
            img_bytes, cost = messenger.make_picture(user, full_cg_prompt, references=refs)
            rel_path = f"messenger/vn_cg/{lead_char.slug}-cg-{uuid.uuid4().hex[:8]}.png"
            saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
            cg_url = default_storage.url(saved_path)
        except ai_client.AIError as exc:
            image_error = str(exc)

    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
    finished_str = timezone.localtime(timezone.now()).strftime("%d %b %Y · %H:%M")
    all_beats = scene.get("beats") or scene.get("history") or []
    gallery_entry = {
        "id": scene["id"],
        "episode": copy.deepcopy(scene),
        "thread_id": scene.get("thread_id"),
        "title": scene.get("title"),
        "location": scene.get("location"),
        "character_slugs": scene.get("character_slugs"),
        "character_names": scene.get("character_names"),
        "cg_url": cg_url,
        "image_error": image_error,
        "continuity": scene.get("continuity") or {},
        "cg_prompt": visual_prompt,
        "quote": finale_quote,
        "finale_quote": finale_quote,
        "summary": chat_summary,
        "chat_summary": chat_summary,
        "music": scene.get("music"),
        "background": scene.get("background"),
        "beats": all_beats,
        "transcript": all_beats,
        "finished_at": finished_str,
        "completed_at": finished_str,
        "ts": time.time(),
        "cost": cost,
    }

    with transaction.atomic():
        gallery = [gallery_entry] + [g for g in state["gallery"] if g.get("id") != scene["id"]]
        save_vn_state(user, {"active_scene": None, "gallery": gallery}, expected=expected)

        # Write a scene completion notice & CG bubble into the linked TeleChat thread so phone chat remembers the meet-up!
        if scene.get("thread_id"):
            thread = MessengerThread.objects.select_for_update().filter(user=user, id=scene["thread_id"]).prefetch_related("characters").first()
            if thread:
                td = messenger.thread_data(thread)
                td["messages"].append({
                    "id": uuid.uuid4().hex[:10],
                    "role": "system",
                    "text": f"🎬 Meet-Up Scene Completed: \"{scene.get('title')}\" ({scene.get('location')}) — {chat_summary}",
                    "time": now_hm,
                    "ts": time.time(),
                })
                if cg_url:
                    td["messages"].append({
                        "id": uuid.uuid4().hex[:10],
                        "role": "assistant",
                        "sender_slug": lead_char.slug,
                        "sender_name": lead_prof["display_name"],
                        "text": f"🎬 *{finale_quote}*",
                        "photo": {
                            "kind": "casual",
                            "prompt": visual_prompt,
                            "caption": f"🎬 Scene Finale CG · {scene.get('title')}",
                            "url": cg_url,
                        },
                        "time": now_hm,
                        "ts": time.time(),
                        "reactions": {"❤️": [lead_prof["display_name"]]},
                    })
                messenger.save_thread_data(thread, td)

    return gallery_entry, float(cost or 0.0)
