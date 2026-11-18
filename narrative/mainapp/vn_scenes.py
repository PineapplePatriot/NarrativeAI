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
- Ends the scene by generating a full Visual Novel Finale CG image (anchored to the character's 1 neutral
  + up to 4 extra reference images and art style lock), saves the scene + CG to the Gallery, writes a
  memory summary back to the TeleChat thread, and lets the user return to the phone or start a new scene.
"""

import json
import logging
import re
import time
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.utils import timezone

from mainapp import ai_client, media_library, messenger, sprites, thinking
from mainapp.models import Character, ChatSettings, MessengerThread

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
        "gallery": gallery[:60],
        "music_catalog": available_music_tracks(),
        "bg_catalog": available_backgrounds(),
    }


def save_vn_state(user, updates):
    settings_obj = _get_settings_obj(user)
    app = dict(settings_obj.appearance or {})
    cur = dict(app.get("vn_scenes") or {})
    cur.update(updates)
    if "gallery" in cur and isinstance(cur["gallery"], list):
        cur["gallery"] = cur["gallery"][:60]
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


def resolve_or_generate_sprite(user, character, emotion, auto_generate=False):
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
    if emo_clean in existing:
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
        f"CRITICAL IDENTITY & STYLE LOCK: Keep the EXACT same face, hair, eyes, outfit design, and visual art style ({art_style}) as the attached reference image(s).\n"
        f"Composition: clean waist-up centered Visual Novel character sprite portrait facing the viewer, expressive '{emo_clean}' emotion, clean simple subtle backdrop.\n"
        f"Character appearance: {appearance[:550]}"
    )
    img_bytes, cost = messenger.make_picture(user, prompt, references=refs)

    if emo_clean in sprites.BUILT_IN:
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
1. SPLIT NARRATION & DIALOGUE ONTO SEPARATE BEATS:
   - Just like a real visual novel, each item in `"beats"` must be EITHER:
     * A concise **Narration / Action beat** (`"speaker_slug": "narrator"`, `"speaker": "Narrator"`, `"emotion": "neutral"`, `"text": "1-2 vivid sentences of physical action, atmosphere, or movement — no quote marks"`), OR
     * A **Character Dialogue beat** (`"speaker_slug": "<character slug>"`, `"speaker": "<character name>"`, `"emotion": "<specific expression mood>"`, `"text": "What they say out loud (1-2 sentences, pure spoken dialogue without narration tags)"`).
   - Generate 3 to 5 beats for this step of the scene.
2. DYNAMIC EXPRESSION SPRITES:
   - On every character beat (and whenever a character reacts silently in a beat), set `"emotion"` to the exact mood that matches their face right now.
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
  "handoff": "user_turn" | "auto_continue" | "climax_ready",
  "handoff_prompt": "Short 4-10 word cue for {user}, e.g. 'How do you answer Il Dottore?' or 'Scene climax reached — capture Finale CG!'",
  "choices": [
    "Short action or dialogue option 1 (under 14 words)",
    "Short action or dialogue option 2 (under 14 words)"
  ],
  "beats": [
    {{
      "speaker_slug": "narrator" | "<character slug>",
      "speaker": "Narrator" | "<character display name>",
      "character_slug": "<slug of the character currently visible center-stage>",
      "emotion": "neutral" | "happy" | "smug" | "flustered" | "scheming" | "<any mood>",
      "text": "The single narration beat OR single spoken dialogue line"
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


def _call_vn_json(user, prompt):
    _, model = ai_client.resolve(user, "chat")
    thinks = thinking.needs_leash(model, "default")
    raw = ai_client.complete(
        user,
        "chat",
        [{"role": "user", "content": prompt}],
        max_tokens=1800 + (thinking.LEASH_ROOM if thinks else 0),
        temperature=0.82,
    )
    parsed = messenger._read_json(raw)
    if not parsed:
        raise ai_client.AIError("Could not parse Visual Novel scene beats from model. Try again.")
    return parsed


def _build_char_roster(chars):
    lines = []
    all_moods = set(sprites.BUILT_IN + sprites.SUGGESTED)
    for c in chars:
        p = messenger.char_profile(c)
        c_sprites = all_character_sprites(c)
        all_moods.update(c_sprites.keys())
        persona = p.get("modern_persona") or c.personality or (c.description or "")[:400]
        app = p.get("appearance_notes") or (c.description or "")[:350]
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
    return tracks[0]


def _match_bg(bgs, name):
    if not bgs:
        return {"id": "none", "name": "Midnight Stage", "url": ""}
    key = str(name or "").strip().lower()
    for b in bgs:
        if b.get("id", "").lower() == key or b["name"].lower() == key or (key and key in b["name"].lower()):
            return b
    return bgs[0]


def _enrich_beats(user, chars, raw_beats, auto_generate_sprites=False):
    char_by_slug = {c.slug: c for c in chars}
    default_char = chars[0]
    enriched = []
    for rb in (raw_beats or [])[:6]:
        if not isinstance(rb, dict):
            continue
        txt = str(rb.get("text") or "").strip()
        if not txt:
            continue
        sp_raw = str(rb.get("speaker_slug") or rb.get("speaker") or "").strip()
        sp_low = sp_raw.lower()
        kind_raw = str(rb.get("kind") or "").strip().lower()
        is_narrator = kind_raw == "narration" or sp_low in ("narrator", "narration", "system", "")
        c_slug = str(rb.get("character_slug") or ("" if is_narrator else sp_raw)).strip()
        stage_char = char_by_slug.get(c_slug) or char_by_slug.get(sp_low) or next(
            (c for c in chars if c.name.lower() == sp_low), default_char
        )
        stage_prof = messenger.char_profile(stage_char)

        emo = sprites.clean_name(rb.get("emotion") or "neutral") or "neutral"
        sp_info = resolve_or_generate_sprite(user, stage_char, emo, auto_generate=auto_generate_sprites)

        enriched.append({
            "id": "vnb_" + uuid.uuid4().hex[:8],
            "kind": "narration" if is_narrator else "dialogue",
            "speaker": "narrator" if is_narrator else stage_char.slug,
            "speaker_slug": "narrator" if is_narrator else stage_char.slug,
            "speaker_name": "Narrator" if is_narrator else stage_prof["display_name"],
            "character_slug": stage_char.slug,
            "character_name": stage_prof["display_name"],
            "emotion": sp_info["emotion"],
            "sprite_url": sp_info["url"],
            "is_new_sprite": sp_info.get("is_new", False),
            "needs_sprite_gen": False if is_narrator else sp_info.get("needs_gen", False),
            "text": txt[:500],
        })
    return enriched


def start_scene(user, thread=None, characters=None, location_hint="", auto_generate_sprites=False):
    """
    Launch a new Visual Novel Meet-Up Scene from a TeleChat `thread` (or selected `characters`).
    Selects music & backdrop, generates the opening 3–5 VN beats, resolves or generates character sprites,
    and saves `active_scene` into the user's VN state.
    """
    chars = list(characters or (thread.characters.all() if thread else []))
    if not chars:
        raise ai_client.AIError("Pick at least one character for the scene.")

    from mainapp.cards import user_name
    u_name = user_name(user)
    now_local = timezone.localtime(timezone.now())
    clock_str = now_local.strftime("%A, %d %B %Y, %H:%M")

    tracks = available_music_tracks(chars)
    bgs = available_backgrounds(chars)
    roster_text, moods_list = _build_char_roster(chars)

    telechat_lines = []
    if thread:
        td = messenger.thread_data(thread)
        for m in (td.get("messages") or [])[-10:]:
            if m.get("role") == "system":
                continue
            sp = m.get("sender_name") or m.get("role")
            txt = (m.get("text") or "").strip()
            if txt:
                telechat_lines.append(f"- [{m.get('time', '')}] {sp}: {txt[:200]}")
    telechat_context = "\n".join(telechat_lines) if telechat_lines else "(Characters agreed to meet up in person.)"

    model_info = messenger.active_model_texting_rules(user)
    model_rules = f"ACTIVE MODEL CALIBRATION ({model_info['label']}):\n{model_info['rules']}" if model_info.get("rules") else ""

    prompt = VN_SCENE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        model_rules=model_rules,
        existing_moods=moods_list,
        music_list="\n".join(f"- {t['name']} (id: {t['id']})" for t in tracks) or "- Default Theme",
        bg_list="\n".join(f"- {b['name']} (id: {b['id']})" for b in bgs) or "- Default Backdrop",
        user_persona=(getattr(user, "persona_description", "") or "")[:400],
        char_roster=roster_text,
        telechat_context=telechat_context,
        scene_history="(Scene is just beginning — set the stage as they meet!)",
        step_input=location_hint or "Begin the in-person meet-up scene right where the latest texts left off.",
    )

    parsed = _call_vn_json(user, prompt)
    chosen_music = _match_track(tracks, parsed.get("music_id") or parsed.get("music"))
    chosen_bg = _match_bg(bgs, parsed.get("background_id") or parsed.get("background"))
    beats = _enrich_beats(user, chars, parsed.get("beats"), auto_generate_sprites=auto_generate_sprites)
    if not beats:
        c0 = chars[0]
        p0 = messenger.char_profile(c0)
        sp0 = resolve_or_generate_sprite(user, c0, "neutral", auto_generate=False)
        beats = [{
            "id": "vnb_" + uuid.uuid4().hex[:8],
            "kind": "dialogue",
            "speaker": c0.slug,
            "speaker_slug": c0.slug,
            "speaker_name": p0["display_name"],
            "character_slug": c0.slug,
            "character_name": p0["display_name"],
            "emotion": "neutral",
            "sprite_url": sp0["url"],
            "is_new_sprite": False,
            "needs_sprite_gen": sp0["needs_gen"],
            "text": str(parsed.get("title") or "You finally made it."),
        }]

    scene = {
        "id": "vns_" + uuid.uuid4().hex[:8],
        "thread_id": thread.id if thread else None,
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
    save_vn_state(user, {"active_scene": scene})
    return scene


def step_scene(user, user_input="", auto_generate_sprites=None):
    """
    Advance the active Visual Novel scene by one turn (either with `user_input` action/dialogue or
    continuing automatically when `user_input` is empty).
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    if not scene:
        raise ai_client.AIError("No active Visual Novel scene. Start a scene first.")

    chars = list(Character.objects.filter(author=user, slug__in=scene.get("character_slugs") or []))
    if not chars:
        raise ai_client.AIError("Scene characters not found.")

    if auto_generate_sprites is None:
        auto_generate_sprites = bool(scene.get("auto_generate_sprites", False))
    else:
        scene["auto_generate_sprites"] = bool(auto_generate_sprites)

    from mainapp.cards import user_name
    u_name = user_name(user)
    now_local = timezone.localtime(timezone.now())
    clock_str = now_local.strftime("%A, %d %B %Y, %H:%M")

    history = list(scene.get("beats") or scene.get("history") or [])
    if user_input and user_input.strip():
        c0 = chars[0]
        last_beat = history[-1] if history else {}
        user_beat = {
            "id": "vnb_" + uuid.uuid4().hex[:8],
            "kind": "dialogue",
            "speaker": "user",
            "speaker_slug": "user",
            "speaker_name": u_name,
            "character_slug": last_beat.get("character_slug") or c0.slug,
            "character_name": last_beat.get("character_name") or c0.name,
            "emotion": last_beat.get("emotion") or "neutral",
            "sprite_url": last_beat.get("sprite_url") or "",
            "is_new_sprite": False,
            "needs_sprite_gen": False,
            "text": user_input.strip()[:500],
        }
        history.append(user_beat)

    hist_lines = []
    for b in history[-14:]:
        emo_tag = f" [{b.get('emotion')}]" if b.get("speaker_slug") not in ("narrator", "user") else ""
        hist_lines.append(f"- {b.get('speaker_name') or b.get('speaker')}{emo_tag}: {b.get('text')}")

    tracks = available_music_tracks(chars)
    bgs = available_backgrounds(chars)
    roster_text, moods_list = _build_char_roster(chars)
    model_info = messenger.active_model_texting_rules(user)
    model_rules = f"ACTIVE MODEL CALIBRATION ({model_info['label']}):\n{model_info['rules']}" if model_info.get("rules") else ""

    step_dir = (
        f"{u_name} just did/said: \"{user_input.strip()}\". React and advance the scene 3 to 5 beats."
        if (user_input and user_input.strip())
        else "Continue unfolding the scene for the next 3 to 5 beats."
    )

    prompt = VN_SCENE_PROMPT.format(
        user=u_name,
        clock=clock_str,
        model_rules=model_rules,
        existing_moods=moods_list,
        music_list="\n".join(f"- {t['name']} (id: {t['id']})" for t in tracks) or "- Default Theme",
        bg_list="\n".join(f"- {b['name']} (id: {b['id']})" for b in bgs) or "- Default Backdrop",
        user_persona=(getattr(user, "persona_description", "") or "")[:400],
        char_roster=roster_text,
        telechat_context=f"Location: {scene.get('location')}",
        scene_history="\n".join(hist_lines) or "(Start of scene)",
        step_input=step_dir,
    )

    parsed = _call_vn_json(user, prompt)
    if parsed.get("music_id") or parsed.get("music"):
        scene["music"] = _match_track(tracks, parsed.get("music_id") or parsed.get("music"))
    if parsed.get("background_id") or parsed.get("background"):
        scene["background"] = _match_bg(bgs, parsed.get("background_id") or parsed.get("background"))
    if parsed.get("location"):
        scene["location"] = str(parsed.get("location")).strip()[:120]

    new_beats = _enrich_beats(user, chars, parsed.get("beats"), auto_generate_sprites=auto_generate_sprites)
    if new_beats:
        history.extend(new_beats)
        scene["current_beats"] = new_beats
    scene["beats"] = history[-60:]
    scene["history"] = history[-60:]
    scene["handoff"] = parsed.get("handoff") if parsed.get("handoff") in ("user_turn", "auto_continue", "climax_ready") else "user_turn"
    scene["handoff_prompt"] = str(parsed.get("handoff_prompt") or "What do you do or say?").strip()[:140]
    scene["choices"] = [str(ch).strip()[:120] for ch in (parsed.get("choices") or []) if str(ch or "").strip()][:3]

    save_vn_state(user, {"active_scene": scene})
    return scene, new_beats


def generate_beat_sprite(user, beat_id="", char_slug="", emotion=""):
    """
    Dynamically generate and permanently store an expression sprite for `(char_slug, emotion)` on demand,
    updating any matching beats in the active scene.
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    target_char = Character.objects.filter(author=user, slug=char_slug).first()
    if not target_char and scene:
        for b in (scene.get("beats") or scene.get("current_beats") or []):
            if b.get("id") == beat_id:
                target_char = Character.objects.filter(author=user, slug=b.get("character_slug")).first()
                emotion = emotion or b.get("emotion")
                break
    if not target_char:
        raise ai_client.AIError("Character not found for sprite generation.")

    sp_info = resolve_or_generate_sprite(user, target_char, emotion or "neutral", auto_generate=True)

    if scene:
        for collection in (scene.get("beats") or [], scene.get("current_beats") or [], scene.get("history") or []):
            for b in collection:
                if b.get("character_slug") == target_char.slug and b.get("emotion") == sp_info["emotion"]:
                    b["sprite_url"] = sp_info["url"]
                    b["is_new_sprite"] = True
                    b["needs_sprite_gen"] = False
        save_vn_state(user, {"active_scene": scene})

    return scene, sp_info["url"], sp_info["emotion"], float(sp_info.get("cost") or 0.0)


def finish_scene_with_cg(user, cg_hint=""):
    """
    End the active Visual Novel scene by generating a full widescreen Finale Event CG image
    (using the character's 1 neutral + up to 4 extra references and art style lock),
    saving the completed scene + CG into the Gallery, and logging a memory notice in the linked TeleChat thread.
    """
    state = get_vn_state(user)
    scene = state.get("active_scene")
    if not scene:
        raise ai_client.AIError("No active Visual Novel scene to finish.")

    chars = list(Character.objects.filter(author=user, slug__in=scene.get("character_slugs") or []))
    if not chars:
        raise ai_client.AIError("Scene character not found.")
    lead_char = chars[0]
    lead_prof = messenger.char_profile(lead_char)

    from mainapp.cards import user_name
    u_name = user_name(user)

    transcript_lines = []
    for b in (scene.get("beats") or scene.get("history") or [])[-20:]:
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
        or f"Met up in person at {scene.get('location')} ({scene.get('title')})."
    ).strip()[:360]

    art_style = lead_prof.get("art_style_notes") or "exact same visual art style, brushwork, linework, shading, and color palette as the attached reference image(s)"
    appearance = lead_prof.get("appearance_notes") or (lead_char.description or "")[:550]
    refs = messenger.load_character_references(lead_char)

    full_cg_prompt = (
        f"Create a full-scene Visual Novel Event CG illustration featuring {', '.join(scene.get('character_names') or [lead_char.name])} at {scene.get('location')}.\n"
        f"CRITICAL IDENTITY & STYLE LOCK: Keep the EXACT same face, hair, eyes, proportions, and visual art style ({art_style}) as the attached reference image(s).\n"
        f"Camera angle & framing: {camera_angle}.\n"
        f"Character appearance: {appearance}\n"
        f"Event CG scene: {visual_prompt[:650]}"
    )

    img_bytes, cost = messenger.make_picture(user, full_cg_prompt, references=refs)
    rel_path = f"messenger/vn_cg/{lead_char.slug}-cg-{uuid.uuid4().hex[:8]}.png"
    saved_path = default_storage.save(rel_path, ContentFile(img_bytes))
    cg_url = default_storage.url(saved_path)

    now_hm = timezone.localtime(timezone.now()).strftime("%H:%M")
    finished_str = timezone.localtime(timezone.now()).strftime("%d %b %Y · %H:%M")
    all_beats = (scene.get("beats") or scene.get("history") or [])[-40:]
    gallery_entry = {
        "id": scene["id"],
        "thread_id": scene.get("thread_id"),
        "title": scene.get("title"),
        "location": scene.get("location"),
        "character_slugs": scene.get("character_slugs"),
        "character_names": scene.get("character_names"),
        "cg_url": cg_url,
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

    gallery = [gallery_entry] + [g for g in state["gallery"] if g.get("id") != scene["id"]]
    save_vn_state(user, {"active_scene": None, "gallery": gallery})

    # Write a scene completion notice & CG bubble into the linked TeleChat thread so phone chat remembers the meet-up!
    if scene.get("thread_id"):
        thread = MessengerThread.objects.filter(user=user, id=scene["thread_id"]).prefetch_related("characters").first()
        if thread:
            td = messenger.thread_data(thread)
            td["messages"].append({
                "id": uuid.uuid4().hex[:10],
                "role": "system",
                "text": f"🎬 Meet-Up Scene Completed: \"{scene.get('title')}\" ({scene.get('location')}) — {chat_summary}",
                "time": now_hm,
                "ts": time.time(),
            })
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
